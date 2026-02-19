"""Admin article editor — API endpoint tests.

Tests the full admin article CRUD cycle: list, get (with title), update
(content + title, title-only, content-only), and the 5-location data sync.
Also validates HTML escaping, ensure_ascii=False, and auth enforcement.

Usage:
    python3 -m pytest tests/test_admin_articles.py -v

No LLM calls, no external network. Uses FastAPI TestClient + temp fixtures.
"""

import json
import os
import re
import shutil
import textwrap
from pathlib import Path

import pytest

# Set a known admin key before importing api_server
os.environ["RESEARCH_ADMIN_KEY"] = "test-admin-key-12345"

from fastapi.testclient import TestClient  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent

# Unique test project ID unlikely to collide with real data
TEST_PROJECT_ID = "__test_admin_article_9999__"
TEST_TITLE = "Test Article Title 테스트"
TEST_CONTENT = textwrap.dedent("""\
    # Introduction

    This is a test article with **bold** and *italic*.

    ## Methods

    We used $E = mc^2$ in our analysis.

    ## Results

    See Table 1 for results.

    ## Conclusion

    In conclusion, the answer is 42.
""")


@pytest.fixture(scope="module")
def client():
    """Create a TestClient with the admin key set."""
    from api_server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers():
    return {
        "Content-Type": "application/json",
        "X-API-Key": "test-admin-key-12345",
    }


@pytest.fixture(scope="module")
def bad_headers():
    return {
        "Content-Type": "application/json",
        "X-API-Key": "wrong-key",
    }


@pytest.fixture(scope="module", autouse=True)
def setup_test_article(client, admin_headers):
    """Create a test article in all 5 data locations, clean up after."""
    # 1. index.json — add entry
    index_path = ROOT / "web" / "data" / "index.json"
    with open(index_path) as f:
        original_index = json.load(f)

    index_data = json.loads(json.dumps(original_index))  # deep copy
    index_data["projects"].insert(0, {
        "id": TEST_PROJECT_ID,
        "title": TEST_TITLE,
        "topic": TEST_TITLE,
        "final_score": 8.0,
        "passed": True,
        "status": "completed",
        "total_rounds": 1,
        "rounds": [],
        "timestamp": "2026-01-01T00:00:00",
        "author": "Test Author",
    })
    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    # 2. web/articles/{id}.md
    md_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.md"
    md_path.write_text(TEST_CONTENT, encoding="utf-8")

    # 3. web/articles/{id}.html — create minimal static article
    html_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.html"
    escaped = TEST_CONTENT.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    html_path.write_text(
        f'<!DOCTYPE html><html><head><title>{TEST_TITLE}</title></head>'
        f'<body><script>const rawMarkdown = `{escaped}`;</script></body></html>',
        encoding="utf-8",
    )

    # 4. results/{id}/ — manuscript + workflow_complete.json
    results_dir = ROOT / "results" / TEST_PROJECT_ID
    results_dir.mkdir(parents=True, exist_ok=True)

    manuscript_path = results_dir / "manuscript_v2.md"
    manuscript_path.write_text(TEST_CONTENT, encoding="utf-8")

    workflow_path = results_dir / "workflow_complete.json"
    workflow_path.write_text(json.dumps({
        "title": TEST_TITLE,
        "topic": TEST_TITLE,
        "author": "Test Author",
        "passed": True,
        "final_score": 8.0,
        "rounds": [],
    }, ensure_ascii=False), encoding="utf-8")

    yield  # tests run here

    # ── Cleanup ──
    # Restore original index.json
    with open(index_path, "w") as f:
        json.dump(original_index, f, indent=2, ensure_ascii=False)

    # Remove test article files
    md_path.unlink(missing_ok=True)
    html_path.unlink(missing_ok=True)
    if results_dir.exists():
        shutil.rmtree(results_dir)


# ── 1. Auth Enforcement ──────────────────────────────────────────────────────

class TestAdminAuth:
    """Admin endpoints must reject invalid/missing keys with 403."""

    def test_list_articles_no_key(self, client):
        resp = client.get("/api/admin/articles")
        assert resp.status_code == 403

    def test_list_articles_wrong_key(self, client, bad_headers):
        resp = client.get("/api/admin/articles", headers=bad_headers)
        assert resp.status_code == 403

    def test_get_article_wrong_key(self, client, bad_headers):
        resp = client.get(f"/api/admin/articles/{TEST_PROJECT_ID}", headers=bad_headers)
        assert resp.status_code == 403

    def test_put_article_wrong_key(self, client, bad_headers):
        resp = client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=bad_headers,
            json={"title": "Hacked"},
        )
        assert resp.status_code == 403


