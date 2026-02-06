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

from ..config import get_config
from ..llm import ClaudeLLM
from ..agents import WriterAgent, ModeratorAgent
from ..agents.specialist_factory import SpecialistFactory
from ..models.expert import ExpertConfig
from ..performance import PerformanceTracker

console = Console()


async def generate_review(
    specialist_id: str,
    specialist: dict,
    manuscript: str,
    round_number: int,
    tracker: PerformanceTracker,
    previous_reviews: Optional[List[dict]] = None,
    previous_manuscript: Optional[str] = None,
    author_rebuttal: Optional[str] = None
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
        author_rebuttal: Author's rebuttal to previous reviews

    Returns:
        Review data dictionary
    """
    config = get_config()

    provider = specialist["provider"]
    model = specialist["model"]

    llm_config = config.get_llm_config(provider, model)
    llm = ClaudeLLM(
        api_key=llm_config.api_key,
        model=llm_config.model,
        base_url=llm_config.base_url
    )

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

    # Add author rebuttal context if available
    rebuttal_context = ""
    if author_rebuttal:
        rebuttal_context = f"""
AUTHOR REBUTTAL TO PREVIOUS REVIEWS:

The authors have responded to reviewer feedback. Read their rebuttal carefully to understand:
- What changes they made
- Their rationale for decisions
- Clarifications of misunderstandings

{author_rebuttal}

---

IMPORTANT: Consider the author's rebuttal when evaluating this revision:
- Did they address your concerns adequately?
- Are their explanations/disagreements reasonable?
- Does the revised manuscript reflect their stated changes?
- Give credit for genuine engagement with feedback

---
"""

    review_prompt = f"""Review this research manuscript (Round {round_number}) from your expert perspective.

{previous_context}
{rebuttal_context}
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
    "rigor": <1-10>
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

    # Parse JSON
    content = response.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        review_data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse review from {specialist_id} as JSON: {e}\n"
            f"Raw response length: {len(response.content)}\n"
            f"Cleaned content length: {len(content)}\n"
            f"Content preview: {content[:200]}..."
        )
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
        "tokens": response.total_tokens
    }


