"""System integrity tests — no LLM calls, zero cost, runs in seconds.

Validates that code changes haven't broken imports, configs, data models,
API endpoints, static assets, the citation pipeline, or frontend-backend contracts.

Usage:
    python3 -m pytest tests/test_integrity.py -v
"""

import json
import re
import importlib
from pathlib import Path

import pytest

# Project root
ROOT = Path(__file__).resolve().parent.parent


# ── 1-1. Import & Module Integrity ──────────────────────────────────────────

class TestImports:
    """Every core module must import without error."""

    @pytest.mark.parametrize("module", [
        "research_cli.agents.lead_author",
        "research_cli.agents.coauthor",
        "research_cli.agents.team_composer",
        "research_cli.agents.writer_team_composer",
        "research_cli.agents.moderator",
        "research_cli.agents.specialist_factory",
        "research_cli.agents.writer",
        "research_cli.agents.integration_editor",
        "research_cli.workflow.collaborative_research",
        "research_cli.workflow.manuscript_writing",
        "research_cli.workflow.collaborative_workflow",
        "research_cli.workflow.orchestrator",
        "research_cli.utils.source_retriever",
        "research_cli.utils.citation_manager",
        "research_cli.utils.json_repair",
        "research_cli.model_config",
        "research_cli.categories",
        "research_cli.performance",
        "research_cli.models.manuscript",
        "research_cli.models.collaborative_research",
        "research_cli.models.author",
        "research_cli.models.expert",
    ])
    def test_import_module(self, module):
        importlib.import_module(module)

    def test_import_export_to_web(self):
        importlib.import_module("export_to_web")


# ── 1-2. Config Integrity ──────────────────────────────────────────────────

class TestConfig:
    """config/models.json must parse correctly with required structure."""

    @pytest.fixture(scope="class")
    def config(self):
        path = ROOT / "config" / "models.json"
        assert path.exists(), "config/models.json not found"
        with open(path) as f:
            return json.load(f)

    def test_config_parses(self, config):
        assert isinstance(config, dict)

    def test_required_roles_exist(self, config):
        roles = config.get("roles", {})
        for required in ("lead_author", "coauthor", "reviewer_rotation"):
            assert required in roles, f"Missing required role: {required}"

    def test_reviewer_rotation_has_3_plus(self, config):
        rotation = config["roles"]["reviewer_rotation"]
        assert isinstance(rotation, list)
        assert len(rotation) >= 3, f"reviewer_rotation has only {len(rotation)} entries (need >=3)"

    def test_role_provider_model_pairs(self, config):
        roles = config.get("roles", {})
        tiers = config.get("tiers", {})
        for role_name, role_cfg in roles.items():
            if role_name == "reviewer_rotation":
                for entry in role_cfg:
                    assert "provider" in entry, f"reviewer_rotation entry missing 'provider'"
                    assert "model" in entry, f"reviewer_rotation entry missing 'model'"
                continue
            if isinstance(role_cfg, dict) and "tier" in role_cfg:
                tier_name = role_cfg["tier"]
                assert tier_name in tiers, f"Role '{role_name}' references unknown tier '{tier_name}'"

    def test_tiers_have_primary(self, config):
        tiers = config.get("tiers", {})
        for tier_name, tier in tiers.items():
            assert "primary" in tier, f"Tier '{tier_name}' missing 'primary'"
            primary = tier["primary"]
            assert "model" in primary, f"Tier '{tier_name}' primary missing 'model'"
            assert "provider" in primary, f"Tier '{tier_name}' primary missing 'provider'"

    def test_pricing_section_exists(self, config):
        assert "pricing" in config, "Missing 'pricing' section"
        pricing = config["pricing"]
        assert len(pricing) > 0, "Pricing section is empty"
        for model_name, prices in pricing.items():
            assert "input" in prices, f"Pricing for '{model_name}' missing 'input'"
            assert "output" in prices, f"Pricing for '{model_name}' missing 'output'"


# ── 1-3. API Endpoint Integrity ─────────────────────────────────────────────