# ── 2. List Articles ─────────────────────────────────────────────────────────

class TestListArticles:
    """GET /api/admin/articles must return test article."""

    def test_list_includes_test_article(self, client, admin_headers):
        resp = client.get("/api/admin/articles", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "articles" in data
        ids = [a["id"] for a in data["articles"]]
        assert TEST_PROJECT_ID in ids

    def test_list_article_has_topic(self, client, admin_headers):
        resp = client.get("/api/admin/articles", headers=admin_headers)
        articles = resp.json()["articles"]
        entry = next(a for a in articles if a["id"] == TEST_PROJECT_ID)
        assert entry["topic"] == TEST_TITLE


# ── 3. Get Article Source ─────────────────────────────────────────────────────

class TestGetArticleSource:
    """GET /api/admin/articles/{id} must return content + title."""

    def test_returns_content(self, client, admin_headers):
        resp = client.get(f"/api/admin/articles/{TEST_PROJECT_ID}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == TEST_PROJECT_ID
        assert data["format"] == "markdown"
        assert "Introduction" in data["content"]
        assert "$E = mc^2$" in data["content"]

    def test_returns_title(self, client, admin_headers):
        """API must return title from index.json (bug fix verification)."""
        resp = client.get(f"/api/admin/articles/{TEST_PROJECT_ID}", headers=admin_headers)
        data = resp.json()
        assert "title" in data
        assert data["title"] == TEST_TITLE

    def test_returns_korean_title_correctly(self, client, admin_headers):
        """Title with Korean characters must come back intact."""
        resp = client.get(f"/api/admin/articles/{TEST_PROJECT_ID}", headers=admin_headers)
        data = resp.json()
        assert "테스트" in data["title"]

    def test_not_found_returns_404(self, client, admin_headers):
        resp = client.get("/api/admin/articles/nonexistent-article-id", headers=admin_headers)
        assert resp.status_code == 404

    def test_html_extraction_fallback(self, client, admin_headers):
        """If .md file missing, content is extracted from .html."""
        md_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.md"
        md_backup = md_path.read_text(encoding="utf-8")
        md_path.unlink()
        try:
            resp = client.get(f"/api/admin/articles/{TEST_PROJECT_ID}", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["format"] == "extracted"
            assert len(data["content"]) > 0
        finally:
            md_path.write_text(md_backup, encoding="utf-8")


# ── 4. Update Article — Content + Title ───────────────────────────────────────

class TestUpdateArticleContentAndTitle:
    """PUT /api/admin/articles/{id} with both title and content."""

    NEW_TITLE = "Updated Title 수정됨"
    NEW_CONTENT = "# Updated\n\nNew content here.\n\n## Section 2\n\nMore text.\n"

    def test_update_returns_success(self, client, admin_headers):
        resp = client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"title": self.NEW_TITLE, "content": self.NEW_CONTENT},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"

    def test_md_file_updated(self):
        """web/articles/{id}.md must have new content."""
        md_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.md"
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert content == self.NEW_CONTENT

    def test_static_html_regenerated(self):
        """web/articles/{id}.html must have new title and content embedded."""
        html_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.html"
        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Updated Title" in html
        assert "수정됨" in html

    def test_manuscript_updated(self):
        """results/{id}/manuscript_v*.md must have new content."""
        results_dir = ROOT / "results" / TEST_PROJECT_ID
        versions = sorted(results_dir.glob("manuscript_v*.md"))
        assert len(versions) > 0
        latest = versions[-1].read_text(encoding="utf-8")
        assert latest == self.NEW_CONTENT

    def test_workflow_json_title_updated(self):
        """results/{id}/workflow_complete.json must have new title/topic."""
        wf_path = ROOT / "results" / TEST_PROJECT_ID / "workflow_complete.json"
        assert wf_path.exists()
        data = json.load(open(wf_path))
        assert data["title"] == self.NEW_TITLE
        assert data["topic"] == self.NEW_TITLE

    def test_index_json_topic_updated(self):
        """web/data/index.json entry must have new topic."""
        with open(ROOT / "web" / "data" / "index.json") as f:
            data = json.load(f)
        entry = next(p for p in data["projects"] if p["id"] == TEST_PROJECT_ID)
        assert entry["topic"] == self.NEW_TITLE

    def test_index_json_preserves_unicode(self):
        """index.json must contain raw Unicode, not \\uXXXX escapes."""
        raw = (ROOT / "web" / "data" / "index.json").read_text(encoding="utf-8")
        # Our test title has Korean — it should appear as-is, not escaped
        assert "수정됨" in raw

    def test_get_reflects_update(self, client, admin_headers):
        """GET after PUT must return updated title and content."""
        resp = client.get(f"/api/admin/articles/{TEST_PROJECT_ID}", headers=admin_headers)
        data = resp.json()
        assert data["title"] == self.NEW_TITLE
        assert data["content"] == self.NEW_CONTENT


# ── 5. Update Article — Title Only ────────────────────────────────────────────

class TestUpdateArticleTitleOnly:
    """PUT with title but no content must still update static HTML."""

    TITLE_ONLY = "Title Only Change 제목만"

    def test_title_only_update(self, client, admin_headers):
        resp = client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"title": self.TITLE_ONLY},
        )
        assert resp.status_code == 200

    def test_static_html_has_new_title(self):
        """Static HTML must be regenerated with new title even without content change."""
        html_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.html"
        html = html_path.read_text(encoding="utf-8")
        assert "Title Only Change" in html
        assert "제목만" in html

    def test_md_file_unchanged(self):
        """Markdown source must not be wiped when content is omitted."""
        md_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.md"
        content = md_path.read_text(encoding="utf-8")
        assert len(content) > 0

    def test_workflow_json_updated(self):
        wf_path = ROOT / "results" / TEST_PROJECT_ID / "workflow_complete.json"
        data = json.load(open(wf_path))
        assert data["title"] == self.TITLE_ONLY
        assert data["topic"] == self.TITLE_ONLY