async def run_review_round(
    manuscript: str,
    round_number: int,
    specialists: Dict[str, dict],
    tracker: PerformanceTracker,
    previous_reviews: Optional[List[dict]] = None,
    previous_manuscript: Optional[str] = None,
    author_rebuttal: Optional[str] = None
) -> tuple[List[Dict], float]:
    """Run one round of peer review.

    Args:
        manuscript: Manuscript to review
        round_number: Round number
        specialists: Dictionary of specialist definitions
        tracker: Performance tracker
        previous_reviews: Reviews from previous round
        previous_manuscript: Manuscript from previous round
        author_rebuttal: Author's rebuttal to previous reviews

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

        # Generate reviews concurrently
        review_tasks = [
            generate_review(specialist_id, specialist, manuscript, round_number, tracker, previous_reviews, previous_manuscript, author_rebuttal)
            for specialist_id, specialist in specialists.items()
        ]

        for review_result in asyncio.as_completed(review_tasks):
            review = await review_result
            reviews.append(review)
            specialist_id = review["specialist"]
            progress.update(tasks[specialist_id], completed=True)
            console.print(f"[green]✓[/green] {review['specialist_name']} complete (avg: {review['average']}/10)")

    overall_average = sum(r["average"] for r in reviews) / len(reviews)

    # Display scores
    table = Table(title=f"\nRound {round_number} Scores", show_header=True)
    table.add_column("Specialist", style="cyan")
    table.add_column("Accuracy", justify="center")
    table.add_column("Complete", justify="center")
    table.add_column("Clarity", justify="center")
    table.add_column("Novelty", justify="center")
    table.add_column("Rigor", justify="center")
    table.add_column("Average", justify="center", style="bold")

    for review in reviews:
        scores = review["scores"]
        table.add_row(
            review["specialist_name"],
            str(scores["accuracy"]),
            str(scores["completeness"]),
            str(scores["clarity"]),
            str(scores["novelty"]),
            str(scores["rigor"]),
            f"{review['average']:.1f}"
        )

    console.print(table)
    console.print(f"\n[bold]Overall Average: {overall_average:.1f}/10[/bold]\n")

    # Record round tokens
    round_tokens = sum(r.get("tokens", 0) for r in reviews)
    tracker.record_round_tokens(round_tokens)

    return reviews, overall_average


class WorkflowOrchestrator:
    """Orchestrates the full research peer review workflow."""

    def __init__(
        self,
        expert_configs: List[ExpertConfig],
        topic: str,
        max_rounds: int = 3,
        threshold: float = 8.0,
        output_dir: Optional[Path] = None,
        status_callback = None
    ):
        """Initialize workflow orchestrator.

        Args:
            expert_configs: List of expert configurations
            topic: Research topic
            max_rounds: Maximum review rounds
            threshold: Score threshold for acceptance
            output_dir: Output directory for results
            status_callback: Optional callback function(status, round_num, message)
        """
        self.expert_configs = expert_configs
        self.topic = topic
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.output_dir = output_dir or Path("results") / topic.replace(" ", "-").lower()
        self.tracker = PerformanceTracker()
        self.status_callback = status_callback

        # Create specialists from configs
        self.specialists = SpecialistFactory.create_specialists_dict(
            expert_configs,
            topic
        )

        # Initialize agents
        self.writer = WriterAgent(model="claude-opus-4.5")
        self.moderator = ModeratorAgent(model="claude-opus-4.5")

    async def run(self, initial_manuscript: Optional[str] = None) -> dict:
        """Run the complete workflow.

        Args:
            initial_manuscript: Optional pre-written manuscript (if None, will generate)

        Returns:
            Workflow results dictionary
        """
        self.tracker.start_workflow()

        console.print(Panel.fit(
            "[bold cyan]AI Research Peer Review Workflow[/bold cyan]\n"
            "Iterative revision until quality threshold achieved",
            border_style="cyan"
        ))

        # Setup output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate or use provided manuscript
        if initial_manuscript is None:
            if self.status_callback:
                self.status_callback("writing", 0, "Generating initial manuscript...")
            manuscript = await self._generate_initial_manuscript()
        else:
            manuscript = initial_manuscript
            console.print(f"\n[bold]Using provided manuscript[/bold]")

        word_count = len(manuscript.split())
        console.print(f"Length: {word_count:,} words")
        console.print(f"Max rounds: {self.max_rounds}")
        console.print(f"Threshold: {self.threshold}/10")
        console.print(f"Expert team size: {len(self.expert_configs)} reviewers\n")

        # Save initial manuscript
        manuscript_v1_path = self.output_dir / "manuscript_v1.md"
        manuscript_v1_path.write_text(manuscript)
        console.print(f"[dim]Saved: {manuscript_v1_path}[/dim]")

        # Track all rounds
        all_rounds = []
        current_manuscript = manuscript
        previous_manuscript = None

        # Iterative review loop
        for round_num in range(1, self.max_rounds + 1):
            console.print("\n" + "="*80 + "\n")

            # Run review
            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Expert reviews in progress...")

            # Get previous reviews and rebuttal for context
            prev_reviews = all_rounds[-1]['reviews'] if all_rounds else None
            prev_rebuttal = all_rounds[-1].get('author_rebuttal') if all_rounds else None

            reviews, overall_average = await run_review_round(
                current_manuscript,
                round_num,
                self.specialists,
                self.tracker,
                prev_reviews,
                previous_manuscript,
                prev_rebuttal  # Pass author rebuttal to reviewers
            )

            # Update status after reviews complete
            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Reviews complete, moderator evaluating...")

            # Moderator decision
            console.print("\n[cyan]Moderator evaluating reviews...[/cyan]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Moderator making decision...", total=None)
                self.tracker.start_operation("moderator")
                moderator_decision = await self.moderator.make_decision(
                    current_manuscript,
                    reviews,
                    round_num,
                    self.max_rounds,
                    previous_rounds=all_rounds  # Pass previous rounds for trajectory analysis
                )
                moderator_time = self.tracker.end_operation("moderator")
                self.tracker.record_moderator_time(moderator_time)
                progress.update(task, completed=True)

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

            # Author rebuttal (if revision needed)
            author_rebuttal = None
            if moderator_decision["decision"] != "ACCEPT":
                console.print("\n[cyan]Author writing rebuttal...[/cyan]")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]Author responding to reviews...", total=None)
                    self.tracker.start_operation("rebuttal")
                    author_rebuttal = await self.writer.write_rebuttal(
                        current_manuscript,
                        reviews,
                        round_num
                    )
                    rebuttal_time = self.tracker.end_operation("rebuttal")
                    progress.update(task, completed=True)

                console.print(f"[green]✓ Author rebuttal complete[/green]")

                # Display rebuttal summary
                rebuttal_preview = author_rebuttal[:300] + "..." if len(author_rebuttal) > 300 else author_rebuttal
                console.print(Panel.fit(
                    rebuttal_preview,
                    title="Author Rebuttal (preview)",
                    border_style="cyan"
                ))

                # Save full rebuttal
                rebuttal_file = self.output_dir / f"rebuttal_round_{round_num}.md"
                rebuttal_file.write_text(author_rebuttal)
                console.print(f"[dim]Saved: {rebuttal_file}[/dim]")

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
                "author_rebuttal": author_rebuttal,  # Include rebuttal
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

            # Save checkpoint for resume capability
            self._save_checkpoint(round_num, current_manuscript, all_rounds)

            # Check if passed
            if moderator_decision["decision"] == "ACCEPT":
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

            previous_manuscript = current_manuscript

            # Generate revision
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
                    round_num
                )
                revision_time = self.tracker.end_operation("revision")
                self.tracker.record_revision_time(revision_time)
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

        # Generate summary and export
        return await self._finalize_workflow(all_rounds)

    async def _generate_initial_manuscript(self) -> str:
        """Generate initial manuscript from topic."""
        console.print("\n[cyan]Generating initial manuscript...[/cyan]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Writer generating manuscript...", total=None)
            self.tracker.start_operation("initial_draft")
            manuscript = await self.writer.write_manuscript(self.topic)
            duration = self.tracker.end_operation("initial_draft")
            # Note: we don't track tokens here as WriterAgent doesn't return them
            # Could be enhanced in the future
            self.tracker.record_initial_draft(duration, 0)
            progress.update(task, completed=True)

        console.print(f"[green]✓ Initial manuscript complete[/green]\n")
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

        # Save complete workflow
        workflow_data = {
            "topic": self.topic,
            "output_directory": str(self.output_dir),
            "max_rounds": self.max_rounds,
            "threshold": self.threshold,
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
            status_callback=status_callback
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
        """Continue workflow from a specific round.

        Args:
            start_round: Round number to resume from
            current_manuscript: Current manuscript state
            all_rounds: Round history

        Returns:
            Workflow results dictionary
        """
        self.tracker.start_workflow()

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

        # Continue iteration from next round
        previous_manuscript = current_manuscript

        for round_num in range(start_round + 1, self.max_rounds + 1):
            console.print("\n" + "="*80 + "\n")

            # Run review
            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Expert reviews in progress...")

            # Get previous reviews and rebuttal
            prev_reviews = all_rounds[-1]['reviews'] if all_rounds else None
            prev_rebuttal = all_rounds[-1].get('author_rebuttal') if all_rounds else None

            reviews, overall_average = await run_review_round(
                current_manuscript,
                round_num,
                self.specialists,
                self.tracker,
                prev_reviews,
                previous_manuscript,
                prev_rebuttal
            )

            if self.status_callback:
                self.status_callback("reviewing", round_num, f"Round {round_num}/{self.max_rounds}: Reviews complete, moderator evaluating...")

            # Moderator decision
            console.print("\n[cyan]Moderator evaluating reviews...[/cyan]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Moderator making decision...", total=None)
                self.tracker.start_operation("moderator")
                moderator_decision = await self.moderator.make_decision(
                    current_manuscript,
                    reviews,
                    round_num,
                    self.max_rounds,
                    previous_rounds=all_rounds
                )
                moderator_time = self.tracker.end_operation("moderator")
                self.tracker.record_moderator_time(moderator_time)
                progress.update(task, completed=True)

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

            # Author rebuttal
            author_rebuttal = None
            if moderator_decision["decision"] != "ACCEPT":
                console.print("\n[cyan]Author writing rebuttal...[/cyan]")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    task = progress.add_task("[cyan]Author responding to reviews...", total=None)
                    self.tracker.start_operation("rebuttal")
                    author_rebuttal = await self.writer.write_rebuttal(
                        current_manuscript,
                        reviews,
                        round_num
                    )
                    rebuttal_time = self.tracker.end_operation("rebuttal")
                    progress.update(task, completed=True)

                console.print(f"[green]✓ Author rebuttal complete[/green]")

                rebuttal_preview = author_rebuttal[:300] + "..." if len(author_rebuttal) > 300 else author_rebuttal
                console.print(Panel.fit(
                    rebuttal_preview,
                    title="Author Rebuttal (preview)",
                    border_style="cyan"
                ))

                rebuttal_file = self.output_dir / f"rebuttal_round_{round_num}.md"
                rebuttal_file.write_text(author_rebuttal)
                console.print(f"[dim]Saved: {rebuttal_file}[/dim]")

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
                "author_rebuttal": author_rebuttal,
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

            # Save checkpoint
            self._save_checkpoint(round_num, current_manuscript, all_rounds)

            # Check if passed
            if moderator_decision["decision"] == "ACCEPT":
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

            previous_manuscript = current_manuscript

            # Generate revision
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
                    round_num
                )
                revision_time = self.tracker.end_operation("revision")
                self.tracker.record_revision_time(revision_time)
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

        # Generate summary and export
        return await self._finalize_workflow(all_rounds)