class TestAPIEndpoints:
    """api_server.py must import and expose required endpoints."""

    @pytest.fixture(scope="class")
    def app(self):
        pytest.importorskip("fastapi")
        from api_server import app
        return app

    def test_app_import(self, app):
        assert app is not None

    @pytest.mark.parametrize("path,method", [
        ("/api/health", "GET"),
        ("/api/start-workflow", "POST"),
        ("/api/workflows", "GET"),
        ("/api/workflow-status/{project_id}", "GET"),
        ("/api/classify-topic", "POST"),
        ("/api/propose-team", "POST"),
        ("/api/version", "GET"),
    ])
    def test_endpoint_exists(self, app, path, method):
        """Check that required endpoint exists with correct HTTP method."""
        route_paths = {}
        for route in app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                route_paths[route.path] = route.methods

        assert path in route_paths, f"Endpoint {path} not found in app routes"
        assert method in route_paths[path], (
            f"Endpoint {path} exists but method {method} not found "
            f"(has: {route_paths[path]})"
        )


# ── 1-4. Web Static File Integrity ──────────────────────────────────────────

class TestWebStaticFiles:
    """Required HTML, CSS, JS files must exist."""

    @pytest.mark.parametrize("filename", [
        "index.html",
        "article.html",
        "ask-topic.html",
        "submit.html",
        "review.html",
    ])
    def test_html_page_exists(self, filename):
        path = ROOT / "web" / filename
        assert path.exists(), f"Missing web page: web/{filename}"

    def test_main_css_exists(self):
        assert (ROOT / "web" / "styles" / "main.css").exists()

    def test_js_directory_exists(self):
        assert (ROOT / "web" / "js").is_dir()


# ── 1-5. Citation Pipeline Unit Tests ───────────────────────────────────────

class TestCitationPipeline:
    """CitationManager must correctly extract, validate, and count citations."""

    @pytest.fixture(scope="class")
    def cm(self):
        from research_cli.utils.citation_manager import CitationManager
        return CitationManager

    @pytest.fixture(scope="class")
    def make_ref(self):
        from research_cli.models.collaborative_research import Reference
        def _make(ref_id):
            return Reference(
                id=ref_id, authors=["Author"], title=f"Paper {ref_id}",
                venue="Journal", year=2025
            )
        return _make

    def test_extract_simple(self, cm):
        assert cm.extract_citations("[1], [2] and [3]") == [1, 2, 3]

    def test_extract_grouped(self, cm):
        assert cm.extract_citations("[1,2,3]") == [1, 2, 3]

    def test_extract_mixed(self, cm):
        result = cm.extract_citations("[1], [2,3] and [4]")
        assert result == [1, 2, 3, 4]

    def test_extract_empty(self, cm):
        assert cm.extract_citations("No citations here.") == []

    def test_extract_deduplicates(self, cm):
        result = cm.extract_citations("[1] and [1,2]")
        assert result == [1, 2]

    def test_validate_all_matched(self, cm, make_ref):
        refs = [make_ref(1), make_ref(2), make_ref(3)]
        text = "As shown in [1] and [2,3]."
        is_valid, errors = cm.validate_citations(text, refs)
        assert is_valid
        assert errors == []

    def test_validate_missing_reference(self, cm, make_ref):
        refs = [make_ref(1)]
        text = "As shown in [1] and [5]."
        is_valid, errors = cm.validate_citations(text, refs)
        assert not is_valid
        assert len(errors) == 1
        assert "[5]" in errors[0]

    def test_statistics_accuracy(self, cm, make_ref):
        refs = [make_ref(1), make_ref(2), make_ref(3), make_ref(4)]
        text = "See [1] and [2,3]."
        stats = cm.get_citation_statistics(text, refs)
        assert stats["total_citations"] == 3
        assert stats["unique_citations"] == 3
        assert stats["total_references"] == 4
        assert stats["unused_references"] == 1
        assert 4 in stats["unused_reference_ids"]

    def test_format_inline_citation(self, cm):
        assert cm.format_inline_citation([1, 2, 3]) == "[1,2,3]"


# ── 1-6. Model / Data Structure Integrity ────────────────────────────────────

