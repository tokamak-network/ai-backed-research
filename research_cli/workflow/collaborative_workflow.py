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
        threshold: float = 8.0,
        target_manuscript_length: int = 4000,
        research_cycles: int = 1,
        status_callback: Optional[Callable] = None
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
        """
        self.topic = topic
        self.major_field = major_field
        self.subfield = subfield
        self.writer_team = writer_team
        self.reviewer_configs = reviewer_configs
        self.output_dir = output_dir
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.target_manuscript_length = target_manuscript_length
        self.research_cycles = research_cycles
        self.status_callback = status_callback

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
        console.print(f"[bold]Lead Author:[/bold] {self.writer_team.lead_author.name}")
        console.print(f"[bold]Co-Authors:[/bold] {', '.join(ca.name for ca in self.writer_team.coauthors)}")
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
            status_callback=self.status_callback
        )

        manuscript = await writing_phase.run()

        # Phase 3: Peer Review
        console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
        console.print("[bold cyan] Phase 3: Peer Review[/bold cyan]")
        console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

        # Convert manuscript to text for review
        manuscript_text = manuscript.content

        # Create review workflow
        review_workflow = WorkflowOrchestrator(
            topic=self.topic,
            expert_configs=self.reviewer_configs,
            output_dir=self.output_dir,
            max_rounds=self.max_rounds,
            threshold=self.threshold,
            status_callback=self.status_callback
        )

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

        console.print("\n[bold green]✓ Complete workflow finished![/bold green]\n")

        return result
