"""Full iterative peer review workflow orchestrator with dynamic teams."""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ..model_config import _create_llm
from ..utils.json_repair import repair_json
from ..agents import WriterAgent, ModeratorAgent
from ..agents.writer import validate_manuscript_completeness
from ..agents.desk_editor import DeskEditorAgent
from ..agents.specialist_factory import SpecialistFactory
from ..categories import get_domain_description
from ..models.expert import ExpertConfig
from ..models.collaborative_research import Reference
from ..performance import PerformanceTracker
from ..utils.source_retriever import SourceRetriever

console = Console()


async def generate_review(
    specialist_id: str,
    specialist: dict,
    manuscript: str,
    round_number: int,
    tracker: PerformanceTracker,
    previous_reviews: Optional[List[dict]] = None,
    previous_manuscript: Optional[str] = None,
    author_response: Optional[str] = None,
    article_length: str = "full",
    audience_level: str = "professional",
    research_type: str = "survey",
) -> dict:
    """Generate review from a specialist.

    Args:
        specialist_id: Specialist identifier
        specialist: Specialist definition dict
        manuscript: Manuscript to review
        round_number: Current round number
        tracker: Performance tracker
        previous_reviews: Reviews from previous round
        previous_manuscript: Manuscript from previous round
        author_response: Author's response to previous reviews
        article_length: "full" or "short" — adjusts reviewer expectations
        audience_level: "beginner", "intermediate", or "professional"
        research_type: "survey" or "research" — adjusts review criteria

    Returns:
        Review data dictionary
    """
    provider = specialist["provider"]
    model = specialist["model"]

    llm = _create_llm(provider, model)

    # Build context from previous reviews
    previous_context = ""
    if round_number > 1 and previous_reviews:
        # Find this specialist's previous review
        my_previous_review = next((r for r in previous_reviews if r.get("specialist") == specialist_id), None)

        if my_previous_review:
            previous_context = f"""
YOUR PREVIOUS REVIEW (Round {round_number-1}):
Summary: {my_previous_review.get('summary', 'N/A')}

Your Previous Weaknesses Identified:
{chr(10).join(f"- {w}" for w in my_previous_review.get('weaknesses', []))}

Your Previous Suggestions:
{chr(10).join(f"- {s}" for s in my_previous_review.get('suggestions', []))}

IMPORTANT: Check if the issues you identified in Round {round_number-1} have been adequately addressed in this revision.
Focus especially on whether your specific suggestions were implemented.

---
"""

    # Add author response context if available
    response_context = ""
    if author_response:
        response_context = f"""
AUTHOR RESPONSE TO PREVIOUS REVIEWS:

The authors have responded to reviewer feedback. Read their response carefully to understand:
- What changes they made
- Their rationale for decisions
- Clarifications of misunderstandings

{author_response}

---

IMPORTANT: Consider the author's response when evaluating this revision:
- Did they address your concerns adequately?
- Are their explanations/disagreements reasonable?
- Does the revised manuscript reflect their stated changes?
- Give credit for genuine engagement with feedback

---
"""

    # Short paper context
    short_paper_note = ""
    if article_length == "short":
        short_paper_note = """NOTE: This is a SHORT PAPER (1,500-2,500 words). Adjust your expectations accordingly:
- Narrower scope is expected; do not penalize for limited breadth
- Evaluate conciseness positively — reward focused, efficient argumentation
- Fewer citations are acceptable if the core claims are well-supported
- A single key contribution explored in depth is sufficient

"""

    # Audience level context
    audience_note = ""
    if audience_level == "beginner":
        audience_note = """NOTE: This manuscript targets a BEGINNER audience (non-experts). Evaluate accordingly:
- Technical terms should be explained on first use
- Analogies and examples should make complex concepts accessible
- Content should progress from simple to complex
- Penalize unnecessary jargon; reward clear, accessible explanations
- Assess whether a non-specialist reader could understand the key points

"""
    elif audience_level == "intermediate":
        audience_note = """NOTE: This manuscript targets an INTERMEDIATE audience (basic domain knowledge assumed). Evaluate accordingly:
- Fundamental concepts can be assumed without explanation
- Advanced or specialized terms should still be explained
- Balance between theoretical depth and practical applicability
- Assess whether someone with basic knowledge could follow the advanced arguments

"""

    # Research type context
    research_type_note = ""
    if research_type == "survey":
        research_type_note = """NOTE: This is a SURVEY / LITERATURE REVIEW paper. Evaluate accordingly:
- Breadth of coverage: Does it comprehensively cover the field?
- Taxonomy/categorization: Are the surveyed works well-organized?
- Gap identification: Does it clearly identify research gaps and future directions?
- Do NOT penalize for lack of novel experimental results
- Do NOT expect original hypotheses or experimental methodology
- Evaluate the quality of synthesis, comparison, and critical analysis of existing work

"""
    elif research_type == "explainer":
        research_type_note = """NOTE: This is an EXPLAINER / TUTORIAL article. Evaluate accordingly:
- Clarity: Are concepts explained in an understandable way?
- Examples: Are there enough real-world examples and analogies?
- Progression: Does the content build from simple to complex?
- Accuracy: Are the explanations technically correct (even if simplified)?
- Do NOT penalize for lack of novel research or comprehensive literature coverage
- Do NOT expect formal proofs, experimental results, or exhaustive citations
- Evaluate the quality of pedagogy: would the target audience learn from this?
- For the "novelty" score, interpret as: how fresh/unique is the explanation approach?

"""

    review_prompt = f"""Review this research manuscript (Round {round_number}) from your expert perspective.

{short_paper_note}{audience_note}{research_type_note}{previous_context}
{response_context}
MANUSCRIPT:
{manuscript}

---

Provide your review in the following JSON format:

{{
  "scores": {{
    "accuracy": <1-10>,
    "completeness": <1-10>,
    "clarity": <1-10>,
    "novelty": <1-10>,
    "rigor": <1-10>,
    "citations": <1-10>
  }},
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "suggestions": ["<suggestion 1>", "<suggestion 2>", "<suggestion 3>"],
  "detailed_feedback": "<paragraph of detailed feedback from your domain expertise>"
}}

Scoring guide:
- 9-10: Exceptional, publication-ready
- 7-8: Strong, minor improvements needed
- 5-6: Adequate, significant improvements needed
- 3-4: Weak, major revisions required
- 1-2: Poor, fundamental issues

Citations scoring guide:
- 9-10: All major claims properly cited with verifiable references
- 7-8: Most claims cited, references are real and checkable
- 5-6: Some citations present but gaps exist, or some references look dubious
- 3-4: Few citations, many unsupported claims
- 1-2: No citations or clearly fabricated references

Penalize: unsupported claims, unverifiable references, hallucinated citations.
Reward: inline citations [1], [2], proper References section, real DOIs/URLs.

Be honest and constructive. Focus on your domain of expertise.
{"Note: This is a revision - check if previous issues were addressed." if round_number > 1 else ""}"""

    tracker.start_operation(f"review_{specialist_id}")
    response = await llm.generate(
        prompt=review_prompt,
        system=specialist["system_prompt"],
        temperature=0.3,
        max_tokens=4096
    )
    duration = tracker.end_operation(f"review_{specialist_id}")
    tracker.record_reviewer_time(specialist_id, duration)

    # Parse JSON (with truncation repair)
    review_data = repair_json(response.content)
    scores = review_data["scores"]
    average = sum(scores.values()) / len(scores)

    return {
        "specialist": specialist_id,
        "specialist_name": specialist["name"],
        "provider": provider,
        "model": model,
        "scores": scores,
        "average": round(average, 1),
        "summary": review_data["summary"],
        "strengths": review_data["strengths"],
        "weaknesses": review_data["weaknesses"],
        "suggestions": review_data["suggestions"],
        "detailed_feedback": review_data["detailed_feedback"],
        "tokens": response.total_tokens,
        "input_tokens": response.input_tokens or 0,
        "output_tokens": response.output_tokens or 0,
    }


