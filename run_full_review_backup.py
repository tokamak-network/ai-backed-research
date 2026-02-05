#!/usr/bin/env python3
"""Full iterative peer review workflow with automatic revision."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from research_cli.config import get_config
from research_cli.llm import ClaudeLLM
from research_cli.agents import WriterAgent, ModeratorAgent
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


# Import specialist definitions from demo_review
SPECIALISTS = {
    "cryptography": {
        "name": "Cryptography Expert",
        "provider": "anthropic",
        "model": "claude-sonnet-4.5",
        "system_prompt": """You are a PhD-level cryptography researcher specializing in blockchain systems.
Your expertise includes: cryptographic primitives, zero-knowledge proofs, signature schemes,
security assumptions, attack vectors, and formal security proofs.

When reviewing research, you focus on:
- Cryptographic accuracy and correctness
- Security assumptions and their validity
- Potential attack vectors or vulnerabilities
- Proper use of cryptographic terminology
- References to relevant cryptographic literature

Provide constructive, rigorous feedback."""
    },
    "economics": {
        "name": "Economics Expert",
        "provider": "anthropic",
        "model": "claude-sonnet-4.5",
        "system_prompt": """You are a blockchain economist specializing in mechanism design and tokenomics.
Your expertise includes: game theory, incentive structures, fee markets, MEV, token economics,
and economic security models.

When reviewing research, you focus on:
- Economic incentive alignment
- Fee market design and efficiency
- Game-theoretic considerations
- Token economics and sustainability
- Market dynamics and user behavior

Provide data-driven, quantitative feedback where possible."""
    },
    "distributed_systems": {
        "name": "Distributed Systems Expert",
        "provider": "anthropic",
        "model": "claude-sonnet-4.5",
        "system_prompt": """You are a distributed systems researcher specializing in blockchain infrastructure.
Your expertise includes: consensus protocols, scalability, fault tolerance, network design,
performance optimization, and system architecture.

When reviewing research, you focus on:
- Scalability and performance claims
- System architecture and design patterns
- Fault tolerance and liveness guarantees
- Network efficiency and latency
- Practical implementation considerations

Provide technically rigorous, implementation-focused feedback."""
    }
}


async def generate_review(specialist_id: str, manuscript: str, round_number: int) -> dict:
    """Generate review from a specialist (reuses demo_review logic)."""
    specialist = SPECIALISTS[specialist_id]
    config = get_config()

    provider = specialist["provider"]
    model = specialist["model"]

    llm_config = config.get_llm_config("anthropic", model)
    llm = ClaudeLLM(
        api_key=llm_config.api_key,
        model=llm_config.model,
        base_url=llm_config.base_url
    )

    review_prompt = f"""Review this research manuscript (Round {round_number}) from your expert perspective.

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

    response = await llm.generate(
        prompt=review_prompt,
        system=specialist["system_prompt"],
        temperature=0.3,
        max_tokens=4096
    )

    # Parse JSON
    content = response.content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    review_data = json.loads(content)
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


