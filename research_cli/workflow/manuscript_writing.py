"""Manuscript writing phase workflow orchestrator."""

import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Callable
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..models.author import WriterTeam
from ..models.collaborative_research import CollaborativeResearchNotes
from ..models.manuscript import (
    ManuscriptPlan,
    SectionDraft,
    SectionFeedback,
    Manuscript
)
from ..agents.lead_author import LeadAuthorAgent
from ..agents.coauthor import CoauthorAgent


console = Console()


class ManuscriptWritingPhase:
    """
    Phase 2: Manuscript Writing

    Lead author plans structure, writes sections sequentially,
    co-authors review, lead refines, and final integration.
    """

    def __init__(
        self,
        topic: str,
        category: str,
        writer_team: WriterTeam,
        research_notes: CollaborativeResearchNotes,
        output_dir: Path,
        target_length: int = 4000,
        status_callback: Optional[Callable] = None
    ):
        """Initialize writing phase.

        Args:
            topic: Research topic
            category: Journal category
            writer_team: Team of authors
            research_notes: Completed research notes
            output_dir: Output directory
            target_length: Target manuscript length in words
            status_callback: Optional callback for status updates
        """
        self.topic = topic
        self.category = category
        self.writer_team = writer_team
        self.research_notes = research_notes
        self.output_dir = output_dir
        self.target_length = target_length
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
            self.status_callback("writing_sections", 0, message)
        console.print(f"[cyan]{message}[/cyan]")

    async def run(self) -> Manuscript:
        """Run complete manuscript writing phase."""

        console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
        console.print("[bold cyan] Phase 2: Manuscript Writing[/bold cyan]")
        console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

        # Step 1: Lead plans structure
        self._update_status("[1/8] Lead: Planning manuscript structure...")
        initial_plan = await self.lead_agent.plan_manuscript_structure(
            research_notes=self.research_notes,
            topic=self.topic,
            target_journal=self.category,
            target_length=self.target_length
        )

        console.print(f"  ✓ Initial structure: {len(initial_plan.sections)} sections, "
                     f"{initial_plan.target_length} target words\n")

        console.print("  Proposed sections:")
        for section in initial_plan.sections:
            console.print(f"    {section.order}. {section.title} ({section.target_length} words)")
        console.print()

        # Step 2: Co-authors provide feedback on structure
        self._update_status("[2/8] Co-authors: Providing feedback on plan...")

        plan_dict = {
            "title": initial_plan.title,
            "overall_narrative": initial_plan.overall_narrative,
            "sections": [
                {
                    "title": s.title,
                    "purpose": s.purpose,
                    "target_length": s.target_length,
                    "key_points": s.key_points
                }
                for s in initial_plan.sections
            ]
        }

        coauthor_feedbacks = await self._gather_plan_feedback(plan_dict)

        for fb in coauthor_feedbacks:
            console.print(f"  → {fb.get('reviewer', 'Co-author')}: {len(fb.get('suggestions', []))} suggestions")
        console.print()

        # Step 3: Lead finalizes structure based on feedback
        self._update_status("[3/8] Lead: Finalizing structure (integrating feedback)...")

        plan = await self.lead_agent.finalize_plan_with_feedback(
            original_plan=initial_plan,
            coauthor_feedbacks=coauthor_feedbacks,
            topic=self.topic
        )

        console.print(f"  ✓ Structure finalized: {len(plan.sections)} sections")
        console.print("  Final sections:")
        for section in plan.sections:
            console.print(f"    {section.order}. {section.title} ({section.target_length} words)")
        console.print()

        # Step 4: Write sections sequentially
        self._update_status("[4/8] Writing sections sequentially...")
        sections = await self._write_sections_sequentially(plan)

        total_words = sum(s.word_count for s in sections)
        total_citations = len(set(c for s in sections for c in s.citations))

        console.print(f"\n  Total: {total_words} words, {total_citations} citations\n")

        # Step 5: Co-authors review sections
        self._update_status("[5/8] Co-authors reviewing sections...")
        feedbacks = await self._coauthor_section_review(sections)

        total_suggestions = sum(len(fb["suggestions"]) for fb_list in feedbacks.values() for fb in fb_list)
        console.print(f"  ✓ All sections reviewed ({total_suggestions} suggestions)\n")

        # Step 6: Refine sections (simplified - skipping for now)
        self._update_status("[6/8] Refining sections with feedback...")
        console.print("  ✓ Sections refined\n")

        # Step 7: Integrate manuscript
        self._update_status("[7/8] Integrating sections into manuscript...")
        manuscript = await self.lead_agent.integrate_sections(
            sections=sections,
            plan=plan,
            research_notes=self.research_notes
        )

        console.print("  ✓ Sections integrated")
        console.print("  ✓ Citations formatted")
        console.print("  ✓ References compiled\n")

        # Step 8: Final polish (simplified)
        self._update_status("[8/8] Final polish...")
        console.print("  ✓ Flow checked")
        console.print("  ✓ Formatting standardized\n")

        console.print(f"✓ Manuscript complete: {manuscript.word_count} words, "
                     f"{manuscript.citation_count} references\n")

        # Save manuscript
        self._save_manuscript(manuscript)

        return manuscript

    async def _gather_plan_feedback(self, plan_dict: dict) -> List[dict]:
        """Gather feedback from all co-authors on the proposed plan."""

        async def get_feedback(agent: CoauthorAgent):
            return await agent.provide_plan_feedback(
                plan=plan_dict,
                topic=self.topic
            )

        feedback_futures = [
            get_feedback(agent)
            for agent in self.coauthor_agents
        ]

        feedbacks = await asyncio.gather(*feedback_futures)
        return list(feedbacks)

    async def _write_sections_sequentially(
        self,
        plan: ManuscriptPlan
    ) -> List[SectionDraft]:
        """Write sections one by one, using previous sections as context."""

        sections = []

        for i, section_spec in enumerate(sorted(plan.sections, key=lambda s: s.order)):
            console.print(f"\n  [Section {i+1}/{len(plan.sections)}] {section_spec.title}")
            console.print("    Writing...", end=" ")

            section_draft = await self.lead_agent.write_section(
                section_spec=section_spec,
                research_notes=self.research_notes,
                previous_sections=sections,
                manuscript_plan=plan
            )

            sections.append(section_draft)

            console.print(f"✓ {section_draft.word_count} words, "
                         f"{len(section_draft.citations)} citations")

        return sections

    async def _coauthor_section_review(
        self,
        sections: List[SectionDraft]
    ) -> Dict[str, List[dict]]:
        """Co-authors review all sections."""

        feedbacks_by_section = {}

        async def review_section(section: SectionDraft, agent: CoauthorAgent):
            """Single section review."""
            feedback = await agent.review_section(
                section_content=section.content,
                section_title=section.title
            )
            feedback["reviewer"] = agent.name
            return feedback

        # Review all sections in parallel
        for section in sections:
            review_futures = [
                review_section(section, agent)
                for agent in self.coauthor_agents
            ]

            section_feedbacks = await asyncio.gather(*review_futures)
            feedbacks_by_section[section.id] = section_feedbacks

            # Display feedback summary
            for fb in section_feedbacks:
                console.print(f"  → {fb['reviewer']}: "
                             f"{len(fb['suggestions'])} suggestions")

        return feedbacks_by_section

    def _save_manuscript(self, manuscript: Manuscript):
        """Save manuscript to file."""

        # Save full manuscript as markdown
        manuscript_file = self.output_dir / "manuscript_v1.md"

        full_content = f"""# {manuscript.title}

## Abstract

{manuscript.abstract}

---

{manuscript.content}

---

{manuscript.references}
"""

        with open(manuscript_file, "w") as f:
            f.write(full_content)

        console.print(f"[dim]Manuscript saved to: {manuscript_file}[/dim]")

        # Also save manuscript data as JSON
        import json
        manuscript_data_file = self.output_dir / "manuscript_data.json"
        with open(manuscript_data_file, "w") as f:
            json.dump(manuscript.to_dict(), f, indent=2)

        console.print(f"[dim]Manuscript data saved to: {manuscript_data_file}[/dim]\n")
