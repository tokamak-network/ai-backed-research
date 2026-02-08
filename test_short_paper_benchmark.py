#!/usr/bin/env python3
"""Benchmark: Short paper collaborative workflow — time, cost, quality."""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from research_cli.models.author import AuthorRole, WriterTeam
from research_cli.models.expert import ExpertConfig
from research_cli.workflow.collaborative_workflow import CollaborativeWorkflowOrchestrator
from research_cli.categories import get_expert_pool


# --- Timing helper ---
phase_times: dict[str, float] = {}
_phase_start: float = 0.0

def status_callback(status: str, round_num: int, message: str):
    """Track phase transitions."""
    global _phase_start
    now = time.time()
    if _phase_start > 0 and phase_times:
        last_key = list(phase_times.keys())[-1]
        if phase_times[last_key] == 0:
            phase_times[last_key] = now - _phase_start

    key = f"{status}_{round_num}"
    if key not in phase_times:
        phase_times[key] = 0
        _phase_start = now
    print(f"  [{time.strftime('%H:%M:%S')}] {message}")


async def main():
    topic = "Sparse Mixture-of-Experts Routing Strategies for Efficient Large Language Model Inference"
    major_field = "computer_science"
    subfield = "theory"

    print("=" * 80)
    print("SHORT PAPER BENCHMARK")
    print("=" * 80)
    print(f"Topic: {topic}")
    print(f"Field: {major_field} / {subfield}")
    print(f"Target length: 2000 words (short)")
    print(f"Max rounds: 2")
    print(f"Parallel sections: True (target_length <= 2500)")
    print()

    # Writer team: 1 lead + 1 coauthor (minimal)
    lead_author = AuthorRole(
        id="lead",
        name="ML Systems Expert",
        role="lead",
        expertise="Machine Learning Systems and Optimization",
        focus_areas=["mixture-of-experts", "model inference", "sparse computation"],
        model="claude-sonnet-4.5",
    )

    coauthor = AuthorRole(
        id="coauthor_1",
        name="NLP Architecture Expert",
        role="coauthor",
        expertise="Transformer Architecture Design",
        focus_areas=["attention mechanisms", "efficient transformers", "scaling laws"],
        model="claude-sonnet-4.5",
    )

    writer_team = WriterTeam(lead_author=lead_author, coauthors=[coauthor])

    # Reviewers from expert pool
    expert_pool = get_expert_pool(major_field, subfield)
    if not expert_pool:
        # Fallback: manually define reviewers
        expert_pool = ["algorithms_expert", "complexity_theory_expert", "computational_theory_expert"]
    reviewer_configs = []
    for i, expert_id in enumerate(expert_pool[:3]):
        name = expert_id.replace("_expert", "").replace("_", " ").title() + " Expert"
        domain = expert_id.replace("_expert", "").replace("_", " ").title()
        reviewer_configs.append(ExpertConfig(
            id=f"reviewer_{i+1}",
            name=name,
            domain=domain,
            focus_areas=[],
            system_prompt="",
            provider="anthropic",
            model="claude-sonnet-4.5",
        ))

    print(f"Lead: {lead_author.name} ({lead_author.model})")
    print(f"Coauthor: {coauthor.name} ({coauthor.model})")
    print(f"Reviewers: {len(reviewer_configs)}")
    for rc in reviewer_configs:
        print(f"  - {rc.name} ({rc.model})")
    print()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    project_id = f"benchmark-short-{timestamp}"
    output_dir = Path("results") / project_id

    orchestrator = CollaborativeWorkflowOrchestrator(
        topic=topic,
        major_field=major_field,
        subfield=subfield,
        writer_team=writer_team,
        reviewer_configs=reviewer_configs,
        output_dir=output_dir,
        max_rounds=2,
        threshold=8.0,
        target_manuscript_length=2000,
        research_cycles=1,
        status_callback=status_callback,
    )

    wall_start = time.time()
    result = await orchestrator.run()
    wall_end = time.time()

    # Close last phase timer
    if phase_times:
        last_key = list(phase_times.keys())[-1]
        if phase_times[last_key] == 0:
            phase_times[last_key] = wall_end - _phase_start

    wall_total = wall_end - wall_start

    # --- Report ---
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)

    print(f"\nTotal wall-clock time: {wall_total:.1f}s ({wall_total/60:.1f}m)")

    print("\nPhase breakdown:")
    for key, dur in phase_times.items():
        print(f"  {key}: {dur:.1f}s")

    # Performance metrics from review workflow
    review_result = result.get("review_result", {})
    perf = review_result.get("performance", {})
    if perf:
        print(f"\nReview phase metrics:")
        print(f"  Total tokens: {perf.get('total_tokens', 'N/A'):,}")
        print(f"  Estimated cost: ${perf.get('estimated_cost', 0):.3f}")
        print(f"  Review duration: {perf.get('total_duration', 0):.1f}s")

    # Manuscript quality
    manuscript = result.get("manuscript", {})
    print(f"\nManuscript:")
    print(f"  Title: {manuscript.get('title', 'N/A')}")
    print(f"  Word count: {manuscript.get('word_count', 'N/A')}")
    print(f"  Citation count: {manuscript.get('citation_count', 'N/A')}")
    print(f"  Sections: {len(manuscript.get('sections', []))}")

    # Review scores
    rounds = review_result.get("rounds", [])
    for rd in rounds:
        r_num = rd.get("round", "?")
        avg = rd.get("overall_average", 0)
        decision = rd.get("moderator_decision", {}).get("decision", "?")
        print(f"\n  Round {r_num}: avg={avg}/10, decision={decision}")
        for rev in rd.get("reviews", []):
            print(f"    {rev['specialist_name']}: {rev['average']}/10")

    final_score = review_result.get("final_score", 0)
    passed = review_result.get("passed", False)
    print(f"\nFinal score: {final_score}/10")
    print(f"Passed: {passed}")

    # Save benchmark summary
    benchmark = {
        "project_id": project_id,
        "topic": topic,
        "wall_time_seconds": round(wall_total, 1),
        "wall_time_minutes": round(wall_total / 60, 1),
        "phase_times": {k: round(v, 1) for k, v in phase_times.items()},
        "manuscript_word_count": manuscript.get("word_count"),
        "manuscript_citation_count": manuscript.get("citation_count"),
        "manuscript_sections": len(manuscript.get("sections", [])),
        "final_score": final_score,
        "passed": passed,
        "total_rounds": review_result.get("total_rounds", 0),
        "review_performance": perf,
        "output_dir": str(output_dir),
        "timestamp": datetime.now().isoformat(),
    }

    benchmark_file = output_dir / "benchmark.json"
    with open(benchmark_file, "w") as f:
        json.dump(benchmark, f, indent=2)
    print(f"\nBenchmark saved: {benchmark_file}")

    # Also save the manuscript content for quality review
    manuscript_content = manuscript.get("content", "")
    if manuscript_content:
        content_file = output_dir / "manuscript_content_for_review.md"
        with open(content_file, "w") as f:
            f.write(manuscript_content)
        print(f"Manuscript saved: {content_file}")

    print(f"\nFull results: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
