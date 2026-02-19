"""Frontend integration tests — validates HTML/JS consistency across web pages.

Covers pages that require authenticated access (my-research.html, admin.html, etc.)
which are NOT included in test_integrity.py's parametrized DOM tests.

No LLM calls, no server required. Runs purely on static file analysis.

Usage:
    python3 -m pytest tests/test_frontend_integration.py -v
"""

import re
import inspect
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"


# ── my-research.html ─────────────────────────────────────────────────────────

class TestMyResearchPage:
    """Validates my-research.html content and DOM consistency."""

    @pytest.fixture(scope="class")
    def html(self):
        path = WEB_DIR / "my-research.html"
        assert path.exists(), "web/my-research.html not found"
        return path.read_text(encoding="utf-8")

    # -- Quota section text --

    def test_quota_heading_is_not_daily(self, html):
        """Quota is total (lifetime), not daily. Heading must not say 'Daily'."""
        # Find all h2 tags near the quota section
        h2_tags = re.findall(r'<h2>(.*?)</h2>', html)
        quota_headings = [h for h in h2_tags if "quota" in h.lower()]
        assert quota_headings, "No h2 with 'quota' found"
        for h in quota_headings:
            assert "daily" not in h.lower(), (
                f"Quota heading says '{h}' — should not reference 'daily' "
                f"since quota is total lifetime usage"
            )

    def test_quota_heading_text(self, html):
        """Quota heading should be 'Research Quota'."""
        assert "<h2>Research Quota</h2>" in html

    def test_quota_detail_does_not_say_today(self, html):
        """Quota detail text must not say 'used today' since it's total usage."""
        assert "used today" not in html, (
            "Found 'used today' in my-research.html — "
            "quota tracks total submissions, not daily"
        )

    def test_quota_detail_says_papers_submitted(self, html):
        """Quota detail should show 'papers submitted'."""
        assert "papers submitted" in html

    # -- DOM ID integrity --

    def test_quota_dom_ids_exist(self, html):
        """IDs referenced by renderQuota() must be defined in HTML."""
        required_ids = ["quota-arc", "quota-text", "quota-label", "quota-detail"]
        for dom_id in required_ids:
            assert f'id="{dom_id}"' in html, (
                f"Missing id='{dom_id}' in my-research.html — "
                f"renderQuota() references it"
            )

    def test_no_orphan_id_references(self, html):
        """Every getElementById() must reference an ID defined in the page."""
        id_def = set(re.findall(r'id=["\']([^"\']+)["\']', html))
        id_ref = set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', html))

        # Safe-guarded patterns (const el = getElementById(...); if (el))
        safe = set()
        for m in re.finditer(
            r'(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(["\']([^"\']+)["\']\);\s*\n\s*if\s*\(\1\)',
            html, re.MULTILINE,
        ):
            safe.add(m.group(2))

        orphans = (id_ref - safe) - id_def
        # Exclude dynamic IDs created in loops
        dynamic_prefixes = ("wf-", "perf-", "activity-")
        orphans = {o for o in orphans if not any(o.startswith(p) for p in dynamic_prefixes)}

        assert orphans == set(), (
            f"my-research.html: getElementById() references undefined IDs:\n"
            + "\n".join(f"  #{oid}" for oid in sorted(orphans))
        )

    # -- API endpoint references --

    def test_fetches_my_quota_endpoint(self, html):
        """Page must fetch /api/my-quota for quota data."""
        assert "/api/my-quota" in html

    def test_renderQuota_uses_api_response_fields(self, html):
        """renderQuota() must access .used and .limit from API response."""
        # Extract renderQuota function body
        match = re.search(r'function renderQuota\(data\)\s*\{(.*?)\n\s{8}\}', html, re.DOTALL)
        assert match, "renderQuota() function not found"
        body = match.group(1)
        assert "data.used" in body, "renderQuota() must read data.used"
        assert "data.limit" in body, "renderQuota() must read data.limit"


# ── API contract: /api/my-quota ──────────────────────────────────────────────

class TestMyQuotaContract:
    """check_quota() return schema must match what renderQuota() expects."""

    def test_check_quota_returns_used_and_limit(self):
        from research_cli.db import check_quota
        import inspect
        source = inspect.getsource(check_quota)
        # The return dict must include 'used' and 'limit'
        assert '"used"' in source or "'used'" in source, "check_quota() must return 'used'"
        assert '"limit"' in source or "'limit'" in source, "check_quota() must return 'limit'"

    def test_get_total_usage_is_not_daily(self):
        """get_total_usage must count ALL time, not just today."""
        from research_cli.db import get_total_usage
        source = inspect.getsource(get_total_usage)
        # Must NOT filter by date (e.g., WHERE date = ... or DATE(...))
        assert "DATE(" not in source.upper() or "created_at" not in source, (
            "get_total_usage() appears to filter by date — "
            "quota should count total lifetime usage"
        )


# ── apply.html — instant signup flow ─────────────────────────────────────────

class TestApplyPageInstantSignup:
    """Validates apply.html implements instant approval: no status check,
    auto-login via setAuth(), and redirect to ask-topic.html."""

    @pytest.fixture(scope="class")
    def html(self):
        path = WEB_DIR / "apply.html"
        assert path.exists(), "web/apply.html not found"
        return path.read_text(encoding="utf-8")

    def test_no_status_check_section(self, html):
        """Status check section must not exist — signup is instant."""
        assert "Check Application Status" not in html
        assert 'id="status-email"' not in html
        assert "checkStatus" not in html

    def test_calls_setAuth_on_success(self, html):
        """Submit handler must call setAuth() to log the user in."""
        assert "setAuth(" in html

    def test_redirects_to_ask_topic(self, html):
        """After signup, user is redirected to ask-topic.html."""
        assert "ask-topic.html" in html

    def test_redirects_logged_in_users(self, html):
        """Already-logged-in users visiting apply.html get redirected."""
        assert "if (getAuth())" in html

    def test_button_says_create_account(self, html):
        """Submit button should say 'Create Account', not 'Submit Application'."""
        assert "Submit Application" not in html
        assert "Create Account" in html


