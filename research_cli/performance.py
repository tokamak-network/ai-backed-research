"""Performance tracking for AI research workflow."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

# Model pricing per 1M tokens (USD)
MODEL_PRICING = {
    "claude-opus-4-5": {"input": 15.0, "output": 75.0},
    "claude-opus-4.5": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4.5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}
# Fallback for unknown models
_DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


@dataclass
class RoundMetrics:
    """Performance metrics for a single review round."""
    round_number: int
    review_start: str  # ISO format datetime
    review_end: str  # ISO format datetime
    review_duration: float  # seconds

    # Per reviewer timing
    reviewer_times: Dict[str, float] = field(default_factory=dict)

    # Moderator timing
    moderator_time: float = 0.0

    # Revision timing (if applicable)
    revision_time: Optional[float] = None

    # Token usage
    round_tokens: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "round_number": self.round_number,
            "review_start": self.review_start,
            "review_end": self.review_end,
            "review_duration": round(self.review_duration, 2),
            "reviewer_times": {k: round(v, 2) for k, v in self.reviewer_times.items()},
            "moderator_time": round(self.moderator_time, 2),
            "revision_time": round(self.revision_time, 2) if self.revision_time else None,
            "round_tokens": self.round_tokens
        }


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for the workflow."""
    # Workflow start/end
    workflow_start: str  # ISO format datetime
    workflow_end: str  # ISO format datetime
    total_duration: float  # seconds

    # Initial draft
    initial_draft_time: float = 0.0
    initial_draft_tokens: int = 0

    # Team composition
    team_composition_time: float = 0.0
    team_composition_tokens: int = 0

    # Writer-side token tracking (previously missing)
    citation_tokens: int = 0
    revision_tokens: int = 0
    author_response_tokens: int = 0
    desk_editor_tokens: int = 0
    moderator_tokens: int = 0

    # Per round metrics
    rounds: List[RoundMetrics] = field(default_factory=list)

    # Model-level breakdown
    tokens_by_model: Dict[str, dict] = field(default_factory=dict)

    # Totals
    total_tokens: int = 0
    estimated_cost: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "workflow_start": self.workflow_start,
            "workflow_end": self.workflow_end,
            "total_duration": round(self.total_duration, 2),
            "initial_draft_time": round(self.initial_draft_time, 2),
            "initial_draft_tokens": self.initial_draft_tokens,
            "team_composition_time": round(self.team_composition_time, 2),
            "team_composition_tokens": self.team_composition_tokens,
            "citation_tokens": self.citation_tokens,
            "revision_tokens": self.revision_tokens,
            "author_response_tokens": self.author_response_tokens,
            "desk_editor_tokens": self.desk_editor_tokens,
            "moderator_tokens": self.moderator_tokens,
            "rounds": [r.to_dict() for r in self.rounds],
            "tokens_by_model": self.tokens_by_model,
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 4)
        }


