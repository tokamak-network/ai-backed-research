"""Performance tracking for AI research workflow."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager


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

    # Per round metrics
    rounds: List[RoundMetrics] = field(default_factory=list)

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
            "rounds": [r.to_dict() for r in self.rounds],
            "total_tokens": self.total_tokens,
            "estimated_cost": round(self.estimated_cost, 2)
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

    def record_initial_draft(self, duration: float, tokens: int = 0):
        """Record initial draft generation metrics.

        Args:
            duration: Time taken in seconds
            tokens: Tokens used
        """
        self._initial_draft_time = duration
        self._initial_draft_tokens = tokens

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

    def export_metrics(self) -> PerformanceMetrics:
        """Generate final performance metrics.

        Returns:
            Complete performance metrics
        """
        if self._workflow_start is None:
            raise ValueError("Workflow not started")

        workflow_end = time.time()
        total_duration = workflow_end - self._workflow_start

        # Calculate total tokens
        total_tokens = (
            self._initial_draft_tokens +
            self._team_composition_tokens +
            sum(r.round_tokens for r in self._rounds)
        )

        # Estimate cost (rough approximation)
        # Assuming mixed usage of Claude Sonnet/Opus
        estimated_cost = (total_tokens / 1000) * 0.003

        return PerformanceMetrics(
            workflow_start=datetime.fromtimestamp(self._workflow_start).isoformat(),
            workflow_end=datetime.fromtimestamp(workflow_end).isoformat(),
            total_duration=total_duration,
            initial_draft_time=self._initial_draft_time,
            initial_draft_tokens=self._initial_draft_tokens,
            team_composition_time=self._team_composition_time,
            team_composition_tokens=self._team_composition_tokens,
            rounds=self._rounds,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost
        )