# ── 6. Update Article — Content Only ──────────────────────────────────────────

class TestUpdateArticleContentOnly:
    """PUT with content but no title."""

    CONTENT_ONLY = "# Content Only\n\nJust updating the body.\n"

    def test_content_only_update(self, client, admin_headers):
        resp = client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"content": self.CONTENT_ONLY},
        )
        assert resp.status_code == 200

    def test_md_file_has_new_content(self):
        md_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.md"
        assert md_path.read_text(encoding="utf-8") == self.CONTENT_ONLY

    def test_manuscript_has_new_content(self):
        results_dir = ROOT / "results" / TEST_PROJECT_ID
        versions = sorted(results_dir.glob("manuscript_v*.md"))
        latest = versions[-1].read_text(encoding="utf-8")
        assert latest == self.CONTENT_ONLY


# ── 7. Empty Content Save ─────────────────────────────────────────────────────

class TestEmptyContentSave:
    """Saving empty string content must work (not silently skip)."""

    def test_empty_content_accepted(self, client, admin_headers):
        resp = client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"content": ""},
        )
        assert resp.status_code == 200

    def test_md_file_is_empty(self):
        md_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.md"
        assert md_path.read_text(encoding="utf-8") == ""

    def test_restore_content(self, client, admin_headers):
        """Restore content for subsequent tests."""
        client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"content": TEST_CONTENT},
        )


# ── 8. HTML Escaping in Static Article ────────────────────────────────────────

class TestHTMLEscaping:
    """Title/author with special chars must be HTML-escaped in static HTML."""

    XSS_TITLE = '<script>alert("xss")</script> & "quotes"'

    def test_xss_title_escaped_in_html(self, client, admin_headers):
        resp = client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"title": self.XSS_TITLE, "content": "# Safe\n\nBody.\n"},
        )
        assert resp.status_code == 200

        html_path = ROOT / "web" / "articles" / f"{TEST_PROJECT_ID}.html"
        html = html_path.read_text(encoding="utf-8")

        # Raw <script> must NOT appear in the HTML (must be escaped)
        assert '<script>alert' not in html
        # Escaped version should appear
        assert '&lt;script&gt;' in html
        assert '&amp;' in html
        assert '&quot;' in html

    def test_restore_title(self, client, admin_headers):
        """Restore normal title."""
        client.put(
            f"/api/admin/articles/{TEST_PROJECT_ID}",
            headers=admin_headers,
            json={"title": TEST_TITLE, "content": TEST_CONTENT},
        )


# ── 9. Static File Integrity (admin-edit.html) ───────────────────────────────