async def run_review_round(
    manuscript: str,
    round_number: int,
    specialists: Dict[str, dict],
    tracker: PerformanceTracker,
    previous_reviews: Optional[List[dict]] = None,
    previous_manuscript: Optional[str] = None,
    author_response: Optional[str] = None,
    article_length: str = "full",
    audience_level: str = "professional",
    research_type: str = "survey",
) -> tuple[List[Dict], float]:
    """Run one round of peer review.

    Args:
        manuscript: Manuscript to review
        round_number: Round number
        specialists: Dictionary of specialist definitions
        tracker: Performance tracker
        previous_reviews: Reviews from previous round
        previous_manuscript: Manuscript from previous round
        author_response: Author's response to previous reviews
        article_length: "full" or "short" — adjusts reviewer expectations
        audience_level: "beginner", "intermediate", or "professional"
        research_type: "survey" or "research" — adjusts review criteria

    Returns:
        (reviews, overall_average)
    """
    console.print(f"\n[bold cyan]Round {round_number}: Specialist Review[/bold cyan]\n")

    tracker.start_round(round_number)
    reviews = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        tasks = {}
        for specialist_id, specialist in specialists.items():
            specialist_name = specialist["name"]
            task = progress.add_task(f"[cyan]{specialist_name}...", total=None)
            tasks[specialist_id] = task

        # Generate reviews concurrently, tolerating individual failures
        specialist_items = list(specialists.items())
        review_coros = [
            generate_review(sid, spec, manuscript, round_number, tracker, previous_reviews, previous_manuscript, author_response, article_length, audience_level, research_type)
            for sid, spec in specialist_items
        ]
        results = await asyncio.gather(*review_coros, return_exceptions=True)

        for (specialist_id, specialist), result in zip(specialist_items, results):
            if isinstance(result, Exception):
                console.print(f"[yellow]⚠ {specialist['name']} failed: {result}[/yellow]")
                failed_review = _build_on_leave_review(specialist_id, specialist, str(result))
                reviews.append(failed_review)
            else:
                reviews.append(result)
                console.print(f"[green]✓[/green] {result['specialist_name']} complete (avg: {result['average']}/10)")
            progress.update(tasks[specialist_id], completed=True)

    # Compute average excluding on_leave reviewers
    active_reviews = [r for r in reviews if not r.get("on_leave")]
    if not active_reviews:
        raise RuntimeError("All reviewers failed. Cannot continue workflow.")
    overall_average = sum(r["average"] for r in active_reviews) / len(active_reviews)

    # Display scores
    table = Table(title=f"\nRound {round_number} Scores", show_header=True)
    table.add_column("Specialist", style="cyan")
    table.add_column("Accuracy", justify="center")
    table.add_column("Complete", justify="center")
    table.add_column("Clarity", justify="center")
    table.add_column("Novelty", justify="center")
    table.add_column("Rigor", justify="center")
    table.add_column("Citations", justify="center")
    table.add_column("Average", justify="center", style="bold")

    for review in reviews:
        if review.get("on_leave"):
            table.add_row(
                f"[dim]{review['specialist_name']}[/dim]",
                "-", "-", "-", "-", "-", "-",
                "[yellow]on leave[/yellow]"
            )
            continue
        scores = review["scores"]
        table.add_row(
            review["specialist_name"],
            str(scores["accuracy"]),
            str(scores["completeness"]),
            str(scores["clarity"]),
            str(scores["novelty"]),
            str(scores["rigor"]),
            str(scores.get("citations", "-")),
            f"{review['average']:.1f}"
        )

    console.print(table)
    console.print(f"\n[bold]Overall Average: {overall_average:.1f}/10[/bold]\n")

    # Record round tokens (total + per-model breakdown)
    round_tokens = sum(r.get("tokens", 0) for r in reviews)
    tracker.record_round_tokens(round_tokens)
    for r in reviews:
        tracker._track_model_tokens(
            r.get("model", ""),
            r.get("input_tokens", 0),
            r.get("output_tokens", 0),
        )

    return reviews, overall_average


def _build_on_leave_review(specialist_id: str, specialist: dict, error_msg: str) -> dict:
    """Build a placeholder review for a reviewer that failed during this round."""
    return {
        "specialist": specialist_id,
        "specialist_name": specialist["name"],
        "model": specialist.get("model", ""),
        "on_leave": True,
        "error": error_msg,
        "scores": {"accuracy": 0, "completeness": 0, "clarity": 0, "novelty": 0, "rigor": 0, "citations": 0},
        "average": 0,
        "summary": "",
        "strengths": [],
        "weaknesses": [],
        "suggestions": [],
        "detailed_feedback": "",
    }


def _detect_reviewer_outliers(reviews: List[Dict]) -> Optional[str]:
    """Detect if any reviewer gave a significantly harsher score than others.

    Returns a string describing outlier reviewers, or None if scores are consistent.
    """
    # Exclude on_leave reviewers from outlier detection
    active = [r for r in reviews if not r.get("on_leave")]
    if len(active) < 2:
        return None

    scores = [r["average"] for r in active]
    avg = sum(scores) / len(scores)

    outliers = []
    for r in active:
        deviation = avg - r["average"]
        # Flag reviewers scoring 1.5+ points below average
        if deviation >= 1.5:
            outliers.append(
                f"Reviewer '{r['specialist_name']}' scored {r['average']:.1f} "
                f"(avg: {avg:.1f}, deviation: -{deviation:.1f})"
            )

    if not outliers:
        return None

    # Compute what the average would be without the outlier(s)
    non_outlier_scores = [r["average"] for r in active if (avg - r["average"]) < 1.5]
    adjusted_avg = sum(non_outlier_scores) / len(non_outlier_scores) if non_outlier_scores else avg

    return (
        "REVIEWER OUTLIER DETECTED:\n"
        + "\n".join(f"- {o}" for o in outliers)
        + f"\nAdjusted average (excluding outliers): {adjusted_avg:.1f}/10\n"
        "Consider whether the outlier reviewer applied disproportionately harsh standards."
    )