class TestDataModels:
    """Data model serialization round-trips must be identity."""

    def test_section_spec_relevant_references_field(self):
        from research_cli.models.manuscript import SectionSpec
        spec = SectionSpec(
            id="intro", title="Introduction", order=1,
            purpose="Introduce the topic", key_points=["point1"],
            target_length=500
        )
        assert hasattr(spec, "relevant_references")
        assert spec.relevant_references == []

    def test_section_spec_roundtrip(self):
        from research_cli.models.manuscript import SectionSpec
        original = SectionSpec(
            id="bg", title="Background", order=2,
            purpose="Background info", key_points=["a", "b"],
            target_length=800,
            relevant_references=[1, 3, 5],
            relevant_findings=["f1"],
        )
        restored = SectionSpec.from_dict(original.to_dict())
        assert restored.to_dict() == original.to_dict()

    def test_manuscript_plan_roundtrip(self):
        from research_cli.models.manuscript import ManuscriptPlan, SectionSpec
        plan = ManuscriptPlan(
            title="Test Plan",
            abstract_outline="An outline",
            sections=[
                SectionSpec(
                    id="intro", title="Intro", order=1,
                    purpose="Purpose", key_points=["kp"],
                    target_length=300, relevant_references=[1]
                ),
            ],
            target_length=2000,
        )
        restored = ManuscriptPlan.from_dict(plan.to_dict())
        assert restored.to_dict() == plan.to_dict()

    def test_section_draft_roundtrip(self):
        from research_cli.models.manuscript import SectionDraft
        draft = SectionDraft(
            id="intro", title="Intro", content="Hello world",
            word_count=2, citations=[1, 2], author="Lead"
        )
        restored = SectionDraft.from_dict(draft.to_dict())
        assert restored.to_dict() == draft.to_dict()

    def test_manuscript_to_dict(self):
        from research_cli.models.manuscript import Manuscript
        ms = Manuscript(
            title="Title", abstract="Abstract", content="Body",
            references="Refs", word_count=100, citation_count=5
        )
        d = ms.to_dict()
        assert d["title"] == "Title"
        assert d["word_count"] == 100

    def test_reference_roundtrip(self):
        from research_cli.models.collaborative_research import Reference
        ref = Reference(
            id=1, authors=["Alice", "Bob"], title="Paper",
            venue="ICML", year=2024, url="https://example.com",
            doi="10.1234/test", summary="Good paper"
        )
        restored = Reference.from_dict(ref.to_dict())
        assert restored.to_dict() == ref.to_dict()

    def test_finding_roundtrip(self):
        from research_cli.models.collaborative_research import Finding
        finding = Finding(
            id="f1", title="Finding 1", description="Desc",
            evidence="Evidence text", citations=[1, 2],
            author="Lead", confidence="high", timestamp="2025-01-01T00:00:00"
        )
        restored = Finding.from_dict(finding.to_dict())
        assert restored.to_dict() == finding.to_dict()

    def test_collaborative_research_notes_roundtrip(self):
        from research_cli.models.collaborative_research import (
            CollaborativeResearchNotes, Reference, Finding
        )
        notes = CollaborativeResearchNotes(
            research_questions=["RQ1"],
            hypotheses=["H1"],
            references=[
                Reference(id=1, authors=["A"], title="T", venue="V", year=2024)
            ],
            findings=[
                Finding(
                    id="f1", title="F", description="D", evidence="E",
                    citations=[1], author="lead", confidence="high",
                    timestamp="2025-01-01T00:00:00"
                )
            ],
            version=1,
        )
        d = notes.to_dict()
        restored = CollaborativeResearchNotes.from_dict(d)
        # Check core fields survived the round-trip
        assert len(restored.references) == 1
        assert restored.references[0].to_dict() == notes.references[0].to_dict()
        assert len(restored.findings) == 1
        assert restored.findings[0].to_dict() == notes.findings[0].to_dict()
        assert restored.research_questions == ["RQ1"]

    def test_author_role_roundtrip(self):
        from research_cli.models.author import AuthorRole
        author = AuthorRole(
            id="lead-1", name="Dr. Smith", role="lead",
            expertise="AI", focus_areas=["NLP", "CV"],
        )
        restored = AuthorRole.from_dict(author.to_dict())
        assert restored.to_dict() == author.to_dict()

    def test_writer_team_roundtrip(self):
        from research_cli.models.author import AuthorRole, WriterTeam
        team = WriterTeam(
            lead_author=AuthorRole(
                id="lead", name="Lead", role="lead",
                expertise="ML", focus_areas=["deep learning"]
            ),
            coauthors=[
                AuthorRole(
                    id="co1", name="Co1", role="coauthor",
                    expertise="NLP", focus_areas=["transformers"]
                )
            ]
        )
        restored = WriterTeam.from_dict(team.to_dict())
        assert restored.to_dict() == team.to_dict()


# ── 1-7. CLI Command Integrity ───────────────────────────────────────────────