class TestAdminEditHTML:
    """admin-edit.html must exist and have correct structure."""

    @pytest.fixture(scope="class")
    def html(self):
        path = ROOT / "web" / "admin-edit.html"
        assert path.exists(), "web/admin-edit.html not found"
        return path.read_text(encoding="utf-8")

    def test_no_api_key_in_url_params(self, html):
        """admin-edit.html must NOT read key from URL (sessionStorage only)."""
        assert "params.get('key')" not in html
        assert "params.get(\"key\")" not in html

    def test_reads_key_from_session_storage(self, html):
        """Must use sessionStorage for admin key."""
        assert "sessionStorage.getItem('admin_key')" in html

    def test_clears_session_on_403(self, html):
        """Must clear sessionStorage on 403 response."""
        assert "sessionStorage.removeItem('admin_key')" in html

    def test_no_article_css_import(self, html):
        """Must NOT import article.css stylesheet (breaks layout)."""
        assert 'href="styles/article.css"' not in html
        assert "href='styles/article.css'" not in html

    def test_has_editor_and_preview_panes(self, html):
        assert 'edit-pane-editor' in html
        assert 'edit-pane-preview' in html

    def test_has_save_button(self, html):
        assert 'saveArticle()' in html

    def test_has_ctrl_s_shortcut(self, html):
        assert "e.key === 's'" in html

    def test_has_beforeunload_guard(self, html):
        assert 'beforeunload' in html

    def test_has_debounced_preview(self, html):
        assert 'debounceTimer' in html
        assert 'renderPreview' in html

    def test_sends_content_not_null(self, html):
        """Save must send content directly, not content || null."""
        # The old bug: content || null converted "" to null
        assert 'content: content }' in html or 'content: content,' in html
        # Must NOT have the old buggy pattern
        assert 'content: content || null' not in html


# ── 10. admin.html sessionStorage Integration ────────────────────────────────

class TestAdminHTMLSessionStorage:
    """admin.html must use sessionStorage for admin key."""

    @pytest.fixture(scope="class")
    def html(self):
        path = ROOT / "web" / "admin.html"
        assert path.exists()
        return path.read_text(encoding="utf-8")

    def test_stores_key_in_session_storage(self, html):
        assert "sessionStorage.setItem('admin_key'" in html

    def test_reads_key_from_session_storage(self, html):
        assert "sessionStorage.getItem('admin_key')" in html

    def test_clears_key_on_failure(self, html):
        assert "sessionStorage.removeItem('admin_key')" in html

    def test_edit_url_has_no_key_param(self, html):
        """editArticle() redirect URL must NOT contain &key=."""
        # Find the editArticle function
        match = re.search(r'function editArticle.*?\n.*?href\s*=\s*[`"\'](.*?)[`"\']', html, re.DOTALL)
        if match:
            url = match.group(1)
            assert 'key=' not in url, f"editArticle URL still contains key param: {url}"

    def test_auto_authenticate_on_load(self, html):
        """Must attempt auto-auth from sessionStorage on page load."""
        assert "authenticate(saved)" in html or "authenticate(key)" in html


# ── 11. DOM ID Integrity for admin-edit.html ──────────────────────────────────

class TestAdminEditDOMIntegrity:
    """All getElementById() refs in admin-edit.html must have matching IDs."""

    def test_no_orphan_dom_references(self):
        path = ROOT / "web" / "admin-edit.html"
        content = path.read_text(encoding="utf-8")

        id_def = re.compile(r'id=["\']([^"\']+)["\']')
        id_ref = re.compile(r'getElementById\(["\']([^"\']+)["\']\)')

        defined = set(id_def.findall(content))
        referenced = set(id_ref.findall(content))

        orphans = referenced - defined
        assert orphans == set(), (
            f"admin-edit.html: getElementById() references undefined IDs: {orphans}"
        )


# ── 12. API Endpoint Registration ─────────────────────────────────────────────

class TestArticleEndpointRegistration:
    """All admin article endpoints must be registered in the app."""

    @pytest.fixture(scope="class")
    def app_routes(self):
        from api_server import app
        routes = {}
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.setdefault(route.path, set()).update(route.methods)
        return routes

    @pytest.mark.parametrize("path,method", [
        ("/api/admin/articles", "GET"),
        ("/api/admin/articles/{project_id}", "GET"),
        ("/api/admin/articles/{project_id}", "PUT"),
    ])
    def test_endpoint_exists(self, app_routes, path, method):
        assert path in app_routes, f"Endpoint {path} not found"
        assert method in app_routes[path], f"{path} missing method {method}"