async def run_review_round(manuscript: str, round_number: int) -> tuple[List[Dict], float]:
    """Run one round of peer review.

    Returns:
        (reviews, overall_average)
    """
    console.print(f"\n[bold cyan]Round {round_number}: Specialist Review[/bold cyan]\n")

    reviews = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        tasks = {}
        for specialist_id in SPECIALISTS.keys():
            specialist_name = SPECIALISTS[specialist_id]["name"]
            task = progress.add_task(f"[cyan]{specialist_name}...", total=None)
            tasks[specialist_id] = task

        # Generate reviews concurrently
        review_tasks = [
            generate_review(specialist_id, manuscript, round_number)
            for specialist_id in SPECIALISTS.keys()
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

    return reviews, overall_average


async def run_full_workflow(
    manuscript_path: Path,
    max_rounds: int = 3,
    threshold: float = 8.0,
    output_dir: Optional[Path] = None
):
    """Run full iterative review workflow.

    Args:
        manuscript_path: Path to initial manuscript
        max_rounds: Maximum review rounds
        threshold: Score threshold for acceptance
        output_dir: Output directory for results
    """
    console.print(Panel.fit(
        "[bold cyan]AI Research Peer Review Workflow[/bold cyan]\n"
        "Iterative revision until quality threshold achieved",
        border_style="cyan"
    ))

    # Setup
    if output_dir is None:
        output_dir = Path("results") / manuscript_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    manuscript = manuscript_path.read_text()
    word_count = len(manuscript.split())

    console.print(f"\n[bold]Initial Manuscript:[/bold] {manuscript_path}")
    console.print(f"Length: {word_count:,} words")
    console.print(f"Max rounds: {max_rounds}")
    console.print(f"Threshold: {threshold}/10\n")

    # Save initial manuscript
    manuscript_v1_path = output_dir / "manuscript_v1.md"
    manuscript_v1_path.write_text(manuscript)
    console.print(f"[dim]Saved: {manuscript_v1_path}[/dim]")

    # Initialize writer agent
    writer = WriterAgent(model="claude-opus-4.5")

    # Track all rounds
    all_rounds = []
    current_manuscript = manuscript

    # Iterative review loop
    for round_num in range(1, max_rounds + 1):
        console.print("\n" + "="*80 + "\n")

        # Run review
        reviews, overall_average = await run_review_round(current_manuscript, round_num)

        # Save round data
        round_data = {
            "round": round_num,
            "manuscript_version": f"v{round_num}",
            "word_count": len(current_manuscript.split()),
            "reviews": reviews,
            "overall_average": round(overall_average, 1),
            "threshold": threshold,
            "passed": overall_average >= threshold,
            "timestamp": datetime.now().isoformat()
        }

        round_file = output_dir / f"round_{round_num}.json"
        with open(round_file, "w") as f:
            json.dump(round_data, f, indent=2)
        console.print(f"[dim]Saved: {round_file}[/dim]")

        all_rounds.append(round_data)

        # Check if passed
        if overall_average >= threshold:
            console.print(f"\n[bold green]✓ PASSED[/bold green] (Score: {overall_average:.1f} >= {threshold})")
            console.print(f"[green]Quality threshold achieved in {round_num} round(s)![/green]\n")

            # Save final manuscript
            final_path = output_dir / "manuscript_final.md"
            final_path.write_text(current_manuscript)
            console.print(f"[green]Final manuscript saved:[/green] {final_path}")
            break

        # Check if max rounds reached
        if round_num >= max_rounds:
            console.print(f"\n[yellow]⚠ MAX ROUNDS REACHED[/yellow]")
            console.print(f"[yellow]Final score: {overall_average:.1f} (threshold: {threshold})[/yellow]\n")

            # Save best attempt
            final_path = output_dir / f"manuscript_final_v{round_num}.md"
            final_path.write_text(current_manuscript)
            console.print(f"[yellow]Best attempt saved:[/yellow] {final_path}")
            break

        # Need revision
        console.print(f"\n[yellow]⚠ REVISION NEEDED[/yellow] (Score: {overall_average:.1f} < {threshold})")
        console.print(f"[cyan]Round {round_num + 1}: Generating revision...[/cyan]\n")

        # Generate revision
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Writer revising manuscript...", total=None)
            revised_manuscript = await writer.revise_manuscript(
                current_manuscript,
                reviews,
                round_num
            )
            progress.update(task, completed=True)

        new_word_count = len(revised_manuscript.split())
        word_change = new_word_count - len(current_manuscript.split())
        console.print(f"[green]✓ Revision complete[/green]")
        console.print(f"New length: {new_word_count:,} words ([{word_change:+,}])\n")

        # Save revised manuscript
        manuscript_path_next = output_dir / f"manuscript_v{round_num + 1}.md"
        manuscript_path_next.write_text(revised_manuscript)
        console.print(f"[dim]Saved: {manuscript_path_next}[/dim]")

        current_manuscript = revised_manuscript

    # Generate summary
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

    # Save complete workflow
    workflow_data = {
        "topic": manuscript_path.stem.replace("-", " ").title(),
        "initial_manuscript": str(manuscript_path),
        "output_directory": str(output_dir),
        "max_rounds": max_rounds,
        "threshold": threshold,
        "rounds": all_rounds,
        "final_score": all_rounds[-1]["overall_average"],
        "passed": all_rounds[-1]["passed"],
        "total_rounds": len(all_rounds),
        "timestamp": datetime.now().isoformat()
    }

    workflow_file = output_dir / "workflow_complete.json"
    with open(workflow_file, "w") as f:
        json.dump(workflow_data, f, indent=2)

    console.print(f"\n[bold green]✓ Complete workflow saved:[/bold green] {workflow_file}")

    # Cost estimate
    total_tokens = sum(
        sum(r.get("tokens", 0) for r in rd["reviews"])
        for rd in all_rounds
    )
    estimated_cost = (total_tokens / 1000) * 0.003
    console.print(f"[dim]Total tokens: {total_tokens:,} (~${estimated_cost:.2f})[/dim]\n")

    # Export to web automatically
    console.print("[cyan]Exporting results to web viewer...[/cyan]")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "export_to_web.py"],
            capture_output=True,
            text=True,
            check=True
        )
        console.print("[green]✓ Results exported to web/data/[/green]")
        console.print("[dim]View at: http://localhost:8080/web/review-viewer.html[/dim]\n")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not export to web: {e}[/yellow]\n")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run full iterative peer review workflow")
    parser.add_argument("manuscript", type=Path, help="Path to manuscript file")
    parser.add_argument("--max-rounds", type=int, default=3, help="Maximum review rounds")
    parser.add_argument("--threshold", type=float, default=8.0, help="Score threshold")
    parser.add_argument("--output", type=Path, help="Output directory")

    args = parser.parse_args()

    if not args.manuscript.exists():
        console.print(f"[red]Error: Manuscript not found: {args.manuscript}[/red]")
        return 1

    # Check API key
    config = get_config()
    if not config.anthropic_api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY not configured[/red]")
        return 1

    try:
        await run_full_workflow(
            args.manuscript,
            max_rounds=args.max_rounds,
            threshold=args.threshold,
            output_dir=args.output
        )
        return 0
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
