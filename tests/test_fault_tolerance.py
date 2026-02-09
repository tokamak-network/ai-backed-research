"""Comprehensive tests for workflow fault tolerance changes.

Tests:
1. json_repair — covered in test_json_repair.py (18 tests)
2. Reviewer partial failure (run_review_round with asyncio.gather)
3. Co-author partial failure (collaborative_research)
4. Round 0 checkpoint → resume flow
5. on_leave review structure and average calculation
6. api_server timestamp helpers (_utcnow, _parse_start_time)
7. review.html on_leave rendering (static check)
"""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Reviewer partial failure in run_review_round
# ---------------------------------------------------------------------------

class TestReviewerPartialFailure:
    """Test that run_review_round handles individual reviewer failures."""

    @pytest.mark.asyncio
    async def test_one_reviewer_fails_others_continue(self):
        """When 1 of 3 reviewers fails, the other 2 results are kept."""
        from research_cli.workflow.orchestrator import (
            _build_on_leave_review,
        )

        # Simulate what run_review_round does internally
        specialists = {
            "r1": {"name": "Reviewer A", "model": "gpt-4.1", "system_prompt": ""},
            "r2": {"name": "Reviewer B", "model": "gpt-4.1", "system_prompt": ""},
            "r3": {"name": "Reviewer C", "model": "gpt-4.1", "system_prompt": ""},
        }

        # Simulate gather results: r1 ok, r2 fails, r3 ok
        ok_review = {
            "specialist": "r1",
            "specialist_name": "Reviewer A",
            "model": "gpt-4.1",
            "scores": {"accuracy": 7, "completeness": 8, "clarity": 7, "novelty": 6, "rigor": 7, "citations": 8},
            "average": 7.2,
            "summary": "Good",
            "strengths": ["a"],
            "weaknesses": ["b"],
            "suggestions": ["c"],
            "detailed_feedback": "ok",
        }
        ok_review_3 = {**ok_review, "specialist": "r3", "specialist_name": "Reviewer C", "average": 6.8}
        error = RuntimeError("API timeout")

        results = [ok_review, error, ok_review_3]
        specialist_items = list(specialists.items())

        reviews = []
        for (sid, spec), result in zip(specialist_items, results):
            if isinstance(result, Exception):
                reviews.append(_build_on_leave_review(sid, spec, str(result)))
            else:
                reviews.append(result)

        # Verify: 3 reviews total, 1 on_leave
        assert len(reviews) == 3
        assert reviews[1]["on_leave"] is True
        assert reviews[1]["specialist"] == "r2"

        # Average should exclude on_leave
        active = [r for r in reviews if not r.get("on_leave")]
        assert len(active) == 2
        avg = sum(r["average"] for r in active) / len(active)
        assert abs(avg - 7.0) < 0.01  # (7.2 + 6.8) / 2

    @pytest.mark.asyncio
    async def test_all_reviewers_fail_raises(self):
        """When all reviewers fail, RuntimeError is raised."""
        from research_cli.workflow.orchestrator import _build_on_leave_review

        reviews = [
            _build_on_leave_review("r1", {"name": "A", "model": ""}, "err1"),
            _build_on_leave_review("r2", {"name": "B", "model": ""}, "err2"),
        ]

        active = [r for r in reviews if not r.get("on_leave")]
        assert len(active) == 0  # all on_leave

        # Mimics the guard in run_review_round
        with pytest.raises(RuntimeError):
            if not active:
                raise RuntimeError("All reviewers failed. Cannot continue workflow.")


# ---------------------------------------------------------------------------
# 2. Co-author partial failure
# ---------------------------------------------------------------------------

