"""Full collaborative research workflow - Research → Writing → Review."""

from pathlib import Path
from typing import Optional, Callable
from rich.console import Console

from ..models.author import WriterTeam
from .collaborative_research import CollaborativeResearchPhase
from .manuscript_writing import ManuscriptWritingPhase
from .orchestrator import WorkflowOrchestrator
from ..models.expert import ExpertConfig


console = Console()


class CollaborativeWorkflowOrchestrator:
    """
    Full collaborative workflow orchestrator.

    Phases:
    1. Collaborative Research (lead + coauthors)
    2. Manuscript Writing (sectional, iterative)
    3. Peer Review (external reviewers)
    """

    def __init__(
        self,
        topic: str,
        major_field: str,
        subfield: str,
        writer_team: WriterTeam,
        reviewer_configs: list,
        output_dir: Path,
        max_rounds: int = 3,
        threshold: float = 7.0,
        target_manuscript_length: int = 4000,
        research_cycles: int = 1,
        status_callback: Optional[Callable] = None,
        article_length: str = "full",
        research_type: str = "survey",
        audience_level: str = "professional",
        quiet: bool = False,
        secondary_major: Optional[str] = None,
        secondary_subfield: Optional[str] = None,
    ):
        """Initialize collaborative workflow.

        Args:
            topic: Research topic
            major_field: Major academic field (e.g., "computer_science")
            subfield: Subfield (e.g., "security")
            writer_team: Team of authors (lead + coauthors)
            reviewer_configs: Reviewer configurations (external, not writers)
            output_dir: Output directory
            max_rounds: Max review rounds
            threshold: Acceptance threshold
            target_manuscript_length: Target length in words
            research_cycles: Number of research note iterations (default 1)
            status_callback: Status update callback
            article_length: "full" or "short" — passed to reviewers for adjusted expectations
            research_type: "explainer", "survey", or "original"
            audience_level: "beginner", "intermediate", or "professional"
            secondary_major: Optional secondary major field for interdisciplinary topics
            secondary_subfield: Optional secondary subfield
        """
        self.topic = topic
        self.major_field = major_field
        self.subfield = subfield
        self.secondary_major = secondary_major
        self.secondary_subfield = secondary_subfield
        self.writer_team = writer_team
        self.reviewer_configs = reviewer_configs
        self.output_dir = output_dir
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.target_manuscript_length = target_manuscript_length
        self.research_cycles = research_cycles
        self.status_callback = status_callback
        self.article_length = article_length
        self.research_type = research_type
        self.audience_level = audience_level
        self.quiet = quiet

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Get category name
        from ..categories import get_category_name
        self.category = get_category_name(major_field, subfield)

    async def run(self) -> dict:
        """Run complete collaborative workflow."""

        console.print("\n[bold green]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold green]")
        console.print("[bold green] Collaborative Research Workflow[/bold green]")
        console.print("[bold green]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold green]\n")

        console.print(f"[bold]Topic:[/bold] {self.topic}")
        console.print(f"[bold]Category:[/bold] {self.category}")
        console.print(f"[bold]Lead Author:[/bold] {self.writer_team.lead_author.name} ({self.writer_team.lead_author.model})")
        console.print(f"[bold]Co-Authors:[/bold] {', '.join(f'{ca.name} ({ca.model})' for ca in self.writer_team.coauthors)}")
        console.print(f"[bold]Reviewers:[/bold] {len(self.reviewer_configs)} external reviewers\n")

        # Phase 1: Collaborative Research
        if self.status_callback:
            self.status_callback("research", 0, "Phase 1: Collaborative research in progress...")

        research_phase = CollaborativeResearchPhase(
            topic=self.topic,
            category=self.category,
            writer_team=self.writer_team,
            output_dir=self.output_dir,
            research_cycles=self.research_cycles,
            status_callback=self.status_callback
        )

        research_notes = await research_phase.run()

        # Phase 2: Manuscript Writing
        if self.status_callback:
            self.status_callback("writing_sections", 0, "Phase 2: Writing manuscript sections...")

        writing_phase = ManuscriptWritingPhase(
            topic=self.topic,
            category=self.category,
            writer_team=self.writer_team,
            research_notes=research_notes,
            output_dir=self.output_dir,
            target_length=self.target_manuscript_length,
            status_callback=self.status_callback,
            parallel=True,
            audience_level=self.audience_level,
            research_type=self.research_type,
        )

        manuscript = await writing_phase.run()

        # Phase 3: Peer Review
        console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
        console.print("[bold cyan] Phase 3: Peer Review[/bold cyan]")
        console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

        # Convert manuscript to full text for review (include abstract/TL;DR + references)
        manuscript_text = manuscript.content
        if manuscript.abstract:
            # Determine summary heading based on audience level
            if self.audience_level in ("beginner", "intermediate"):
                summary_heading = "## TL;DR"
            else:
                summary_heading = "## Abstract"
            manuscript_text = f"{summary_heading}\n\n{manuscript.abstract}\n\n---\n\n{manuscript.content}"
        # Append references section if available
        if manuscript.references:
            manuscript_text = f"{manuscript_text}\n\n---\n\n{manuscript.references}"

        # Create review workflow
        category_dict = {"major": self.major_field, "subfield": self.subfield}
        if self.secondary_major:
            category_dict["secondary_major"] = self.secondary_major
        if self.secondary_subfield:
            category_dict["secondary_subfield"] = self.secondary_subfield

        review_workflow = WorkflowOrchestrator(
            topic=self.topic,
            expert_configs=self.reviewer_configs,
            output_dir=self.output_dir,
            max_rounds=self.max_rounds,
            threshold=self.threshold,
            status_callback=self.status_callback,
            category=category_dict,
            article_length=self.article_length,
            audience_level=self.audience_level,
            research_type=self.research_type,
            quiet=self.quiet,
        )

        # Pass phase timings to review workflow for inclusion in output
        review_workflow.phase_timings = [
            research_phase.phase_timing,
            writing_phase.phase_timing,
        ]

        # Pass co-author agents so they can provide revision notes during peer review
        review_workflow.coauthor_agents = writing_phase.coauthor_agents

        # Run review workflow with pre-written manuscript
        review_result = await review_workflow.run(
            initial_manuscript=manuscript_text
        )

        # Combine results
        result = {
            "topic": self.topic,
            "category": self.category,
            "writer_team": self.writer_team.to_dict(),
            "research_notes": research_notes.to_dict(),
            "manuscript": manuscript.to_dict(),
            "review_result": review_result,
            "output_directory": str(self.output_dir)
        }
        if self.secondary_major and self.secondary_subfield:
            from ..categories import get_category_name
            result["secondary_category"] = get_category_name(self.secondary_major, self.secondary_subfield)

        console.print("\n[bold green]✓ Complete workflow finished![/bold green]\n")

        return result