class PerformanceTracker:
    """Tracks performance metrics for the research workflow."""

    def __init__(self):
        """Initialize performance tracker."""
        self._timers: Dict[str, float] = {}
        self._workflow_start: Optional[float] = None
        self._current_round: Optional[RoundMetrics] = None
        self._rounds: List[RoundMetrics] = []
        self._initial_draft_time: float = 0.0
        self._initial_draft_tokens: int = 0
        self._team_composition_time: float = 0.0
        self._team_composition_tokens: int = 0

        # New cumulative token fields
        self._citation_tokens: int = 0
        self._revision_tokens: int = 0
        self._author_response_tokens: int = 0
        self._desk_editor_tokens: int = 0
        self._moderator_tokens: int = 0

        # Model-level input/output tracking for accurate cost calculation
        self._tokens_by_model: Dict[str, dict] = {}

    def _track_model_tokens(self, model: str, input_tokens: int, output_tokens: int):
        """Track input/output tokens per model for cost calculation."""
        if not model:
            return
        if model not in self._tokens_by_model:
            self._tokens_by_model[model] = {"input": 0, "output": 0}
        self._tokens_by_model[model]["input"] += input_tokens
        self._tokens_by_model[model]["output"] += output_tokens

    def start_workflow(self):
        """Start tracking the entire workflow."""
        self._workflow_start = time.time()

    def start_operation(self, name: str):
        """Start timing an operation.

        Args:
            name: Name of the operation
        """
        self._timers[name] = time.time()

    def end_operation(self, name: str) -> float:
        """End timing an operation.

        Args:
            name: Name of the operation

        Returns:
            Duration in seconds
        """
        if name not in self._timers:
            return 0.0

        duration = time.time() - self._timers[name]
        del self._timers[name]
        return duration

    @contextmanager
    def track_operation(self, name: str):
        """Context manager for tracking an operation.

        Usage:
            with tracker.track_operation("review"):
                # do work
                pass
        """
        self.start_operation(name)
        try:
            yield
        finally:
            duration = self.end_operation(name)

    def record_team_composition(self, duration: float, tokens: int = 0):
        """Record team composition metrics.

        Args:
            duration: Time taken in seconds
            tokens: Tokens used
        """
        self._team_composition_time = duration
        self._team_composition_tokens = tokens

    def record_initial_draft(self, duration: float, tokens: int = 0,
                             input_tokens: int = 0, output_tokens: int = 0,
                             model: str = ""):
        """Record initial draft generation metrics.

        Args:
            duration: Time taken in seconds
            tokens: Total tokens used
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            model: Model identifier
        """
        self._initial_draft_time = duration
        self._initial_draft_tokens = tokens
        self._track_model_tokens(model, input_tokens, output_tokens)

    def record_citation_verification(self, tokens: int = 0,
                                     input_tokens: int = 0,
                                     output_tokens: int = 0,
                                     model: str = ""):
        """Record citation verification token usage."""
        self._citation_tokens += tokens
        self._track_model_tokens(model, input_tokens, output_tokens)

    def record_revision(self, tokens: int = 0,
                        input_tokens: int = 0, output_tokens: int = 0,
                        model: str = ""):
        """Record manuscript revision token usage."""
        self._revision_tokens += tokens
        self._track_model_tokens(model, input_tokens, output_tokens)

    def record_author_response(self, tokens: int = 0,
                               input_tokens: int = 0,
                               output_tokens: int = 0,
                               model: str = ""):
        """Record author response token usage."""
        self._author_response_tokens += tokens
        self._track_model_tokens(model, input_tokens, output_tokens)

    def record_desk_editor(self, tokens: int = 0,
                           input_tokens: int = 0,
                           output_tokens: int = 0,
                           model: str = ""):
        """Record desk editor screening token usage."""
        self._desk_editor_tokens += tokens
        self._track_model_tokens(model, input_tokens, output_tokens)

    def record_moderator(self, tokens: int = 0,
                         input_tokens: int = 0,
                         output_tokens: int = 0,
                         model: str = ""):
        """Record moderator decision token usage."""
        self._moderator_tokens += tokens
        self._track_model_tokens(model, input_tokens, output_tokens)

    def start_round(self, round_number: int):
        """Start tracking a review round.

        Args:
            round_number: Round number
        """
        self._current_round = RoundMetrics(
            round_number=round_number,
            review_start=datetime.now().isoformat(),
            review_end="",
            review_duration=0.0
        )
        self.start_operation(f"round_{round_number}")

    def record_reviewer_time(self, reviewer_id: str, duration: float):
        """Record time for a specific reviewer.

        Args:
            reviewer_id: Reviewer identifier
            duration: Time taken in seconds
        """
        if self._current_round:
            self._current_round.reviewer_times[reviewer_id] = duration

    def record_moderator_time(self, duration: float):
        """Record moderator decision time.

        Args:
            duration: Time taken in seconds
        """
        if self._current_round:
            self._current_round.moderator_time = duration

    def record_revision_time(self, duration: float):
        """Record manuscript revision time.

        Args:
            duration: Time taken in seconds
        """
        if self._current_round:
            self._current_round.revision_time = duration

    def record_round_tokens(self, tokens: int):
        """Record tokens used in current round.

        Args:
            tokens: Token count
        """
        if self._current_round:
            self._current_round.round_tokens = tokens

    def end_round(self):
        """Finish tracking current round."""
        if self._current_round:
            round_num = self._current_round.round_number
            duration = self.end_operation(f"round_{round_num}")
            self._current_round.review_duration = duration
            self._current_round.review_end = datetime.now().isoformat()
            self._rounds.append(self._current_round)
            self._current_round = None

    def _calculate_cost(self) -> float:
        """Calculate estimated cost from model-level token tracking."""
        total_cost = 0.0
        for model, usage in self._tokens_by_model.items():
            pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
            input_cost = (usage["input"] / 1_000_000) * pricing["input"]
            output_cost = (usage["output"] / 1_000_000) * pricing["output"]
            total_cost += input_cost + output_cost
        return total_cost

    def export_metrics(self) -> PerformanceMetrics:
        """Generate final performance metrics.

        Returns:
            Complete performance metrics
        """
        if self._workflow_start is None:
            raise ValueError("Workflow not started")

        workflow_end = time.time()
        total_duration = workflow_end - self._workflow_start

        # Calculate total tokens from all sources
        total_tokens = (
            self._initial_draft_tokens +
            self._team_composition_tokens +
            self._citation_tokens +
            self._revision_tokens +
            self._author_response_tokens +
            self._desk_editor_tokens +
            self._moderator_tokens +
            sum(r.round_tokens for r in self._rounds)
        )

        # Calculate cost from model-level breakdown (accurate)
        # Fall back to flat rate if no model data
        if self._tokens_by_model:
            estimated_cost = self._calculate_cost()
        else:
            estimated_cost = (total_tokens / 1_000_000) * 3.0  # fallback $3/M

        return PerformanceMetrics(
            workflow_start=datetime.fromtimestamp(self._workflow_start).isoformat(),
            workflow_end=datetime.fromtimestamp(workflow_end).isoformat(),
            total_duration=total_duration,
            initial_draft_time=self._initial_draft_time,
            initial_draft_tokens=self._initial_draft_tokens,
            team_composition_time=self._team_composition_time,
            team_composition_tokens=self._team_composition_tokens,
            citation_tokens=self._citation_tokens,
            revision_tokens=self._revision_tokens,
            author_response_tokens=self._author_response_tokens,
            desk_editor_tokens=self._desk_editor_tokens,
            moderator_tokens=self._moderator_tokens,
            rounds=self._rounds,
            tokens_by_model=self._tokens_by_model,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost
        )
