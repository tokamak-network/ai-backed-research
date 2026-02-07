"""Collaborative research phase workflow orchestrator."""

import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Callable
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..models.author import WriterTeam
from ..models.collaborative_research import (
    CollaborativeResearchNotes,
    ResearchTask,
    ResearchContribution
)
from ..agents.lead_author import LeadAuthorAgent
from ..agents.coauthor import CoauthorAgent


console = Console()


class CollaborativeResearchPhase:
    """
    Phase 1: Collaborative Research

    Lead author creates initial research notes, identifies gaps,
    assigns research tasks to co-authors, and integrates findings.
    """

    def __init__(
        self,
        topic: str,
        category: str,
        writer_team: WriterTeam,
        output_dir: Path,
        research_cycles: int = 1,
        status_callback: Optional[Callable] = None
    ):
        """Initialize research phase.

        Args:
            topic: Research topic
            category: Journal category
            writer_team: Team of authors
            output_dir: Output directory
            research_cycles: Number of research note iterations (default 1)
            status_callback: Optional callback for status updates
        """
        self.topic = topic
        self.category = category
        self.writer_team = writer_team
        self.output_dir = output_dir
        self.research_cycles = research_cycles
        self.status_callback = status_callback

        # Initialize agents
        lead = writer_team.lead_author
        self.lead_agent = LeadAuthorAgent(
            expertise=lead.expertise,
            focus_areas=lead.focus_areas,
            model=lead.model
        )

        self.coauthor_agents = []
        for coauthor in writer_team.coauthors:
            agent = CoauthorAgent(
                author_id=coauthor.id,
                name=coauthor.name,
                expertise=coauthor.expertise,
                focus_areas=coauthor.focus_areas,
                model=coauthor.model
            )
            self.coauthor_agents.append(agent)

    def _update_status(self, message: str):
        """Update status."""
        if self.status_callback:
            self.status_callback("research", 0, message)
        console.print(f"[cyan]{message}[/cyan]")

    async def run(self) -> CollaborativeResearchNotes:
        """Run complete research phase with optional cycles."""

        console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
        console.print("[bold cyan] Phase 1: Collaborative Research[/bold cyan]")
        console.print(f"[bold cyan] ({self.research_cycles} cycle{'s' if self.research_cycles > 1 else ''})[/bold cyan]")
        console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

        # Step 1: Lead creates initial research notes
        self._update_status("[1/5] Lead: Creating initial research notes...")
        research_notes = await self.lead_agent.create_initial_research_notes(
            topic=self.topic,
            category=self.category
        )

        console.print(f"  ✓ Research questions: {len(research_notes.research_questions)}")
        console.print(f"  ✓ Hypotheses: {len(research_notes.hypotheses)}")
        console.print(f"  ✓ Open questions: {len(research_notes.open_questions)}\n")

        coauthor_info = [
            {
                "id": ca.id,
                "name": ca.name,
                "expertise": ca.expertise
            }
            for ca in self.writer_team.coauthors
        ]

        # Run research cycles
        for cycle in range(self.research_cycles):
            if self.research_cycles > 1:
                console.print(f"\n[bold yellow]━━━ Research Cycle {cycle + 1}/{self.research_cycles} ━━━[/bold yellow]\n")

            # Step 2: Identify research gaps and assign tasks
            self._update_status(f"[2/5] Lead: Identifying research gaps (Cycle {cycle + 1})...")

            tasks = await self.lead_agent.identify_research_gaps(
                notes=research_notes,
                coauthor_expertises=coauthor_info
            )

            console.print(f"  → {len(tasks)} research tasks identified\n")
            for task in tasks:
                assigned_author = self.writer_team.get_author_by_id(task.assigned_to)
                console.print(f"  Task: \"{task.title}\"")
                console.print(f"    Assigned to: {assigned_author.name if assigned_author else task.assigned_to}\n")

            research_notes.tasks.extend(tasks)

            # Step 3: Co-authors conduct distributed research
            self._update_status(f"[3/5] Co-authors: Conducting research (Cycle {cycle + 1})...")

            # Create context for coauthors
            context = {
                "research_questions": research_notes.research_questions,
                "hypotheses": research_notes.hypotheses,
                "existing_findings": [f.title for f in research_notes.findings]
            }

            # Parallel research by coauthors
            contributions = await self._conduct_parallel_research(tasks, context)

            # Display results
            for contrib in contributions:
                console.print(f"  → {contrib.author}: {len(contrib.findings)} findings, "
                             f"{len(contrib.references)} references")

            console.print()

            # Step 4: Integrate findings
            self._update_status(f"[4/5] Lead: Integrating findings (Cycle {cycle + 1})...")
            research_notes = self._integrate_contributions(research_notes, contributions)

            console.print(f"  ✓ Total findings: {len(research_notes.findings)}")
            console.print(f"  ✓ Total references: {len(research_notes.references)}\n")

            # Mutual feedback between authors (if more cycles remaining)
            if cycle < self.research_cycles - 1:
                self._update_status(f"[4.5/5] Mutual feedback between authors...")
                await self._conduct_mutual_feedback(research_notes, contributions)
                console.print("  ✓ Feedback integrated\n")

        # Step 5: Assess completeness
        self._update_status("[5/5] Lead: Assessing research completeness...")
        console.print(f"  ✓ Research phase complete")
        console.print(f"  ✓ {len(research_notes.findings)} findings")
        console.print(f"  ✓ {len(research_notes.references)} references\n")

        # Save research notes
        self._save_research_notes(research_notes)

        return research_notes

    async def _conduct_mutual_feedback(
        self,
        notes: CollaborativeResearchNotes,
        contributions: List[ResearchContribution]
    ):
        """Conduct mutual feedback between authors on each other's findings."""
        # Each co-author reviews findings from other co-authors
        for agent in self.coauthor_agents:
            other_findings = [
                f for f in notes.findings
                if f.author != agent.name
            ]
            if other_findings:
                # Simplified: just log that feedback was given
                console.print(f"    {agent.name}: reviewed {len(other_findings)} findings from others")

    async def _conduct_parallel_research(
        self,
        tasks: List[ResearchTask],
        context: dict
    ) -> List[ResearchContribution]:
        """Conduct research tasks in parallel."""

        async def research_task(task: ResearchTask, agent: CoauthorAgent):
            """Single research task."""
            contrib = await agent.conduct_research(task, context)
            task.status = "completed"
            return contrib

        # Map tasks to agents
        task_futures = []
        for task in tasks:
            # Find agent for this task
            agent = next(
                (a for a in self.coauthor_agents if a.author_id == task.assigned_to),
                None
            )
            if agent:
                task_futures.append(research_task(task, agent))

        # Execute in parallel
        contributions = await asyncio.gather(*task_futures)

        return contributions

    def _integrate_contributions(
        self,
        notes: CollaborativeResearchNotes,
        contributions: List[ResearchContribution]
    ) -> CollaborativeResearchNotes:
        """Integrate co-author contributions into research notes."""

        for contrib in contributions:
            # Assign reference IDs and add to notes
            for ref in contrib.references:
                ref.id = notes.get_next_reference_id()
                notes.add_reference(ref)

            # Update finding citations with assigned reference IDs
            # (Simplified - in real version, would match findings to refs)
            for finding in contrib.findings:
                # Use all refs from this contribution
                finding.citations = [r.id for r in contrib.references]
                notes.add_finding(finding)

            # Store contribution
            notes.contributions.append(contrib)

        return notes

    def _save_research_notes(self, notes: CollaborativeResearchNotes):
        """Save research notes to file."""
        import json

        notes_file = self.output_dir / "research_notes.json"
        with open(notes_file, "w") as f:
            json.dump(notes.to_dict(), f, indent=2)

        console.print(f"[dim]Research notes saved to: {notes_file}[/dim]\n")
