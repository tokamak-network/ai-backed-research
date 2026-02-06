#!/usr/bin/env python3
"""Test research notes → paper writing workflow."""

import asyncio
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from research_cli.agents.research_notes_agent import ResearchNotesAgent
from research_cli.agents.data_analysis_agent import DataAnalysisAgent
from research_cli.agents.paper_writer_agent import PaperWriterAgent
from research_cli.agents.integration_editor import IntegrationEditorAgent

console = Console()


async def test_research_notes_workflow():
    """Test complete research notes to paper workflow."""

    topic = "Ethereum EIP-4844 Blob Transaction Economics"
    research_questions = [
        "How much does EIP-4844 reduce L2 transaction costs?",
        "What is the theoretical maximum throughput with blob transactions?",
        "How does the blob gas market work?"
    ]

    output_dir = Path("results/research-notes-test")
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print("\n[bold cyan]RESEARCH NOTES → PAPER WORKFLOW TEST[/bold cyan]\n")
    console.print(Panel(f"[bold]Topic:[/bold] {topic}", style="cyan"))

    # ==================
    # PHASE 1: RESEARCH
    # ==================
    console.print("\n[bold]═══ PHASE 1: RESEARCH & NOTES ═══[/bold]\n")

    notes_agent = ResearchNotesAgent()
    data_agent = DataAnalysisAgent()

    # Start notebook
    console.print("📓 Starting research notebook...")
    notebook = await notes_agent.start_research(topic, research_questions)
    console.print("✓ Notebook initialized\n")

    # Literature review
    console.print("📚 Conducting literature review...")
    lit_notes = await notes_agent.literature_search(
        notebook,
        "EIP-4844 proto-danksharding blob transactions"
    )
    notebook.literature_notes.extend(lit_notes)
    console.print(f"✓ Reviewed {len(lit_notes)} sources\n")

    # Data analysis
    console.print("📊 Performing data analysis...")
    notebook.artifacts_dir = output_dir / "artifacts"

    for question in research_questions[:2]:  # Test 2 questions
        console.print(f"  Analyzing: {question[:60]}...")
        analysis_note = await data_agent.perform_analysis(
            question,
            topic,
            notebook.artifacts_dir
        )
        notebook.data_analysis_notes.append(analysis_note)
        console.print(f"  ✓ {len(analysis_note.findings)} findings, {len(analysis_note.visualizations)} charts")

    console.print(f"\n✓ Data analysis complete\n")

    # Record observations
    console.print("💡 Recording observations...")
    obs1 = await notes_agent.record_observation(
        notebook,
        "EIP-4844 provides significant cost reduction for L2s",
        ["Data shows 90%+ cost reduction", "Multiple protocols adopted quickly"]
    )
    notebook.observations.append(obs1)
    console.print("✓ Observations recorded\n")

    # Identify gaps
    console.print("🔍 Identifying research gaps...")
    questions = await notes_agent.identify_gaps(notebook)
    notebook.questions.extend(questions)
    console.print(f"✓ Identified {len(questions)} gaps\n")

    # Save notebook
    notebook.status = "ready_for_paper"
    notebook_md = notebook.to_markdown()
    notebook_file = output_dir / "research_notes.md"
    notebook_file.write_text(notebook_md)

    stats = notebook.get_statistics()
    console.print(Panel(
        f"""[bold]Research Complete![/bold]

Literature Sources: {stats['literature_sources']}
Data Analyses: {stats['data_analyses']}
Visualizations: {stats['visualizations']}
Observations: {stats['observations']}
Open Questions: {stats['open_questions']}

Notebook saved: {notebook_file}""",
        style="green"
    ))

    # ==================
    # PHASE 2: PAPER WRITING
    # ==================
    console.print("\n[bold]═══ PHASE 2: PAPER WRITING ═══[/bold]\n")

    paper_writer = PaperWriterAgent()
    integrator = IntegrationEditorAgent()

    # Plan paper
    console.print("📋 Planning paper structure...")
    plan = await paper_writer.plan_paper_structure(notebook)
    console.print(f"✓ Planned {len(plan.sections)} sections\n")

    # Write paper
    console.print("✍️  Writing paper sections...")
    sections = []

    for section_spec in plan.get_ordered_sections()[:3]:  # Test first 3 sections
        console.print(f"  Writing: {section_spec.title}...")
        section_output = await paper_writer.write_section_from_notes(
            section_spec,
            notebook,
            previous_sections=sections
        )
        sections.append(section_output)
        console.print(f"  ✓ {section_output.word_count} words")

        # Save section
        section_file = output_dir / f"section_{section_spec.order}_{section_spec.id}.md"
        section_file.write_text(section_output.content)

    console.print(f"\n✓ Sections written\n")

    # Integrate
    console.print("🔗 Integrating sections...")
    result = await integrator.integrate_sections(sections, plan)
    console.print(f"✓ Integration complete: {result.word_count} words\n")

    # Save final paper
    paper_file = output_dir / "paper_final.md"
    paper_file.write_text(result.manuscript)

    # ==================
    # SUMMARY
    # ==================
    console.print("\n[bold green]✓ WORKFLOW COMPLETE[/bold green]\n")

    console.print(Panel(
        f"""[bold]Output Files:[/bold]

Research Notes:
  • {output_dir}/research_notes.md ({len(notebook_md.split())} words)
  • {output_dir}/artifacts/ ({stats['visualizations']} charts)

Paper Sections:
  • {output_dir}/section_*.md ({len(sections)} files)

Final Paper:
  • {output_dir}/paper_final.md ({result.word_count} words)

[bold]Comparison:[/bold]
  Research Notes: {len(notebook_md.split())} words (raw)
  Final Paper: {result.word_count} words (polished)
  Ratio: {len(notebook_md.split())/result.word_count:.2f}x compression""",
        style="cyan"
    ))

    # Show sample comparison
    console.print("\n[bold]Sample: Research Notes vs. Paper[/bold]\n")

    console.print("[yellow]Research Notes (raw):[/yellow]")
    console.print(notebook_md[:400] + "...\n")

    console.print("[green]Final Paper (polished):[/green]")
    console.print(result.manuscript[:400] + "...")


if __name__ == "__main__":
    asyncio.run(test_research_notes_workflow())