def _build_auto_accept_decision(
    reviews: List[Dict], overall_average: float, round_number: int, threshold: float
) -> Dict:
    """Build a synthetic ACCEPT decision when score meets threshold automatically."""
    strengths = []
    for r in reviews:
        strengths.extend(r.get("strengths", [])[:2])
    # Deduplicate and limit
    seen = set()
    unique_strengths = []
    for s in strengths:
        if s not in seen:
            seen.add(s)
            unique_strengths.append(s)
            if len(unique_strengths) >= 3:
                break

    return {
        "decision": "ACCEPT",
        "confidence": 5,
        "meta_review": (
            f"The manuscript achieved an average reviewer score of {overall_average:.1f}/10, "
            f"meeting the acceptance threshold of {threshold}/10. "
            f"All structural completeness checks passed. "
            f"Auto-accepted based on reviewer consensus."
        ),
        "key_strengths": unique_strengths or ["Meets quality threshold"],
        "key_weaknesses": [],
        "required_changes": [],
        "recommendation": f"Accepted — score {overall_average:.1f} meets threshold {threshold}.",
        "round": round_number,
        "overall_average": round(overall_average, 1),
        "tokens": 0,
        "auto_accepted": True,
    }


class WorkflowOrchestrator:
    """Orchestrates the full research peer review workflow."""

    def __init__(
        self,
        expert_configs: List[ExpertConfig],
        topic: str,
        max_rounds: int = 3,
        threshold: float = 7.0,
        output_dir: Optional[Path] = None,
        status_callback = None,
        category: Optional[dict] = None,
        article_length: str = "full",
        audience_level: str = "professional",
        research_type: str = "survey",
    ):
        """Initialize workflow orchestrator.

        Args:
            expert_configs: List of expert configurations
            topic: Research topic
            max_rounds: Maximum review rounds
            threshold: Score threshold for acceptance
            output_dir: Output directory for results
            status_callback: Optional callback function(status, round_num, message)
            category: Optional dict with 'major' and 'subfield' keys for domain detection
            article_length: "full" (3,000-5,000 words) or "short" (1,500-2,500 words)
            audience_level: "beginner", "intermediate", or "professional"
            research_type: "survey" or "research" — determines writing/review approach
        """
        self.expert_configs = expert_configs
        self.topic = topic
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.output_dir = output_dir or Path("results") / topic.replace(" ", "-").lower()
        self.tracker = PerformanceTracker()
        self.status_callback = status_callback
        self.category = category
        self.article_length = article_length
        self.audience_level = audience_level
        self.research_type = research_type
        self._current_stage = "initializing"  # Track current pipeline stage for error context

        # Compute domain description from category
        if category and category.get("major"):
            self.domain_desc = get_domain_description(
                category["major"], category.get("subfield", "")
            )
        else:
            self.domain_desc = "interdisciplinary research"

        # Create specialists from configs
        self.specialists = SpecialistFactory.create_specialists_dict(
            expert_configs,
            topic
        )

        # Initialize agents
        self.writer = WriterAgent(role="writer")
        self.author_response_agent = WriterAgent(role="author_response")
        self.citation_verifier = WriterAgent(role="citation_verifier")
        self.moderator = ModeratorAgent(role="moderator")
        self.desk_editor = DeskEditorAgent(role="desk_editor")

        # Sources retrieved before writing (populated in _generate_initial_manuscript)
        self.sources: List[Reference] = []

    async def run(self, initial_manuscript: Optional[str] = None) -> dict:
        """Run the complete workflow.

        Args:
            initial_manuscript: Optional pre-written manuscript (if None, will generate)

        Returns:
            Workflow results dictionary
        """
        try:
            return await self._run_impl(initial_manuscript)
        except Exception as e:
            stage = getattr(self, '_current_stage', 'unknown')
            raise type(e)(f"[Stage: {stage}] {e}") from e

    async def _run_impl(self, initial_manuscript: Optional[str] = None) -> dict:
        """Internal implementation of the workflow run."""
        self.tracker.start_workflow()

        console.print(Panel.fit(
            "[bold cyan]AI Research Peer Review Workflow[/bold cyan]\n"
            "Iterative revision until quality threshold achieved",
            border_style="cyan"
        ))

        # Setup output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate or use provided manuscript
        self._current_stage = "writing initial manuscript"
        if initial_manuscript is None:
            if self.status_callback:
                self.status_callback("writing", 0, "Generating initial manuscript...")
            manuscript = await self._generate_initial_manuscript()
        else:
            manuscript = initial_manuscript
            console.print(f"\n[bold]Using provided manuscript[/bold]")

        # Citation verification pass (if sources available)
        if self.sources:
            console.print("\n[cyan]Running citation verification pass...[/cyan]")
            if self.status_callback:
                self.status_callback("writing", 0, "Verifying and strengthening citations...")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Verifying citations...", total=None)
                self.tracker.start_operation("citation_verification")
                manuscript = await self.citation_verifier.verify_citations(
                    manuscript,
                    self.sources,
                    domain=self.domain_desc,
                )
                cv_time = self.tracker.end_operation("citation_verification")
                self.tracker.record_citation_verification(**self.citation_verifier.get_last_token_usage())
                progress.update(task, completed=True)

            console.print(f"[green]✓ Citation verification complete[/green]")

        word_count = len(manuscript.split())
        console.print(f"Length: {word_count:,} words")
        console.print(f"Max rounds: {self.max_rounds}")
        console.print(f"Threshold: {self.threshold}/10")
        console.print(f"Expert team size: {len(self.expert_configs)} reviewers\n")

        # Save initial manuscript
        manuscript_v1_path = self.output_dir / "manuscript_v1.md"
        manuscript_v1_path.write_text(manuscript)
        console.print(f"[dim]Saved: {manuscript_v1_path}[/dim]")

        # Save initial checkpoint (enables resume from review phase if interrupted)
        self._save_checkpoint(0, manuscript, [])

        # Track all rounds
        all_rounds = []
        current_manuscript = manuscript
        previous_manuscript = None

        # Desk screening - quick editor check before expensive peer review
        self._current_stage = "desk screening"
        if self.status_callback:
            self.status_callback("desk_screening", 0, "Editor screening manuscript...")

        console.print("\n[cyan]Desk editor screening manuscript...[/cyan]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Desk editor screening...", total=None)
            desk_result = await self.desk_editor.screen(current_manuscript, self.topic)
            self._desk_result = desk_result
            self.tracker.record_desk_editor(
                tokens=desk_result.get("tokens", 0),
                input_tokens=desk_result.get("input_tokens", 0),
                output_tokens=desk_result.get("output_tokens", 0),
                model=desk_result.get("model", ""),
            )
            progress.update(task, completed=True)

        if desk_result["decision"] == "DESK_REJECT":
            console.print(f"\n[bold red]DESK REJECTED[/bold red]")
            console.print(f"[red]Reason: {desk_result['reason']}[/red]\n")

            # Save the rejected manuscript
            final_path = self.output_dir / "manuscript_final.md"
            final_path.write_text(current_manuscript)

            # Save round data for desk reject (round 0)
            round_data = {
                "round": 0,
                "manuscript_version": "v1",
                "word_count": len(current_manuscript.split()),
                "reviews": [],
                "overall_average": 0,
                "moderator_decision": {
                    "decision": "DESK_REJECT",
                    "reason": desk_result["reason"],
                    "tokens": desk_result["tokens"]
                },
                "author_response": None,
                "manuscript_diff": None,
                "threshold": self.threshold,
                "passed": False,
                "timestamp": datetime.now().isoformat()
            }
            all_rounds.append(round_data)

            round_file = self.output_dir / "round_0.json"
            with open(round_file, "w") as f:
                json.dump(round_data, f, indent=2)

            if self.status_callback:
                self.status_callback("completed", 0, "Desk rejected by editor")

            return await self._finalize_workflow(all_rounds)

        console.print(f"[green]Desk screening: PASS[/green] - {desk_result['reason']}")

        # Iterative review loop
        for round_num in range(1, self.max_rounds + 1):
            console.print("\n" + "="*80 + "\n")

            # Run review
            self._current_stage = f"peer review (round {round_num}/{self.max_rounds})"
            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Expert reviews in progress...")

            # Get previous reviews and author response for context
            prev_reviews = all_rounds[-1]['reviews'] if all_rounds else None
            prev_response = all_rounds[-1].get('author_response') or all_rounds[-1].get('author_rebuttal') if all_rounds else None

            reviews, overall_average = await run_review_round(
                current_manuscript,
                round_num,
                self.specialists,
                self.tracker,
                prev_reviews,
                previous_manuscript,
                prev_response,  # Pass author response to reviewers
                self.article_length,
                self.audience_level,
                self.research_type,
            )

            # Update status after reviews complete
            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Reviews complete, moderator evaluating...")

            # Check manuscript completeness before moderator evaluation
            completeness = validate_manuscript_completeness(current_manuscript)
            completeness_warning = None
            if not completeness["is_complete"]:
                completeness_warning = (
                    f"COMPLETENESS WARNING: {', '.join(completeness['issues'])}. "
                    "An incomplete manuscript MUST NOT be accepted."
                )
                console.print(f"[yellow]⚠ {completeness_warning}[/yellow]")

            # Auto-accept if score >= threshold and manuscript is complete
            self._current_stage = f"moderator evaluation (round {round_num})"
            if overall_average >= self.threshold and (completeness_warning is None):
                console.print(f"\n[bold green]✓ AUTO-ACCEPT: Score {overall_average:.1f} >= {self.threshold} threshold[/bold green]")
                moderator_decision = _build_auto_accept_decision(
                    reviews, overall_average, round_num, self.threshold
                )
                self.tracker.record_moderator_time(0)
            else:
                # Detect outlier reviewers for moderator context
                outlier_info = _detect_reviewer_outliers(reviews)

                # Moderator decision
                console.print("\n[cyan]Moderator evaluating...[/cyan]")

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]Moderator evaluating...", total=None)
                    self.tracker.start_operation("moderator")
                    moderator_decision = await self.moderator.make_decision(
                        current_manuscript,
                        reviews,
                        round_num,
                        self.max_rounds,
                        previous_rounds=all_rounds,
                        domain=self.domain_desc,
                        completeness_warning=completeness_warning,
                        outlier_info=outlier_info,
                        threshold=self.threshold,
                    )
                    moderator_time = self.tracker.end_operation("moderator")
                    self.tracker.record_moderator_time(moderator_time)
                    self.tracker.record_moderator(
                        tokens=moderator_decision.get("tokens", 0),
                        input_tokens=moderator_decision.get("input_tokens", 0),
                        output_tokens=moderator_decision.get("output_tokens", 0),
                        model=moderator_decision.get("model", ""),
                    )
                    progress.update(task, completed=True)

            # Report score + decision via status callback for activity log
            if self.status_callback:
                decision_str = moderator_decision["decision"]
                score_str = f"{overall_average:.1f}/10"
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Score {score_str} — {decision_str}")

            # Display moderator decision
            decision_color = {
                "ACCEPT": "green",
                "MINOR_REVISION": "yellow",
                "MAJOR_REVISION": "yellow",
                "REJECT": "red"
            }.get(moderator_decision["decision"], "white")

            console.print(Panel.fit(
                f"[bold {decision_color}]Decision: {moderator_decision['decision']}[/bold {decision_color}]\n"
                f"Confidence: {moderator_decision['confidence']}/5\n\n"
                f"[bold]Meta-Review:[/bold]\n{moderator_decision['meta_review']}\n\n"
                f"[bold]Required Changes:[/bold]\n" +
                "\n".join(f"• {c}" for c in moderator_decision['required_changes']),
                title="Moderator Decision",
                border_style=decision_color
            ))

            # Generate author response only if revision is needed AND not at max rounds
            author_response = None
            needs_revision = moderator_decision["decision"] != "ACCEPT"
            is_final_round = round_num >= self.max_rounds

            if needs_revision and not is_final_round:
                console.print("\n[cyan]Author preparing response...[/cyan]")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]Author writing response...", total=None)
                    self.tracker.start_operation("author_response")
                    author_response = await self.author_response_agent.write_author_response(
                        current_manuscript,
                        reviews,
                        round_num
                    )
                    response_time = self.tracker.end_operation("author_response")
                    self.tracker.record_author_response(**self.author_response_agent.get_last_token_usage())
                    progress.update(task, completed=True)

                console.print(f"[green]✓ Author response complete[/green]")

                response_preview = author_response[:300] + "..." if len(author_response) > 300 else author_response
                console.print(Panel.fit(
                    response_preview,
                    title="Author Response (preview)",
                    border_style="cyan"
                ))

                response_file = self.output_dir / f"author_response_round_{round_num}.md"
                response_file.write_text(author_response)
                console.print(f"[dim]Saved: {response_file}[/dim]")

            # Calculate manuscript diff
            manuscript_diff = None
            if previous_manuscript:
                words_added = len(current_manuscript.split()) - len(previous_manuscript.split())
                manuscript_diff = {
                    "words_added": words_added,
                    "previous_version": f"v{round_num-1}",
                    "current_version": f"v{round_num}"
                }

            # End round tracking
            self.tracker.end_round()

            # Save round data
            round_data = {
                "round": round_num,
                "manuscript_version": f"v{round_num}",
                "word_count": len(current_manuscript.split()),
                "reviews": reviews,
                "overall_average": round(overall_average, 1),
                "moderator_decision": moderator_decision,
                "author_response": author_response,
                "manuscript_diff": manuscript_diff,
                "threshold": self.threshold,
                "passed": moderator_decision["decision"] == "ACCEPT",
                "timestamp": datetime.now().isoformat()
            }

            round_file = self.output_dir / f"round_{round_num}.json"
            with open(round_file, "w") as f:
                json.dump(round_data, f, indent=2)
            console.print(f"[dim]Saved: {round_file}[/dim]")

            all_rounds.append(round_data)

            # Check if passed
            if moderator_decision["decision"] == "ACCEPT":
                # Save checkpoint before finalizing (manuscript unchanged, just for completeness)
                self._save_checkpoint(round_num, current_manuscript, all_rounds)

                console.print(f"\n[bold green]✓ ACCEPTED BY MODERATOR[/bold green]")
                console.print(f"[green]Manuscript accepted after {round_num} round(s) of review![/green]\n")

                final_path = self.output_dir / "manuscript_final.md"
                final_path.write_text(current_manuscript)
                console.print(f"[green]Final manuscript saved:[/green] {final_path}")

                if self.status_callback:
                    self.status_callback("completed", round_num, f"Report completed successfully after {round_num} rounds")
                break

            # Check if max rounds reached
            if round_num >= self.max_rounds:
                self._save_checkpoint(round_num, current_manuscript, all_rounds)

                console.print(f"\n[yellow]⚠ MAX ROUNDS REACHED[/yellow]")
                console.print(f"[yellow]Final decision: {moderator_decision['decision']}[/yellow]\n")

                final_path = self.output_dir / f"manuscript_final_v{round_num}.md"
                final_path.write_text(current_manuscript)
                console.print(f"[yellow]Best attempt saved:[/yellow] {final_path}")
                break

            # Need revision
            revision_type = moderator_decision["decision"].replace("_", " ")
            console.print(f"\n[yellow]⚠ {revision_type} REQUIRED[/yellow]")
            console.print(f"[cyan]Round {round_num + 1}: Generating revision...[/cyan]\n")

            # Save checkpoint BEFORE revision (if interrupted, resume will re-do revision)
            self._save_checkpoint(round_num, current_manuscript, all_rounds)

            previous_manuscript = current_manuscript

            # Generate revision
            self._current_stage = f"manuscript revision (round {round_num})"
            if self.status_callback:
                self.status_callback("revising", round_num, f"Round {round_num}: Revising manuscript based on feedback...")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Writer revising manuscript...", total=None)
                self.tracker.start_operation("revision")
                revised_manuscript = await self.writer.revise_manuscript(
                    current_manuscript,
                    reviews,
                    round_num,
                    references=self.sources if self.sources else None,
                    domain=self.domain_desc,
                    article_length=self.article_length,
                    audience_level=self.audience_level,
                    research_type=self.research_type,
                )
                revision_time = self.tracker.end_operation("revision")
                self.tracker.record_revision_time(revision_time)
                self.tracker.record_revision(**self.writer.get_last_token_usage())
                progress.update(task, completed=True)

            new_word_count = len(revised_manuscript.split())
            word_change = new_word_count - len(current_manuscript.split())
            console.print(f"[green]✓ Revision complete[/green]")
            console.print(f"New length: {new_word_count:,} words ([{word_change:+,}])\n")

            # Save revised manuscript
            manuscript_path_next = self.output_dir / f"manuscript_v{round_num + 1}.md"
            manuscript_path_next.write_text(revised_manuscript)
            console.print(f"[dim]Saved: {manuscript_path_next}[/dim]")

            current_manuscript = revised_manuscript

            # Generate author response based on revised manuscript
            if moderator_decision["decision"] != "ACCEPT":
                console.print("\n[cyan]Generating author response based on revised manuscript...[/cyan]")
                self.tracker.start_operation("author_response")
                author_response = await self.author_response_agent.write_author_response(
                    current_manuscript,
                    reviews,
                    round_num
                )
                response_time = self.tracker.end_operation("author_response")
                self.tracker.record_author_response(**self.author_response_agent.get_last_token_usage())

                console.print(f"[green]✓ Author response complete[/green]")
                response_preview = author_response[:300] + "..." if len(author_response) > 300 else author_response
                console.print(Panel.fit(
                    response_preview,
                    title="Author Response (preview)",
                    border_style="cyan"
                ))
                response_file = self.output_dir / f"author_response_round_{round_num}.md"
                response_file.write_text(author_response)
                console.print(f"[dim]Saved: {response_file}[/dim]")
            else:
                author_response = None

            # Update round data with actual revision diff
            revision_diff = {
                "words_added": new_word_count - len(previous_manuscript.split()),
                "previous_version": f"v{round_num}",
                "current_version": f"v{round_num + 1}"
            }
            round_data["manuscript_diff"] = revision_diff
            round_data["revised_word_count"] = new_word_count

            # Re-save round file with updated revision diff
            with open(round_file, "w") as f:
                json.dump(round_data, f, indent=2)

            # Update checkpoint with REVISED manuscript (resume gets correct version)
            self._save_checkpoint(round_num, current_manuscript, all_rounds)

        # Generate summary and export
        return await self._finalize_workflow(all_rounds)

    async def _generate_initial_manuscript(self) -> str:
        """Generate initial manuscript from topic with real source retrieval."""

        # --- Source retrieval ---
        console.print("\n[cyan]Searching academic databases for sources...[/cyan]\n")
        if self.status_callback:
            self.status_callback("searching", 0, "Searching academic databases for real sources...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Retrieving sources (OpenAlex, arXiv, ...)...", total=None)
            retriever = SourceRetriever()
            self.sources = await retriever.search_all(self.topic)
            progress.update(task, completed=True)

        if self.sources:
            console.print(f"[green]✓ Found {len(self.sources)} verified sources[/green]")
            for ref in self.sources[:5]:
                console.print(f"  [{ref.id}] {ref.title[:70]}{'...' if len(ref.title) > 70 else ''} ({ref.year})")
            if len(self.sources) > 5:
                console.print(f"  ... and {len(self.sources) - 5} more")
        else:
            console.print("[yellow]No external sources found, proceeding without citations[/yellow]")

        # --- Manuscript generation ---
        console.print("\n[cyan]Generating initial manuscript...[/cyan]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Writer generating manuscript...", total=None)
            self.tracker.start_operation("initial_draft")
            manuscript = await self.writer.write_manuscript(
                self.topic,
                references=self.sources if self.sources else None,
                domain=self.domain_desc,
                article_length=self.article_length,
                audience_level=self.audience_level,
                research_type=self.research_type,
            )
            duration = self.tracker.end_operation("initial_draft")
            self.tracker.record_initial_draft(duration, **self.writer.get_last_token_usage())
            progress.update(task, completed=True)

        console.print(f"[green]✓ Initial manuscript complete[/green]")

        # Check manuscript completeness
        completeness = validate_manuscript_completeness(manuscript)
        if not completeness["is_complete"]:
            console.print(f"[yellow]⚠ Completeness issues: {', '.join(completeness['issues'])}[/yellow]")
        else:
            console.print(f"[green]✓ Manuscript completeness check passed[/green]")

        # Generate academic title from manuscript content
        console.print("\n[cyan]Generating academic title...[/cyan]")
        from ..utils.title_generator import generate_title_from_manuscript
        self.generated_title = await generate_title_from_manuscript(manuscript, self.topic)
        console.print(f"[green]✓ Title: {self.generated_title}[/green]")

        # Add metadata header to manuscript
        from pathlib import Path as _Path
        from datetime import datetime
        version_file = _Path(__file__).resolve().parent.parent.parent / "VERSION"
        system_version = version_file.read_text().strip() if version_file.exists() else "unknown"

        metadata_header = f"""<!--
Generated by: Autonomous Research Press v{system_version}
Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
Topic: {self.topic}
Title: {self.generated_title}
Audience Level: {self.audience_level}
Research Type: {self.research_type}
-->

"""
        manuscript = metadata_header + manuscript

        console.print()
        return manuscript

    async def _finalize_workflow(self, all_rounds: List[dict]) -> dict:
        """Finalize workflow and export results.

        Args:
            all_rounds: List of round data

        Returns:
            Complete workflow data
        """
        console.print("\n" + "="*80 + "\n")
        console.print("[bold]Workflow Summary:[/bold]\n")

        summary_table = Table(show_header=True)
        summary_table.add_column("Round", style="cyan")
        summary_table.add_column("Score", justify="center")
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Words", justify="right")

        for rd in all_rounds:
            status = "✓ PASS" if rd["passed"] else "⚠ REVISE"
            status_color = "green" if rd["passed"] else "yellow"
            summary_table.add_row(
                str(rd["round"]),
                f"{rd['overall_average']:.1f}/10",
                f"[{status_color}]{status}[/{status_color}]",
                f"{rd['word_count']:,}"
            )

        console.print(summary_table)

        # Export performance metrics
        metrics = self.tracker.export_metrics()

        # Display performance summary
        console.print(f"\n[bold]Performance Metrics:[/bold]")
        console.print(f"  Total duration: {metrics.total_duration:.1f}s ({metrics.total_duration/60:.1f}m)")
        console.print(f"  Initial draft: {metrics.initial_draft_time:.1f}s")
        if metrics.team_composition_time > 0:
            console.print(f"  Team composition: {metrics.team_composition_time:.1f}s")
        console.print(f"  Review rounds: {len(metrics.rounds)}")
        for round_metric in metrics.rounds:
            console.print(f"    Round {round_metric.round_number}: {round_metric.review_duration:.1f}s")
        console.print(f"  Total tokens: {metrics.total_tokens:,}")
        console.print(f"  Estimated cost: ${metrics.estimated_cost:.2f}\n")

        # Read system version
        from pathlib import Path as _Path
        version_file = _Path(__file__).resolve().parent.parent.parent / "VERSION"
        system_version = "unknown"
        if version_file.exists():
            system_version = version_file.read_text().strip()

        # Save complete workflow
        workflow_data = {
            "topic": self.topic,
            "title": getattr(self, 'generated_title', self.topic),
            "system_version": system_version,
            "generated_at": datetime.now().isoformat(),
            "output_directory": str(self.output_dir),
            "max_rounds": self.max_rounds,
            "threshold": self.threshold,
            "category": self.category,
            "audience_level": self.audience_level,
            "research_type": self.research_type,
            "desk_screening": getattr(self, '_desk_result', {}),
            "expert_team": [config.to_dict() for config in self.expert_configs],
            "rounds": all_rounds,
            "final_score": all_rounds[-1]["overall_average"],
            "passed": all_rounds[-1]["passed"],
            "total_rounds": len(all_rounds),
            "performance": metrics.to_dict(),
            "timestamp": datetime.now().isoformat()
        }

        workflow_file = self.output_dir / "workflow_complete.json"
        with open(workflow_file, "w") as f:
            json.dump(workflow_data, f, indent=2)

        console.print(f"[bold green]✓ Complete workflow saved:[/bold green] {workflow_file}\n")

        # Remove checkpoint file on successful completion
        checkpoint_file = self.output_dir / "workflow_checkpoint.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

        return workflow_data

    def _save_checkpoint(self, round_num: int, current_manuscript: str, all_rounds: List[dict]):
        """Save checkpoint for resume capability.

        Args:
            round_num: Current round number
            current_manuscript: Current manuscript text
            all_rounds: All round data so far
        """
        checkpoint = {
            "topic": self.topic,
            "current_round": round_num,
            "max_rounds": self.max_rounds,
            "threshold": self.threshold,
            "current_manuscript": current_manuscript,
            "all_rounds": all_rounds,
            "expert_configs": [config.to_dict() for config in self.expert_configs],
            "category": self.category,
            "audience_level": self.audience_level,
            "research_type": self.research_type,
            "checkpoint_time": datetime.now().isoformat(),
            "status": "in_progress"
        }

        checkpoint_file = self.output_dir / "workflow_checkpoint.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint, f, indent=2)

    @classmethod
    async def resume_from_checkpoint(cls, output_dir: Path, status_callback=None) -> dict:
        """Resume workflow from checkpoint.

        Args:
            output_dir: Directory containing checkpoint
            status_callback: Optional status callback function

        Returns:
            Workflow results dictionary

        Raises:
            FileNotFoundError: If no checkpoint found
            ValueError: If checkpoint is invalid
        """
        checkpoint_file = output_dir / "workflow_checkpoint.json"

        if not checkpoint_file.exists():
            raise FileNotFoundError(f"No checkpoint found in {output_dir}")

        console.print(f"\n[cyan]Resuming workflow from checkpoint...[/cyan]")

        # Load checkpoint
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)

        # Reconstruct expert configs
        from ..models.expert import ExpertConfig
        expert_configs = [ExpertConfig.from_dict(cfg) for cfg in checkpoint["expert_configs"]]

        # Create orchestrator
        orchestrator = cls(
            expert_configs=expert_configs,
            topic=checkpoint["topic"],
            max_rounds=checkpoint["max_rounds"],
            threshold=checkpoint["threshold"],
            output_dir=output_dir,
            status_callback=status_callback,
            category=checkpoint.get("category"),
            audience_level=checkpoint.get("audience_level", "professional"),
            research_type=checkpoint.get("research_type", "survey"),
        )

        # Restore state
        current_round = checkpoint["current_round"]
        current_manuscript = checkpoint["current_manuscript"]
        all_rounds = checkpoint["all_rounds"]

        console.print(f"[green]✓ Loaded checkpoint from Round {current_round}[/green]")
        console.print(f"[cyan]Continuing from Round {current_round + 1}...[/cyan]\n")

        # Resume from next round
        return await orchestrator._resume_workflow(
            current_round,
            current_manuscript,
            all_rounds
        )

    async def _resume_workflow(
        self,
        start_round: int,
        current_manuscript: str,
        all_rounds: List[dict]
    ) -> dict:
        """Continue workflow from a specific round."""
        try:
            return await self._resume_workflow_impl(start_round, current_manuscript, all_rounds)
        except Exception as e:
            stage = getattr(self, '_current_stage', 'unknown')
            raise type(e)(f"[Stage: {stage}] {e}") from e

    async def _resume_workflow_impl(
        self,
        start_round: int,
        current_manuscript: str,
        all_rounds: List[dict]
    ) -> dict:
        """Internal implementation of resume workflow.

        Args:
            start_round: Round number to resume from
            current_manuscript: Current manuscript state
            all_rounds: Round history

        Returns:
            Workflow results dictionary
        """
        self.tracker.start_workflow()

        # Handle round 0 checkpoint (no reviews yet — start fresh from round 1)
        if not all_rounds:
            console.print(f"[cyan]Resuming from initial manuscript (no reviews completed yet)[/cyan]")
            console.print(f"[cyan]Starting review from Round 1...[/cyan]\n")
            # Fall through to the iteration loop below with start_round=0
            # which will iterate range(1, max_rounds+1)
        else:
            # Check last round's decision
            last_round = all_rounds[-1]
            last_decision = last_round["moderator_decision"]["decision"]

            console.print(f"[cyan]Last decision: {last_decision}[/cyan]")

            # If already accepted, finalize
            if last_decision == "ACCEPT":
                console.print(f"[green]✓ Paper already accepted in Round {start_round}[/green]")
                return await self._finalize_workflow(all_rounds)

            # If at max rounds, finalize
            if start_round >= self.max_rounds:
                console.print(f"[yellow]⚠ Already at max rounds ({self.max_rounds})[/yellow]")
                return await self._finalize_workflow(all_rounds)

            # Check if revision was interrupted: last decision needed revision but revised manuscript missing
            self._current_stage = f"resuming from round {start_round}"
            revised_path = self.output_dir / f"manuscript_v{start_round + 1}.md"
            if last_decision in ("MINOR_REVISION", "MAJOR_REVISION") and not revised_path.exists():
                self._current_stage = f"re-running interrupted revision (round {start_round})"
                console.print(f"[yellow]Revision for round {start_round} was interrupted — re-running revision...[/yellow]")

                if self.status_callback:
                    self.status_callback("revising", start_round, f"Round {start_round}: Re-running interrupted revision...")

                prev_reviews = last_round.get("reviews", [])
                prev_author_response = last_round.get("author_response")

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]Writer revising manuscript (resumed)...", total=None)
                    self.tracker.start_operation("revision")
                    revised_manuscript = await self.writer.revise_manuscript(
                        current_manuscript,
                        prev_reviews,
                        start_round,
                        references=self.sources if self.sources else None,
                        domain=self.domain_desc,
                        article_length=self.article_length,
                        author_response=prev_author_response,
                        audience_level=self.audience_level,
                        research_type=self.research_type,
                    )
                    revision_time = self.tracker.end_operation("revision")
                    self.tracker.record_revision_time(revision_time)
                    self.tracker.record_revision(**self.writer.get_last_token_usage())
                    progress.update(task, completed=True)

                new_word_count = len(revised_manuscript.split())
                console.print(f"[green]✓ Revision complete[/green] — {new_word_count:,} words")

                revised_path.write_text(revised_manuscript)
                current_manuscript = revised_manuscript

                # Update last round data with revision diff
                last_round["manuscript_diff"] = {
                    "words_added": new_word_count - len(current_manuscript.split()),
                    "previous_version": f"v{start_round}",
                    "current_version": f"v{start_round + 1}"
                }
                last_round["revised_word_count"] = new_word_count

                # Update checkpoint with revised manuscript
                self._save_checkpoint(start_round, current_manuscript, all_rounds)

        # Continue iteration from next round
        previous_manuscript = current_manuscript

        for round_num in range(start_round + 1, self.max_rounds + 1):
            console.print("\n" + "="*80 + "\n")

            # Run review
            self._current_stage = f"peer review (round {round_num}/{self.max_rounds})"
            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Expert reviews in progress...")

            # Get previous reviews and author response
            prev_reviews = all_rounds[-1]['reviews'] if all_rounds else None
            prev_response = all_rounds[-1].get('author_response') or all_rounds[-1].get('author_rebuttal') if all_rounds else None

            reviews, overall_average = await run_review_round(
                current_manuscript,
                round_num,
                self.specialists,
                self.tracker,
                prev_reviews,
                previous_manuscript,
                prev_response,
                self.article_length,
                self.audience_level,
                self.research_type,
            )

            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Reviews complete, moderator evaluating...")

            # Check manuscript completeness before moderator evaluation
            completeness = validate_manuscript_completeness(current_manuscript)
            completeness_warning = None
            if not completeness["is_complete"]:
                completeness_warning = (
                    f"COMPLETENESS WARNING: {', '.join(completeness['issues'])}. "
                    "An incomplete manuscript MUST NOT be accepted."
                )
                console.print(f"[yellow]⚠ {completeness_warning}[/yellow]")

            # Auto-accept if score >= threshold and manuscript is complete
            self._current_stage = f"moderator evaluation (round {round_num})"
            if overall_average >= self.threshold and (completeness_warning is None):
                console.print(f"\n[bold green]✓ AUTO-ACCEPT: Score {overall_average:.1f} >= {self.threshold} threshold[/bold green]")
                moderator_decision = _build_auto_accept_decision(
                    reviews, overall_average, round_num, self.threshold
                )
                self.tracker.record_moderator_time(0)
                speculative_author_response = None
            else:
                # Detect outlier reviewers for moderator context
                outlier_info = _detect_reviewer_outliers(reviews)

                # Moderator decision + author response in parallel
                console.print("\n[cyan]Moderator evaluating + Author preparing response (parallel)...[/cyan]")

                async def _run_moderator_resume():
                    self.tracker.start_operation("moderator")
                    result = await self.moderator.make_decision(
                        current_manuscript,
                        reviews,
                        round_num,
                        self.max_rounds,
                        previous_rounds=all_rounds,
                        domain=self.domain_desc,
                        completeness_warning=completeness_warning,
                        outlier_info=outlier_info,
                        threshold=self.threshold,
                    )
                    moderator_time = self.tracker.end_operation("moderator")
                    self.tracker.record_moderator_time(moderator_time)
                    self.tracker.record_moderator(
                        tokens=result.get("tokens", 0),
                        input_tokens=result.get("input_tokens", 0),
                        output_tokens=result.get("output_tokens", 0),
                        model=result.get("model", ""),
                    )
                    return result

                async def _run_author_response_resume():
                    self.tracker.start_operation("author_response")
                    result = await self.author_response_agent.write_author_response(
                        current_manuscript,
                        reviews,
                        round_num
                    )
                    response_time = self.tracker.end_operation("author_response")
                    self.tracker.record_author_response(**self.author_response_agent.get_last_token_usage())
                    return result

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]Moderator + Author response (parallel)...", total=None)
                    moderator_decision, speculative_author_response = await asyncio.gather(
                        _run_moderator_resume(),
                        _run_author_response_resume()
                    )
                    progress.update(task, completed=True)

            # Report score + decision via status callback for activity log
            if self.status_callback:
                decision_str = moderator_decision["decision"]
                score_str = f"{overall_average:.1f}/10"
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Score {score_str} — {decision_str}")

            # Display decision
            decision_color = {
                "ACCEPT": "green",
                "MINOR_REVISION": "yellow",
                "MAJOR_REVISION": "yellow",
                "REJECT": "red"
            }.get(moderator_decision["decision"], "white")

            console.print(Panel.fit(
                f"[bold {decision_color}]Decision: {moderator_decision['decision']}[/bold {decision_color}]\n"
                f"Confidence: {moderator_decision['confidence']}/5\n\n"
                f"[bold]Meta-Review:[/bold]\n{moderator_decision['meta_review']}\n\n"
                f"[bold]Required Changes:[/bold]\n" +
                "\n".join(f"• {c}" for c in moderator_decision['required_changes']),
                title="Moderator Decision",
                border_style=decision_color
            ))

            # Use author response only if revision is needed
            author_response = None
            if moderator_decision["decision"] != "ACCEPT":
                author_response = speculative_author_response
                console.print(f"[green]✓ Author response complete[/green]")

                response_preview = author_response[:300] + "..." if len(author_response) > 300 else author_response
                console.print(Panel.fit(
                    response_preview,
                    title="Author Response (preview)",
                    border_style="cyan"
                ))

                response_file = self.output_dir / f"author_response_round_{round_num}.md"
                response_file.write_text(author_response)
                console.print(f"[dim]Saved: {response_file}[/dim]")

            # Calculate diff
            manuscript_diff = None
            if previous_manuscript:
                words_added = len(current_manuscript.split()) - len(previous_manuscript.split())
                manuscript_diff = {
                    "words_added": words_added,
                    "previous_version": f"v{round_num-1}",
                    "current_version": f"v{round_num}"
                }

            # End round tracking
            self.tracker.end_round()

            # Save round data
            round_data = {
                "round": round_num,
                "manuscript_version": f"v{round_num}",
                "word_count": len(current_manuscript.split()),
                "reviews": reviews,
                "overall_average": round(overall_average, 1),
                "moderator_decision": moderator_decision,
                "author_response": author_response,
                "manuscript_diff": manuscript_diff,
                "threshold": self.threshold,
                "passed": moderator_decision["decision"] == "ACCEPT",
                "timestamp": datetime.now().isoformat()
            }

            round_file = self.output_dir / f"round_{round_num}.json"
            with open(round_file, "w") as f:
                json.dump(round_data, f, indent=2)
            console.print(f"[dim]Saved: {round_file}[/dim]")

            all_rounds.append(round_data)

            # Check if passed
            if moderator_decision["decision"] == "ACCEPT":
                self._save_checkpoint(round_num, current_manuscript, all_rounds)

                console.print(f"\n[bold green]✓ ACCEPTED BY MODERATOR[/bold green]")
                console.print(f"[green]Manuscript accepted after {round_num} round(s) of review![/green]\n")

                final_path = self.output_dir / "manuscript_final.md"
                final_path.write_text(current_manuscript)
                console.print(f"[green]Final manuscript saved:[/green] {final_path}")

                if self.status_callback:
                    self.status_callback("completed", round_num, f"Report completed successfully after {round_num} rounds")
                break

            # Check if max rounds reached
            if round_num >= self.max_rounds:
                self._save_checkpoint(round_num, current_manuscript, all_rounds)

                console.print(f"\n[yellow]⚠ MAX ROUNDS REACHED[/yellow]")
                console.print(f"[yellow]Final decision: {moderator_decision['decision']}[/yellow]\n")

                final_path = self.output_dir / f"manuscript_final_v{round_num}.md"
                final_path.write_text(current_manuscript)
                console.print(f"[yellow]Best attempt saved:[/yellow] {final_path}")
                break

            # Need revision
            revision_type = moderator_decision["decision"].replace("_", " ")
            console.print(f"\n[yellow]⚠ {revision_type} REQUIRED[/yellow]")
            console.print(f"[cyan]Round {round_num + 1}: Generating revision...[/cyan]\n")

            # Save checkpoint BEFORE revision (if interrupted, resume will re-do revision)
            self._save_checkpoint(round_num, current_manuscript, all_rounds)

            previous_manuscript = current_manuscript

            # Generate revision
            self._current_stage = f"manuscript revision (round {round_num})"
            if self.status_callback:
                self.status_callback("revising", round_num, f"Round {round_num}: Revising manuscript based on feedback...")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Writer revising manuscript...", total=None)
                self.tracker.start_operation("revision")
                revised_manuscript = await self.writer.revise_manuscript(
                    current_manuscript,
                    reviews,
                    round_num,
                    references=self.sources if self.sources else None,
                    domain=self.domain_desc,
                    article_length=self.article_length,
                    audience_level=self.audience_level,
                    research_type=self.research_type,
                )
                revision_time = self.tracker.end_operation("revision")
                self.tracker.record_revision_time(revision_time)
                self.tracker.record_revision(**self.writer.get_last_token_usage())
                progress.update(task, completed=True)

            new_word_count = len(revised_manuscript.split())
            word_change = new_word_count - len(current_manuscript.split())
            console.print(f"[green]✓ Revision complete[/green]")
            console.print(f"New length: {new_word_count:,} words ([{word_change:+,}])\n")

            # Save revised manuscript
            manuscript_path_next = self.output_dir / f"manuscript_v{round_num + 1}.md"
            manuscript_path_next.write_text(revised_manuscript)
            console.print(f"[dim]Saved: {manuscript_path_next}[/dim]")

            current_manuscript = revised_manuscript

            # Generate author response based on revised manuscript
            if moderator_decision["decision"] != "ACCEPT":
                console.print("\n[cyan]Generating author response based on revised manuscript...[/cyan]")
                self.tracker.start_operation("author_response")
                author_response = await self.author_response_agent.write_author_response(
                    current_manuscript,
                    reviews,
                    round_num
                )
                response_time = self.tracker.end_operation("author_response")
                self.tracker.record_author_response(**self.author_response_agent.get_last_token_usage())

                console.print(f"[green]✓ Author response complete[/green]")
                response_preview = author_response[:300] + "..." if len(author_response) > 300 else author_response
                console.print(Panel.fit(
                    response_preview,
                    title="Author Response (preview)",
                    border_style="cyan"
                ))
                response_file = self.output_dir / f"author_response_round_{round_num}.md"
                response_file.write_text(author_response)
                console.print(f"[dim]Saved: {response_file}[/dim]")
            else:
                author_response = None

            # Update round data with actual revision diff
            revision_diff = {
                "words_added": new_word_count - len(previous_manuscript.split()),
                "previous_version": f"v{round_num}",
                "current_version": f"v{round_num + 1}"
            }
            round_data["manuscript_diff"] = revision_diff
            round_data["revised_word_count"] = new_word_count

            # Re-save round file with updated revision diff
            with open(round_file, "w") as f:
                json.dump(round_data, f, indent=2)

            # Update checkpoint with REVISED manuscript (resume gets correct version)
            self._save_checkpoint(round_num, current_manuscript, all_rounds)

        # Generate summary and export
        return await self._finalize_workflow(all_rounds)
