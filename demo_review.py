#!/usr/bin/env python3
"""Demo: Review existing research report with specialist AIs."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from research_cli.config import get_config
from research_cli.llm import ClaudeLLM, GeminiLLM, OpenAILLM
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.markdown import Markdown

console = Console()


# Specialist system prompts
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
        "provider": "anthropic",  # Using Claude for all in demo (can change to "google" if Gemini key available)
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
        "provider": "anthropic",  # Using Claude for all in demo
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

# Review criteria
CRITERIA = [
    "accuracy",      # Factual correctness, no hallucinations
    "completeness",  # Covers all important aspects
    "clarity",       # Well-structured, understandable
    "novelty",       # Original insights beyond existing literature
    "rigor"          # Proper methodology, citations, evidence
]


async def generate_review(specialist_id: str, manuscript: str) -> dict:
    """Generate review from a specialist.

    Args:
        specialist_id: ID of specialist (cryptography, economics, distributed_systems)
        manuscript: Full manuscript text

    Returns:
        Dictionary with scores and feedback
    """
    specialist = SPECIALISTS[specialist_id]
    config = get_config()

    # Get LLM for this specialist
    provider = specialist["provider"]
    model = specialist["model"]

    if provider == "anthropic":
        llm_config = config.get_llm_config("anthropic", model)
        llm = ClaudeLLM(api_key=llm_config.api_key, model=llm_config.model, base_url=llm_config.base_url)
    elif provider == "google":
        llm_config = config.get_llm_config("google", model)
        llm = GeminiLLM(api_key=llm_config.api_key, model=llm_config.model)
    elif provider == "openai":
        llm_config = config.get_llm_config("openai", model)
        llm = OpenAILLM(api_key=llm_config.api_key, model=llm_config.model)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    # Generate review
    review_prompt = f"""Review this research manuscript from your expert perspective.

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

Be honest and constructive. Focus on your domain of expertise."""

    response = await llm.generate(
        prompt=review_prompt,
        system=specialist["system_prompt"],
        temperature=0.3,  # Lower temperature for consistent scoring
        max_tokens=4096
    )

    # Parse JSON response
    try:
        # Extract JSON from response (handle markdown code blocks)
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        review_data = json.loads(content)

        # Calculate average score
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
    except json.JSONDecodeError as e:
        console.print(f"[red]Failed to parse JSON from {specialist['name']}[/red]")
        console.print(f"Response: {response.content[:500]}")
        raise


async def review_manuscript(manuscript_path: Path):
    """Run full review workflow on a manuscript.

    Args:
        manuscript_path: Path to manuscript file
    """
    # Read manuscript
    console.print(f"\n[bold cyan]Reading manuscript:[/bold cyan] {manuscript_path}")
    manuscript = manuscript_path.read_text()
    word_count = len(manuscript.split())
    console.print(f"Length: {word_count:,} words\n")

    # Run reviews in parallel
    console.print("[bold]Generating specialist reviews...[/bold]\n")

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
            generate_review(specialist_id, manuscript)
            for specialist_id in SPECIALISTS.keys()
        ]

        for i, review_result in enumerate(asyncio.as_completed(review_tasks)):
            review = await review_result
            reviews.append(review)
            specialist_id = review["specialist"]
            progress.update(tasks[specialist_id], completed=True)
            console.print(f"[green]✓[/green] {review['specialist_name']} complete")

    # Calculate overall scores
    overall_average = sum(r["average"] for r in reviews) / len(reviews)
    threshold = 8.0
    passed = overall_average >= threshold

    console.print("\n" + "="*80 + "\n")

    # Display results
    console.print(Panel.fit(
        f"[bold]Overall Score: {overall_average:.1f}/10[/bold]\n"
        f"Threshold: {threshold}/10\n"
        f"Status: {'[green]✓ PASS[/green]' if passed else '[yellow]⚠ REVISION NEEDED[/yellow]'}",
        title="Review Results",
        border_style="green" if passed else "yellow"
    ))

    # Score table
    table = Table(title="\nDetailed Scores by Specialist", show_header=True)
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

    # Display reviews
    console.print("\n[bold]Detailed Reviews:[/bold]\n")

    for review in reviews:
        console.print(Panel(
            f"[bold]{review['summary']}[/bold]\n\n"
            f"[green]Strengths:[/green]\n" + "\n".join(f"  • {s}" for s in review["strengths"]) + "\n\n"
            f"[yellow]Weaknesses:[/yellow]\n" + "\n".join(f"  • {w}" for w in review["weaknesses"]) + "\n\n"
            f"[blue]Suggestions:[/blue]\n" + "\n".join(f"  • {s}" for s in review["suggestions"]) + "\n\n"
            f"[dim]{review['detailed_feedback']}[/dim]",
            title=f"{review['specialist_name']} Review",
            border_style="cyan"
        ))

    # Save results
    output_dir = Path("results/layer-2-fee-structures")
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "topic": "Layer 2 Fee Structures",
        "manuscript_path": str(manuscript_path),
        "review_date": datetime.now().isoformat(),
        "word_count": word_count,
        "overall_average": round(overall_average, 1),
        "threshold": threshold,
        "passed": passed,
        "reviews": reviews
    }

    output_file = output_dir / "review_round_1.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)

    console.print(f"\n[green]✓ Results saved to:[/green] {output_file}")

    # Cost estimate
    total_tokens = sum(r.get("tokens", 0) for r in reviews)
    estimated_cost = (total_tokens / 1000) * 0.003  # Rough estimate
    console.print(f"[dim]Tokens used: {total_tokens:,} (~${estimated_cost:.3f})[/dim]")


async def main():
    """Main entry point."""
    console.print(Panel.fit(
        "[bold cyan]AI Research Review System[/bold cyan]\n"
        "Multi-specialist peer review demo",
        border_style="cyan"
    ))

    # Check configuration
    config = get_config()
    validation = config.validate()

    if not validation["anthropic"]:
        console.print("[red]Error: ANTHROPIC_API_KEY not configured[/red]")
        console.print("Set it in .env file to run review")
        return 1

    # Review manuscript
    manuscript_path = Path("reports/research-report.md")

    if not manuscript_path.exists():
        console.print(f"[red]Error: Manuscript not found at {manuscript_path}[/red]")
        return 1

    try:
        await review_manuscript(manuscript_path)
        return 0
    except Exception as e:
        console.print(f"\n[red]Error during review: {e}[/red]")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