class TestCLI:
    """CLI must parse arguments and show help without errors."""

    def test_cli_help(self):
        from click.testing import CliRunner
        from research_cli.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "research workflow" in result.output.lower() or "Usage" in result.output

    def test_run_help(self):
        from click.testing import CliRunner
        from research_cli.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0

    @pytest.mark.parametrize("option,values", [
        ("--article-length", ["short", "full"]),
        ("--audience-level", ["beginner", "intermediate", "professional"]),
        ("--research-type", ["explainer", "survey", "original"]),
    ])
    def test_run_option_in_help(self, option, values):
        from click.testing import CliRunner
        from research_cli.cli import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert option in result.output, f"Option '{option}' not found in run --help"
        for val in values:
            assert val in result.output, f"Value '{val}' not found in run --help for {option}"


# ── 1-8. Export Pipeline Integrity ───────────────────────────────────────────

class TestExportPipeline:
    """export_to_web.generate_article_html must be callable with sample data."""

    def test_generate_article_html_callable(self):
        from export_to_web import generate_article_html
        import inspect
        sig = inspect.signature(generate_article_html)
        params = list(sig.parameters.keys())
        assert "project_id" in params
        assert "workflow_data" in params
        assert "manuscript_text" in params

    def test_generate_article_html_with_sample_data(self):
        from export_to_web import generate_article_html
        workflow_data = {
            "topic": "Test Topic",
            "rounds": [
                {
                    "overall_average": 7.5,
                    "moderator_decision": {"decision": "ACCEPT"},
                }
            ],
            "expert_team": [
                {"name": "Expert 1"},
                {"name": "Expert 2"},
            ],
        }
        manuscript_text = (
            "# Test Article\n\n"
            "## Introduction\n\n"
            "This is a test article with citation [1].\n\n"
            "## Conclusion\n\n"
            "We conclude with [2].\n\n"
            "## References\n\n"
            "[1] Author (2024). Title. Venue.\n"
            "[2] Author (2024). Title2. Venue2.\n"
        )
        html = generate_article_html("test-project", workflow_data, manuscript_text)
        assert isinstance(html, str)
        assert len(html) > 100
        assert "Test Article" in html or "test-project" in html


# ── 2-1. Frontend Fetch URL Integrity ────────────────────────────────────────

class TestFrontendFetchURLs:
    """All fetch() calls in HTML files must reference API endpoints or existing static files.

    Catches bugs like fetching 'data/index.json' when the file doesn't exist
    and should use an API endpoint instead.
    """

    # Static paths that are legitimately dynamic (template-based, user-input, etc.)
    DYNAMIC_PATH_PATTERNS = [
        r'data/\$\{',          # data/${id}.json — dynamic per-project, generated at runtime
        r'\$\{API_BASE\}',     # ${API_BASE}/api/... — API calls (correct)
        r'\$\{encodeURI',      # URL-encoded dynamic paths
        r'/api/',              # Direct API calls
    ]

    # Known valid static paths that exist or are generated at runtime
    KNOWN_VALID_STATIC = {
        # These data/ files are generated by export_to_web.py per-project
        # and referenced with dynamic ${id} — not hardcoded
    }

    @pytest.fixture(scope="class")
    def html_files(self):
        web_dir = ROOT / "web"
        return list(web_dir.glob("*.html"))

    @pytest.fixture(scope="class")
    def all_fetches(self, html_files):
        """Extract all fetch() URLs from HTML files."""
        fetch_pattern = re.compile(r"""fetch\(\s*[`'"](.*?)[`'"]\s*[,)]""")
        results = []
        for html_file in html_files:
            content = html_file.read_text(encoding="utf-8")
            for match in fetch_pattern.finditer(content):
                url = match.group(1)
                line_num = content[:match.start()].count('\n') + 1
                results.append({
                    "file": html_file.name,
                    "line": line_num,
                    "url": url,
                })
        return results

    def test_no_hardcoded_static_data_fetches(self, all_fetches):
        """No fetch() should reference hardcoded static data/ files.

        Dynamic references like data/${id}.json are OK (per-project files).
        But hardcoded paths like 'data/index.json' must use API endpoints.
        """
        hardcoded = []
        for f in all_fetches:
            url = f["url"]
            # Skip dynamic/API URLs
            if any(re.search(p, url) for p in self.DYNAMIC_PATH_PATTERNS):
                continue
            # Flag hardcoded data/ references
            if url.startswith("data/") and "${" not in url:
                hardcoded.append(f"{f['file']}:{f['line']} → fetch('{url}')")

        assert hardcoded == [], (
            f"Hardcoded static data/ fetches found (should use API endpoints):\n"
            + "\n".join(f"  {h}" for h in hardcoded)
        )

    def test_all_api_fetches_use_api_base(self, all_fetches):
        """API fetches should use ${API_BASE}/api/ pattern, not hardcoded domains."""
        bad = []
        for f in all_fetches:
            url = f["url"]
            # Skip non-API URLs
            if not url.startswith("http") or "/api/" not in url:
                continue
            bad.append(f"{f['file']}:{f['line']} → fetch('{url}')")

        assert bad == [], (
            f"Hardcoded API URLs found (should use ${{API_BASE}}):\n"
            + "\n".join(f"  {b}" for b in bad)
        )


