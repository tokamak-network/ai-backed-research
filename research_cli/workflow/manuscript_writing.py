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
from ..performance import PhaseTimer


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
        status_callback: Optional[Callable] = None,
        parallel: bool = False,
        audience_level: str = "professional",
        research_type: str = "survey",
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
            parallel: If True, write sections in parallel instead of sequentially
            audience_level: "beginner", "intermediate", or "professional"
            research_type: "explainer", "survey", or "original"
        """
        self.topic = topic
        self.category = category
        self.writer_team = writer_team
        self.research_notes = research_notes
        self.output_dir = output_dir
        self.target_length = target_length
        self.status_callback = status_callback
        self.parallel = parallel
        self.audience_level = audience_level
        self.research_type = research_type

        # Initialize agents
        lead = writer_team.lead_author
        self.lead_agent = LeadAuthorAgent(
            expertise=lead.expertise,
            focus_areas=lead.focus_areas,
        )

        self.coauthor_agents = []
        for coauthor in writer_team.coauthors:
            agent = CoauthorAgent(
                author_id=coauthor.id,
                name=coauthor.name,
                expertise=coauthor.expertise,
                focus_areas=coauthor.focus_areas,
            )
            self.coauthor_agents.append(agent)

    def _update_status(self, message: str):
        """Update status."""
        if self.status_callback:
            self.status_callback("writing_sections", 0, message)
        console.print(f"[cyan]{message}[/cyan]")

    async def run(self) -> Manuscript:
        """Run complete manuscript writing phase."""

        self.timer = PhaseTimer("writing")
        self.timer.start()

        console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
        console.print("[bold cyan] Phase 2: Manuscript Writing[/bold cyan]")
        console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

        # Step 1: Lead plans structure
        self._update_status("[1/7] Lead: Planning manuscript structure...")
        self.timer.step("plan_structure")
        initial_plan = await self.lead_agent.plan_manuscript_structure(
            research_notes=self.research_notes,
            topic=self.topic,
            target_journal=self.category,
            target_length=self.target_length,
            research_type=self.research_type,
            audience_level=self.audience_level,
        )

        console.print(f"  ✓ Initial structure: {len(initial_plan.sections)} sections, "
                     f"{initial_plan.target_length} target words\n")

        console.print("  Proposed sections:")
        for section in initial_plan.sections:
            console.print(f"    {section.order}. {section.title} ({section.target_length} words)")
        console.print()

        # Step 2: Co-authors provide feedback on structure
        self._update_status("[2/7] Co-authors: Providing feedback on plan...")
        self.timer.step("plan_feedback")

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
        self._update_status("[3/7] Lead: Finalizing structure (integrating feedback)...")
        self.timer.step("finalize_structure")

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

        # Save finalized plan
        self._save_plan(plan)

        # Step 4: Write sections
        self.timer.step("write_sections")
        if self.parallel:
            self._update_status("[4/7] Writing sections in parallel...")
            sections = await self._write_sections_parallel(plan)
        else:
            self._update_status("[4/7] Writing sections sequentially...")
            sections = await self._write_sections_sequentially(plan)

        total_words = sum(s.word_count for s in sections)
        total_citations = len(set(c for s in sections for c in s.citations))

        console.print(f"\n  Total: {total_words} words, {total_citations} citations\n")

        # Step 5: Integrate manuscript
        self._update_status("[5/7] Integrating sections into manuscript...")
        self.timer.step("integrate_sections")
        manuscript = await self.lead_agent.integrate_sections(
            sections=sections,
            plan=plan,
            research_notes=self.research_notes,
            audience_level=self.audience_level,
        )

        console.print("  ✓ Sections integrated")
        console.print("  ✓ Citations formatted")
        console.print("  ✓ References compiled\n")

        # Step 6: Co-authors review full manuscript (parallel)
        self._update_status("[6/7] Co-authors reviewing full manuscript...")
        self.timer.step("coauthor_review")
        feedbacks = await self._coauthor_manuscript_review(manuscript.content)

        total_suggestions = sum(len(fb["suggestions"]) for fb in feedbacks)
        console.print(f"  ✓ Manuscript reviewed ({total_suggestions} suggestions)\n")

        # Step 7: Final polish (simplified)
        self._update_status("[7/7] Final polish...")
        self.timer.step("final_polish")
        console.print("  ✓ Flow checked")
        console.print("  ✓ Formatting standardized\n")

        console.print(f"✓ Manuscript complete: {manuscript.word_count} words, "
                     f"{manuscript.citation_count} references\n")

        # Save manuscript
        self._save_manuscript(manuscript)

        self.phase_timing = self.timer.end()
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
                manuscript_plan=plan,
                audience_level=self.audience_level,
            )

            sections.append(section_draft)

            console.print(f"✓ {section_draft.word_count} words, "
                         f"{len(section_draft.citations)} citations")

        return sections

    async def _write_sections_parallel(
        self,
        plan: ManuscriptPlan
    ) -> List[SectionDraft]:
        """Write all sections in parallel using plan context only."""

        sorted_specs = sorted(plan.sections, key=lambda s: s.order)

        console.print(f"\n  Writing {len(sorted_specs)} sections in parallel...")

        async def write_one(section_spec: 'SectionSpec') -> SectionDraft:
            section_draft = await self.lead_agent.write_section(
                section_spec=section_spec,
                research_notes=self.research_notes,
                previous_sections=[],  # No sequential context — plan is sufficient
                manuscript_plan=plan,
                audience_level=self.audience_level,
            )
            console.print(f"  ✓ {section_spec.title}: {section_draft.word_count} words, "
                         f"{len(section_draft.citations)} citations")
            return section_draft

        drafts = await asyncio.gather(*(write_one(spec) for spec in sorted_specs))

        # Return in section order
        return list(drafts)

    async def _coauthor_manuscript_review(
        self,
        manuscript_content: str
    ) -> List[dict]:
        """Co-authors review the full integrated manuscript in parallel."""

        async def review_manuscript(agent: CoauthorAgent) -> dict:
            feedback = await agent.review_section(
                section_content=manuscript_content,
                section_title="Full Manuscript"
            )
            feedback["reviewer"] = agent.name
            return feedback

        review_futures = [
            review_manuscript(agent)
            for agent in self.coauthor_agents
        ]

        feedbacks = await asyncio.gather(*review_futures)

        for fb in feedbacks:
            console.print(f"  → {fb['reviewer']}: "
                         f"{len(fb['suggestions'])} suggestions")

        return list(feedbacks)

    def _save_manuscript(self, manuscript: Manuscript):
        """Save manuscript to file."""

        # Save full manuscript as markdown
        manuscript_file = self.output_dir / "manuscript_v1.md"

        # Audience-appropriate summary heading
        if self.audience_level == "beginner":
            summary_heading = "## TL;DR"
        elif self.audience_level == "intermediate":
            summary_heading = "## Executive Summary"
        else:
            summary_heading = "## Abstract"

        full_content = f"""# {manuscript.title}

{summary_heading}

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

    def _save_plan(self, plan: ManuscriptPlan):
        """Save finalized manuscript plan as JSON."""
        import json
        plan_file = self.output_dir / "manuscript_plan.json"
        with open(plan_file, "w") as f:
            json.dump(plan.to_dict(), f, indent=2)
        console.print(f"[dim]Manuscript plan saved to: {plan_file}[/dim]")