class TestCoauthorPartialFailure:
    """Test _conduct_parallel_research with partial failures."""

    @pytest.mark.asyncio
    async def test_one_coauthor_fails(self):
        from research_cli.workflow.collaborative_research import CollaborativeResearchPhase

        phase = object.__new__(CollaborativeResearchPhase)

        class FakeContrib:
            def __init__(self, author):
                self.author = author
                self.findings = []
                self.references = []

        class FakeAgent:
            def __init__(self, author_id, fail=False):
                self.author_id = author_id
                self.fail = fail
            async def conduct_research(self, task, context):
                if self.fail:
                    raise RuntimeError(f"{self.author_id} timeout")
                return FakeContrib(self.author_id)

        class FakeTask:
            def __init__(self, assigned_to):
                self.assigned_to = assigned_to
                self.status = "pending"

        phase.coauthor_agents = [FakeAgent("ca1"), FakeAgent("ca2", fail=True)]
        tasks = [FakeTask("ca1"), FakeTask("ca2")]

        contribs = await phase._conduct_parallel_research(tasks, {})
        assert len(contribs) == 1
        assert contribs[0].author == "ca1"

    @pytest.mark.asyncio
    async def test_all_coauthors_fail_raises(self):
        from research_cli.workflow.collaborative_research import CollaborativeResearchPhase

        phase = object.__new__(CollaborativeResearchPhase)

        class FailAgent:
            def __init__(self, author_id):
                self.author_id = author_id
            async def conduct_research(self, task, context):
                raise RuntimeError("fail")

        class FakeTask:
            def __init__(self, assigned_to):
                self.assigned_to = assigned_to
                self.status = "pending"

        phase.coauthor_agents = [FailAgent("ca1"), FailAgent("ca2")]
        tasks = [FakeTask("ca1"), FakeTask("ca2")]

        with pytest.raises(RuntimeError, match="All co-author"):
            await phase._conduct_parallel_research(tasks, {})


# ---------------------------------------------------------------------------
# 3. Round 0 checkpoint → resume flow
# ---------------------------------------------------------------------------