# ── 2-2. Frontend DOM ID Reference Integrity ─────────────────────────────────

class TestFrontendDOMReferences:
    """JavaScript getElementById() calls must reference IDs that exist in the HTML.

    Catches bugs like referencing 'step-submit' when no element with that ID exists.
    """

    @pytest.fixture(scope="class")
    def page_data(self):
        """Parse each HTML file for defined IDs and referenced IDs.

        Excludes safe getElementById calls that are guarded with null checks
        (e.g., `const el = getElementById('x'); if (el) ...`).
        """
        web_dir = ROOT / "web"
        id_def_pattern = re.compile(r'id=["\']([^"\']+)["\']')
        # Match getElementById calls
        id_ref_pattern = re.compile(r'getElementById\(["\']([^"\']+)["\']\)')
        # Detect null-guarded patterns: `const x = ...getElementById('id'); if (x)`
        safe_pattern = re.compile(
            r'(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\(["\']([^"\']+)["\']\);\s*\n\s*if\s*\(\1\)',
            re.MULTILINE,
        )

        pages = {}
        for html_file in web_dir.glob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            defined = set(id_def_pattern.findall(content))
            referenced = set(id_ref_pattern.findall(content))
            # IDs that are safely guarded with null checks — not real bugs
            safe_ids = {m.group(2) for m in safe_pattern.finditer(content)}
            pages[html_file.name] = {
                "defined": defined,
                "referenced": referenced - safe_ids,
            }
        return pages

    @pytest.mark.parametrize("page", [
        "ask-topic.html",
        "research-queue.html",
        "index.html",
        "article.html",
        "review.html",
        "submit.html",
    ])
    def test_no_orphan_id_references(self, page_data, page):
        """Every getElementById() must reference an ID defined in the same page."""
        if page not in page_data:
            pytest.skip(f"{page} not found")

        data = page_data[page]
        # IDs that are dynamically generated (template literals, loops, etc.)
        # These create IDs like "customize-panel-0", "custom-desc-1", etc.
        dynamic_prefixes = (
            "customize-panel-", "custom-desc-", "custom-content-",
            "activity-feed-", "perf-panel-",
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


# ── 2-3. Backend-Frontend Data Contract ──────────────────────────────────────

class TestBackendFrontendContract:
    """The /api/workflows response must include fields that the frontend depends on.

    Catches bugs where the backend omits fields like final_score, rounds, etc.
    that the frontend needs for display.
    """

    @pytest.fixture(scope="class")
    def scan_function(self):
        """Get the scan_interrupted_workflows function and simulate it."""
        from api_server import scan_interrupted_workflows
        return scan_interrupted_workflows

    def test_workflow_status_schema_for_completed(self):
        """Completed workflow_status entries must have all frontend-required fields."""
        pytest.importorskip("fastapi")
        import api_server

        # Required fields that the frontend (research-queue.html) accesses
        required_fields = {
            "topic", "status", "current_round", "total_rounds",
            "progress_percentage", "message", "error",
            "start_time", "elapsed_time_seconds",
            # These were missing and caused N/A scores:
            "final_score", "final_decision", "passed", "rounds",
            "category", "word_count", "total_tokens", "estimated_cost",
            "expert_team",
        }

        # Check that _build_project_summary returns all needed fields
        from api_server import _build_project_summary  # noqa: E402

        # Find a real completed workflow to test against
        results_dir = Path("results")
        sample_dir = None
        if results_dir.exists():
            for d in results_dir.iterdir():
                if d.is_dir() and (d / "workflow_complete.json").exists():
                    sample_dir = d
                    break

        if sample_dir is None:
            pytest.skip("No completed workflow found in results/")

        summary = _build_project_summary(sample_dir)
        assert summary is not None, f"_build_project_summary returned None for {sample_dir.name}"

        missing = required_fields - {"error", "expert_status", "cost_estimate"} - set(summary.keys())
        # Map field names (summary uses 'id' not 'project_id', etc.)
        field_mapping = {"topic", "status", "total_rounds", "rounds",
                         "final_score", "final_decision", "passed",
                         "category", "word_count", "total_tokens",
                         "estimated_cost", "expert_team", "elapsed_time_seconds",
                         "start_time"}
        missing_important = field_mapping - set(summary.keys())
        assert missing_important == set(), (
            f"_build_project_summary missing fields needed by frontend:\n"
            + "\n".join(f"  {f}" for f in sorted(missing_important))
        )

    def test_completed_workflow_status_has_required_fields(self):
        """Simulate startup scan and verify completed entries have required fields."""
        results_dir = Path("results")
        if not results_dir.exists():
            pytest.skip("No results directory")

        sample_file = None
        for d in results_dir.iterdir():
            wf = d / "workflow_complete.json"
            if wf.exists():
                sample_file = wf
                break

        if not sample_file:
            pytest.skip("No completed workflow found")

        with open(sample_file) as f:
            wf_data = json.load(f)

        # Simulate the restoration logic from scan_interrupted_workflows
        passed = wf_data.get("passed", False)
        final_score = wf_data.get("final_score", 0)
        raw_rounds = wf_data.get("rounds", [])

        # Verify the source data has what we need
        assert "passed" in wf_data, "workflow_complete.json missing 'passed'"
        assert "rounds" in wf_data, "workflow_complete.json missing 'rounds'"

        if raw_rounds:
            last_round = raw_rounds[-1]
            assert "overall_average" in last_round, "Round missing 'overall_average'"
            assert "moderator_decision" in last_round, "Round missing 'moderator_decision'"
            decision = last_round["moderator_decision"]
            assert "decision" in decision, "moderator_decision missing 'decision'"

    def test_workflow_status_fields_match_frontend_expectations(self):
        """Fields accessed by research-queue.html JS must exist in workflow_status.

        Parses the JS for wf.FIELD accesses and cross-checks against the
        schema built by scan_interrupted_workflows for completed workflows.
        """
        queue_html = ROOT / "web" / "research-queue.html"
        if not queue_html.exists():
            pytest.skip("research-queue.html not found")

        content = queue_html.read_text(encoding="utf-8")

        # Extract wf.FIELD accesses from JS (e.g., wf.final_score, wf.rounds)
        wf_field_pattern = re.compile(r'\bwf\.(\w+)')
        accessed_fields = set(wf_field_pattern.findall(content))

        # Fields that the /api/workflows endpoint should provide for completed workflows
        # (built by scan_interrupted_workflows or returned as workflow_status dict)
        provided_by_api_workflows = {
            "project_id", "topic", "status", "current_round", "total_rounds",
            "progress_percentage", "message", "error", "error_stage",
            "expert_status", "cost_estimate", "start_time", "elapsed_time_seconds",
            "estimated_time_remaining_seconds", "research_type",
            "final_score", "final_decision", "passed", "rounds",
            "category", "word_count", "total_tokens", "estimated_cost",
            "expert_team", "can_resume",
        }

        # Fields that come from /api/projects merge (line 1931-1971 in research-queue.html)
        provided_by_api_projects = {
            "id", "title", "final_score", "final_decision", "passed",
            "rounds", "total_rounds", "topic", "category",
            "elapsed_time_seconds", "total_tokens", "estimated_cost",
            "expert_team", "status", "start_time", "data_file",
            "word_count", "research_type", "audience_level",
        }

        all_provided = provided_by_api_workflows | provided_by_api_projects

        # Fields that are JS methods/properties, not data fields
        js_builtins = {
            "status", "message", "length", "map", "filter", "find",
            "forEach", "push", "includes", "join", "slice", "sort",
            "toFixed", "toLocaleString", "toString", "replace",
            "startsWith", "endsWith", "trim",
        }

        missing = accessed_fields - all_provided - js_builtins
        # Filter out obviously non-data accesses
        missing = {f for f in missing if not f.startswith("_") and f.islower()}

        assert missing == set(), (
            f"research-queue.html accesses wf.FIELD not provided by API:\n"
            + "\n".join(f"  wf.{f}" for f in sorted(missing))
        )