# ── API contract: create_researcher() instant approval ───────────────────────

class TestCreateResearcherInstantApproval:
    """create_researcher() must return api_key and set status='approved'."""

    def test_returns_api_key(self):
        source = inspect.getsource(__import__("research_cli.db", fromlist=["create_researcher"]).create_researcher)
        assert '"api_key"' in source or "'api_key'" in source, (
            "create_researcher() must return 'api_key' in result dict"
        )

    def test_status_is_approved(self):
        source = inspect.getsource(__import__("research_cli.db", fromlist=["create_researcher"]).create_researcher)
        assert "'approved'" in source or '"approved"' in source, (
            "create_researcher() must set status to 'approved'"
        )
        assert "status='pending'" not in source.replace("-- pending", ""), (
            "create_researcher() must not insert status='pending' for researchers"
        )


# ── Authenticated pages DOM integrity ────────────────────────────────────────

class TestAuthenticatedPagesDOMIntegrity:
    """DOM ID reference checks for pages not covered in test_integrity.py."""

    @pytest.fixture(scope="class")
    def page_data(self):
        """Parse each authenticated HTML file for defined/referenced IDs."""
        id_def_pattern = re.compile(r'id=["\']([^"\']+)["\']')
        id_ref_pattern = re.compile(r'getElementById\(["\']([^"\']+)["\']\)')
        safe_pattern = re.compile(
            r'(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(["\']([^"\']+)["\']\);\s*\n\s*if\s*\(\1\)',
            re.MULTILINE,
        )

        pages = {}
        for page_name in ("my-research.html", "login.html", "apply.html",
                          "admin.html", "admin-edit.html", "about.html",
                          "api-docs.html", "blog-reader.html"):
            html_file = WEB_DIR / page_name
            if not html_file.exists():
                continue
            content = html_file.read_text(encoding="utf-8")
            defined = set(id_def_pattern.findall(content))
            referenced = set(id_ref_pattern.findall(content))
            safe_ids = {m.group(2) for m in safe_pattern.finditer(content)}
            pages[page_name] = {
                "defined": defined,
                "referenced": referenced - safe_ids,
            }
        return pages

    @pytest.mark.parametrize("page", [
        "my-research.html",
        "login.html",
        "apply.html",
        "admin.html",
    ])
    def test_no_orphan_id_references(self, page_data, page):
        if page not in page_data:
            pytest.skip(f"{page} not found")

        data = page_data[page]
        # Dynamic ID prefixes generated in JS loops
        dynamic_prefixes = (
            "wf-", "perf-", "activity-", "key-", "app-",
            "researcher-", "article-", "sub-",
        )

        orphans = []
        for ref_id in data["referenced"]:
            if ref_id in data["defined"]:
                continue
            if any(ref_id.startswith(p) for p in dynamic_prefixes):
                continue
            orphans.append(ref_id)

        assert orphans == [], (
            f"{page}: getElementById() references undefined IDs:\n"
            + "\n".join(f"  #{oid}" for oid in sorted(orphans))
        )


# ── Fetch URL integrity for authenticated pages ─────────────────────────────

class TestAuthenticatedPagesFetchURLs:
    """fetch() calls in authenticated pages must use API_BASE or relative paths."""

    DYNAMIC_PATH_PATTERNS = [
        r'data/\$\{',
        r'\$\{API_BASE\}',
        r'\$\{encodeURI',
        r'/api/',
    ]

    @pytest.fixture(scope="class")
    def all_fetches(self):
        fetch_pattern = re.compile(r"""fetch\(\s*[`'"](.*?)[`'"]\s*[,)]""")
        results = []
        for page_name in ("my-research.html", "login.html", "apply.html",
                          "admin.html", "admin-edit.html"):
            html_file = WEB_DIR / page_name
            if not html_file.exists():
                continue
            content = html_file.read_text(encoding="utf-8")
            for match in fetch_pattern.finditer(content):
                url = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                results.append({"file": page_name, "line": line_num, "url": url})
        return results

    def test_no_hardcoded_api_urls(self, all_fetches):
        """No fetch() should use hardcoded http(s) URLs for API calls."""
        bad = []
        for f in all_fetches:
            url = f["url"]
            if url.startswith("http") and "/api/" in url:
                bad.append(f"{f['file']}:{f['line']} → fetch('{url}')")

        assert bad == [], (
            f"Hardcoded API URLs found (should use relative paths or ${{API_BASE}}):\n"
            + "\n".join(f"  {b}" for b in bad)
        )

    def test_no_hardcoded_static_data_fetches(self, all_fetches):
        """No fetch() should reference hardcoded static data/ files."""
        hardcoded = []
        for f in all_fetches:
            url = f["url"]
            if any(re.search(p, url) for p in self.DYNAMIC_PATH_PATTERNS):
                continue
            if url.startswith("data/") and "${" not in url:
                hardcoded.append(f"{f['file']}:{f['line']} → fetch('{url}')")

        assert hardcoded == [], (
            f"Hardcoded static data/ fetches found:\n"
            + "\n".join(f"  {h}" for h in hardcoded)
        )