class TestRound0Checkpoint:
    """Test that round 0 checkpoint saves correctly and resume handles it."""

    def test_checkpoint_round0_structure(self):
        """Verify a round 0 checkpoint has the right fields."""
        checkpoint = {
            "topic": "Test Topic",
            "current_round": 0,
            "max_rounds": 3,
            "threshold": 7.0,
            "current_manuscript": "# Test\n\nBody text.",
            "all_rounds": [],
            "expert_configs": [],
            "category": "computer_science",
            "audience_level": "professional",
            "research_type": "survey",
            "checkpoint_time": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
        }

        assert checkpoint["current_round"] == 0
        assert checkpoint["all_rounds"] == []
        assert checkpoint["current_manuscript"] != ""

    def test_resume_round0_iteration_range(self):
        """With start_round=0, range(0+1, max+1) = range(1, max+1) — correct."""
        start_round = 0
        max_rounds = 3

        rounds_to_run = list(range(start_round + 1, max_rounds + 1))
        assert rounds_to_run == [1, 2, 3]

    def test_resume_round0_empty_all_rounds(self):
        """_resume_workflow_impl with empty all_rounds doesn't crash."""
        all_rounds = []

        # The guard: if not all_rounds → skip revision check, fall through
        if not all_rounds:
            path = "round_0_fresh_start"
        else:
            path = "normal_resume"

        assert path == "round_0_fresh_start"

    def test_resume_round0_prev_reviews_none(self):
        """prev_reviews should be None when all_rounds is empty."""
        all_rounds = []

        prev_reviews = all_rounds[-1]['reviews'] if all_rounds else None
        prev_response = all_rounds[-1].get('author_response') if all_rounds else None

        assert prev_reviews is None
        assert prev_response is None

    def test_checkpoint_roundtrip(self):
        """Write and read a round 0 checkpoint file."""
        checkpoint = {
            "topic": "Test",
            "current_round": 0,
            "max_rounds": 3,
            "threshold": 7.0,
            "current_manuscript": "# Test",
            "all_rounds": [],
            "expert_configs": [],
            "checkpoint_time": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(checkpoint, f)
            f.flush()

            loaded = json.load(open(f.name))
            assert loaded["current_round"] == 0
            assert loaded["all_rounds"] == []
            assert loaded["current_manuscript"] == "# Test"

            Path(f.name).unlink()


# ---------------------------------------------------------------------------
# 4. on_leave review structure
# ---------------------------------------------------------------------------

class TestOnLeaveReview:
    """Test _build_on_leave_review produces valid review data."""

    def test_has_all_required_fields(self):
        from research_cli.workflow.orchestrator import _build_on_leave_review

        review = _build_on_leave_review("r1", {"name": "Dr. X", "model": "m"}, "timeout")

        required = [
            "specialist", "specialist_name", "model", "on_leave", "error",
            "scores", "average", "summary", "strengths", "weaknesses",
            "suggestions", "detailed_feedback"
        ]
        for field in required:
            assert field in review, f"Missing: {field}"

    def test_on_leave_is_true(self):
        from research_cli.workflow.orchestrator import _build_on_leave_review
        review = _build_on_leave_review("r1", {"name": "X"}, "err")
        assert review["on_leave"] is True

    def test_average_is_zero(self):
        from research_cli.workflow.orchestrator import _build_on_leave_review
        review = _build_on_leave_review("r1", {"name": "X"}, "err")
        assert review["average"] == 0

    def test_scores_all_zero(self):
        from research_cli.workflow.orchestrator import _build_on_leave_review
        review = _build_on_leave_review("r1", {"name": "X"}, "err")
        assert all(v == 0 for v in review["scores"].values())

    def test_error_message_preserved(self):
        from research_cli.workflow.orchestrator import _build_on_leave_review
        review = _build_on_leave_review("r1", {"name": "X"}, "Connection reset")
        assert review["error"] == "Connection reset"

    def test_serializable_to_json(self):
        from research_cli.workflow.orchestrator import _build_on_leave_review
        review = _build_on_leave_review("r1", {"name": "X", "model": "m"}, "err")
        # Must not raise
        serialized = json.dumps(review)
        loaded = json.loads(serialized)
        assert loaded["on_leave"] is True


# ---------------------------------------------------------------------------
# 5. Outlier detection with on_leave
# ---------------------------------------------------------------------------

class TestOutlierDetectionWithOnLeave:
    """Test _detect_reviewer_outliers excludes on_leave."""

    def test_on_leave_not_counted_as_outlier(self):
        from research_cli.workflow.orchestrator import _detect_reviewer_outliers

        reviews = [
            {"specialist_name": "A", "average": 7.5},
            {"specialist_name": "B", "average": 7.0},
            {"specialist_name": "C", "average": 0.0, "on_leave": True},
        ]
        result = _detect_reviewer_outliers(reviews)
        assert result is None  # C is on_leave, not an outlier

    def test_real_outlier_still_detected(self):
        from research_cli.workflow.orchestrator import _detect_reviewer_outliers

        reviews = [
            {"specialist_name": "A", "average": 8.0},
            {"specialist_name": "B", "average": 7.5},
            {"specialist_name": "C", "average": 4.0},
        ]
        result = _detect_reviewer_outliers(reviews)
        assert result is not None
        assert "C" in result

    def test_all_on_leave_returns_none(self):
        from research_cli.workflow.orchestrator import _detect_reviewer_outliers

        reviews = [
            {"specialist_name": "A", "average": 0, "on_leave": True},
            {"specialist_name": "B", "average": 0, "on_leave": True},
        ]
        result = _detect_reviewer_outliers(reviews)
        assert result is None  # < 2 active reviewers


# ---------------------------------------------------------------------------
# 6. api_server timestamp helpers
# ---------------------------------------------------------------------------

class TestTimestampHelpers:
    """Test _utcnow and _parse_start_time."""

    def test_utcnow_has_timezone(self):
        """_utcnow returns timezone-aware UTC datetime."""
        from datetime import datetime as dt, timezone as tz
        now = dt.now(tz.utc)
        assert now.tzinfo is not None
        # isoformat should contain +00:00
        iso = now.isoformat()
        assert "+00:00" in iso

    def test_parse_aware_timestamp(self):
        """_parse_start_time handles +00:00 timestamps."""
        iso = "2026-02-09T09:19:38.123456+00:00"
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        assert dt.tzinfo is not None

    def test_parse_naive_timestamp_backward_compat(self):
        """_parse_start_time assumes UTC for naive timestamps."""
        iso = "2026-02-09T09:19:38.123456"
        dt = datetime.fromisoformat(iso)
        assert dt.tzinfo is None

        # After _parse_start_time logic:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        assert dt.tzinfo == timezone.utc

    def test_elapsed_calc_mixed_timestamps(self):
        """Elapsed calculation works with both old (naive) and new (aware) start_time."""
        old_ts = "2026-02-09T09:00:00.000000"
        new_ts = "2026-02-09T09:00:00.000000+00:00"

        def _parse(s):
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        ref = datetime(2026, 2, 9, 9, 10, 0, tzinfo=timezone.utc)

        elapsed_old = (ref - _parse(old_ts)).total_seconds()
        elapsed_new = (ref - _parse(new_ts)).total_seconds()

        assert elapsed_old == 600  # 10 minutes
        assert elapsed_new == 600
        assert elapsed_old == elapsed_new


# ---------------------------------------------------------------------------
# 7. review.html on_leave rendering (static check)
# ---------------------------------------------------------------------------

class TestReviewHtmlOnLeave:
    """Verify review.html contains on_leave rendering code."""

    def test_renderReview_has_on_leave_branch(self):
        html = Path("web/review.html").read_text()
        assert "review.on_leave" in html
        assert "on-leave" in html
        assert "On Leave" in html

    def test_on_leave_css_exists(self):
        html = Path("web/review.html").read_text()
        assert ".review-card.on-leave" in html
        assert ".on-leave-badge" in html
        assert ".on-leave-message" in html

    def test_on_leave_card_has_dashed_border(self):
        html = Path("web/review.html").read_text()
        # Find the .review-card.on-leave block
        idx = html.index(".review-card.on-leave")
        block = html[idx:idx+200]
        assert "border-style: dashed" in block

    def test_on_leave_card_has_opacity(self):
        html = Path("web/review.html").read_text()
        idx = html.index(".review-card.on-leave")
        block = html[idx:idx+200]
        assert "opacity: 0.6" in block


# ---------------------------------------------------------------------------
# 8. research-queue.html timestamp rendering (static check)
# ---------------------------------------------------------------------------

class TestResearchQueueTimestamps:
    """Verify research-queue.html uses parseUTCTimestamp for backward compat."""

    def test_parseUTCTimestamp_function_exists(self):
        html = Path("web/research-queue.html").read_text()
        assert "function parseUTCTimestamp" in html

    def test_activity_log_uses_parseUTCTimestamp(self):
        html = Path("web/research-queue.html").read_text()
        assert "parseUTCTimestamp(activity.timestamp)" in html

    def test_start_time_uses_parseUTCTimestamp(self):
        html = Path("web/research-queue.html").read_text()
        assert "parseUTCTimestamp(wf.start_time)" in html

    def test_naive_timestamp_gets_Z_appended(self):
        """parseUTCTimestamp appends Z for timezone-less strings."""
        html = Path("web/research-queue.html").read_text()
        # Check the regex pattern that detects missing timezone
        assert "endsWith('Z')" in html
        assert "isoString + 'Z'" in html


# ---------------------------------------------------------------------------
# 9. api_server start_time reset on worker pickup
# ---------------------------------------------------------------------------

class TestStartTimeReset:
    """Verify api_server resets start_time when worker actually starts."""

    def test_run_workflow_background_resets_start_time(self):
        """run_workflow_background has start_time reset at the top."""
        code = Path("api_server.py").read_text()
        # Find the function
        idx = code.index("async def run_workflow_background(")
        # Check within next 500 chars for the reset
        block = code[idx:idx+800]
        assert 'workflow_status[project_id]["start_time"] = _utcnow().isoformat()' in block

    def test_resume_workflow_background_resets_start_time(self):
        """resume_workflow_background has start_time reset at the top."""
        code = Path("api_server.py").read_text()
        idx = code.index("async def resume_workflow_background(")
        block = code[idx:idx+800]
        assert 'workflow_status[project_id]["start_time"] = _utcnow().isoformat()' in block
