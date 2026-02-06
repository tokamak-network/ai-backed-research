#!/usr/bin/env python3
"""Test multi-stage writing process."""

import asyncio
from pathlib import Path
from rich.console import Console
from rich.table import Table

from research_cli.agents.research_planner import ResearchPlannerAgent
from research_cli.agents.writer import WriterAgent
from research_cli.agents.integration_editor import IntegrationEditorAgent
from research_cli.models.section import WritingContext

console = Console()


async def test_multi_stage_writing():
    """Test complete multi-stage writing workflow."""

    topic = "Ethereum EIP-4844 Proto-Danksharding"

    console.print("\n[bold cyan]MULTI-STAGE WRITING TEST[/bold cyan]\n")
    console.print(f"Topic: {topic}\n")

    # Stage 1: Planning
    console.print("[bold]Stage 1: Research Planning[/bold]")
    planner = ResearchPlannerAgent()

    console.print("  Creating research plan...")
    plan = await planner.create_research_plan(topic, target_length="short")

    console.print(f"  ✓ Plan created: {len(plan.sections)} sections")
    console.print(f"  ✓ Estimated total: ~{plan.total_estimated_tokens//250} words\n")

    # Display plan
    table = Table(title="Research Plan")
    table.add_column("Order", style="cyan")
    table.add_column("Section", style="green")
    table.add_column("Key Points", style="yellow")
    table.add_column("Est. Words", justify="right")

    for section in plan.get_ordered_sections():
        key_points_str = "\n".join(f"• {p[:50]}..." if len(p) > 50 else f"• {p}" for p in section.key_points[:2])
        table.add_row(
            str(section.order),
            section.title,
            key_points_str,
            f"{section.estimated_tokens//200}"
        )

    console.print(table)
    console.print()

    # Stage 2: Section-by-Section Writing
    console.print("[bold]Stage 2: Section Writing[/bold]")
    writer = WriterAgent()

    sections = []
    for section_spec in plan.get_ordered_sections()[:3]:  # Test first 3 sections only
        console.print(f"  Writing: {section_spec.title}...")

        context = WritingContext(
            research_plan=plan,
            previous_sections=sections,
            section_spec=section_spec
        )

        section_output = await writer.write_section(context)
        sections.append(section_output)

        console.print(f"  ✓ Complete: {section_output.word_count} words, {section_output.tokens_used} tokens")

    console.print()
    total_words = sum(s.word_count for s in sections)
    console.print(f"  Total sections written: {len(sections)}")
    console.print(f"  Total word count: {total_words}\n")

    # Stage 3: Integration
    console.print("[bold]Stage 3: Section Integration[/bold]")
    integrator = IntegrationEditorAgent()

    console.print("  Integrating sections...")
    result = await integrator.integrate_sections(sections, plan)

    console.print(f"  ✓ Integration complete")
    console.print(f"  ✓ Final manuscript: {result.word_count} words")
    console.print(f"  ✓ Changes: {', '.join(result.changes_made)}\n")

    # Save results
    output_dir = Path("results/multi-stage-test")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save plan
    import json
    with open(output_dir / "research_plan.json", "w") as f:
        json.dump({
            "topic": plan.topic,
            "research_questions": plan.research_questions,
            "sections": [
                {
                    "id": s.id,
                    "title": s.title,
                    "key_points": s.key_points,
                    "estimated_tokens": s.estimated_tokens,
                    "order": s.order
                }
                for s in plan.sections
            ]
        }, f, indent=2)

    # Save individual sections
    for section in sections:
        section_file = output_dir / f"section_{section.metadata['order']}_{section.section_id}.md"
        section_file.write_text(section.content)

    # Save integrated manuscript
    manuscript_file = output_dir / "manuscript_integrated.md"
    manuscript_file.write_text(result.manuscript)

    console.print(f"[bold green]✓ Test Complete[/bold green]")
    console.print(f"\nOutput saved to: {output_dir}")
    console.print(f"  - research_plan.json")
    console.print(f"  - section_*.md ({len(sections)} files)")
    console.print(f"  - manuscript_integrated.md\n")

    # Summary
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Sections planned: {len(plan.sections)}")
    console.print(f"  Sections written: {len(sections)}")
    console.print(f"  Total words: {total_words} → {result.word_count} (integrated)")
    console.print(f"  Word change: {((result.word_count/total_words)-1)*100:+.1f}%")


if __name__ == "__main__":
    asyncio.run(test_multi_stage_writing())
