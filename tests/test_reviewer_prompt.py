"""
Reviewer Prompt Enhancement A/B Test

Tests whether enhanced reviewer prompts can make Pro/Flash produce
Opus-quality reviews (stricter scoring, citation verification, formal rigor).

Uses real production data from completed workflows as test inputs.
Compares: baseline prompt vs enhanced prompt for Pro and Flash.
Gold standard: existing Opus reviews from the same manuscripts.
"""

import asyncio
import json
import time
from pathlib import Path
from research_cli.model_config import _create_llm, get_pricing
from research_cli.utils.json_repair import repair_json


# ── Enhanced prompt additions (based on Opus review patterns) ────────────────

ENHANCED_SCORING_CALIBRATION = """
CRITICAL SCORING RULES — apply these strictly:
- 9-10: Reserved for truly exceptional, publication-ready work with zero significant flaws.
  Most manuscripts should NOT receive 9-10 on any dimension.
- 7-8: Strong work with only minor issues. Use this for well-executed manuscripts.
- 5-6: Adequate but with clear gaps. This is the appropriate score when important
  aspects are missing or insufficiently developed.
- 3-4: Weak, with fundamental problems that require major revision.
- 1-2: Critically flawed or largely unusable.

If you cannot identify at least 3 genuine, substantive weaknesses, you are reviewing
too generously. Vague praise like "could be slightly improved" is NOT an acceptable weakness.
"""

ENHANCED_CITATION_VERIFICATION = """
CITATION VERIFICATION — mandatory for the "citations" score:
- For each cited reference [N], verify that the combination of author names, paper title,
  venue, and year is plausible and internally consistent.
- Flag any reference where: (a) the listed authors are not known to collaborate or work in
  the claimed area, (b) the paper title does not appear in the claimed venue's proceedings,
  (c) the venue name or year seems inconsistent with the claimed content.
- If references use only numbered markers [1]-[N] with no bibliography section, the
  citations score MUST be 3 or below. A survey without a verifiable bibliography is
  fundamentally unscholarly.
- Explicitly name any suspicious or likely fabricated references in your weaknesses.
"""

ENHANCED_RIGOR_REQUIREMENTS = """
TECHNICAL RIGOR — required for the "rigor" score:
- Identify claims that lack formal justification. If a security property is claimed,
  check: is the adversary model defined? Are assumptions stated? Is there a proof sketch
  or reference to one?
- For cryptographic primitives: check if constructions are named, hardness assumptions
  stated, and known limitations acknowledged.
- For comparative claims: check if metrics are defined, baselines stated, and the
  comparison is grounded in specific implementations rather than abstract archetypes.
- Name specific missing formalisms or definitions in your weaknesses.
"""

ENHANCED_DEPTH_REQUIREMENTS = """
REVIEW DEPTH — your review must demonstrate domain expertise:
- Your detailed_feedback MUST be at least 300 words with specific technical analysis.
- Name specific tools, protocols, papers, algorithms, or systems relevant to the
  manuscript's claims — do not stay at the level of abstract concepts.
- When identifying weaknesses, provide concrete examples of what is missing or incorrect,
  not just that "more detail would be helpful".
- Distinguish between fundamental limitations and minor presentation issues.
"""

ENHANCEMENT_BLOCK = (
    ENHANCED_SCORING_CALIBRATION
    + ENHANCED_CITATION_VERIFICATION
    + ENHANCED_RIGOR_REQUIREMENTS
    + ENHANCED_DEPTH_REQUIREMENTS
)


# ── Test data loader ─────────────────────────────────────────────────────────

def load_test_cases() -> list[dict]:
    """Load test cases from the two most recent completed workflows."""
    results_dir = Path("results")
    cases = []

    targets = [
        "instant-finality-in-cryptocurrency-and-ai-20260211-141101",
        "ai's-impact-on-cryptocurrency-industry.-20260211-101633",
    ]

    for dirname in targets:
        wf_dir = results_dir / dirname
        wf_file = wf_dir / "workflow_complete.json"
        ms_file = wf_dir / "manuscript_v1.md"

        if not wf_file.exists() or not ms_file.exists():
            continue

        with open(wf_file) as f:
            wf = json.load(f)
        manuscript = ms_file.read_text()

        # Extract Opus baseline review (round 1, reviewer_2)
        round1_file = wf_dir / "round_1.json"
        with open(round1_file) as f:
            round1 = json.load(f)

        opus_review = None
        for r in round1["reviews"]:
            if r["model"] == "claude-opus-4-6":
                opus_review = r
                break

        # Extract specialist configs for reviewer_2 (Opus)
        opus_expert = None
        for expert in wf.get("expert_team", []):
            if expert["id"] == "reviewer_2":
                opus_expert = expert
                break

        cases.append({
            "name": wf["topic"][:50],
            "manuscript": manuscript,
            "opus_review": opus_review,
            "specialist_name": opus_expert["name"] if opus_expert else "Applied Cryptography & Blockchain Security",
            "focus_areas": opus_expert.get("focus_areas", []) if opus_expert else [],
            "topic": wf["topic"],
            "research_type": wf.get("research_type", "survey"),
            "audience_level": wf.get("audience_level", "professional"),
        })

    return cases


# ── Prompt builder ───────────────────────────────────────────────────────────

def build_system_prompt(specialist_name: str, focus_areas: list, topic: str) -> str:
    """Reconstruct the specialist system prompt."""
    focus_list = "\n".join(f"- {area}" for area in focus_areas)
    return f"""You are a research expert specializing in {specialist_name}.
Your role is to provide rigorous peer review from the perspective of {specialist_name}.

You are reviewing research on: {topic}

Your specific areas of focus for this review:
{focus_list}

Apply deep domain expertise. Evaluate technical correctness, identify gaps and errors, assess novelty, and provide constructive feedback."""


def build_review_prompt(manuscript: str, enhanced: bool = False) -> str:
    """Build the review prompt, optionally with enhancements."""
    enhancement = ENHANCEMENT_BLOCK if enhanced else ""

    return f"""Review this research manuscript (Round 1) from your expert perspective.

{enhancement}
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
    "rigor": <1-10>,
    "citations": <1-10>
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

Citations scoring:
- 9-10: All claims properly cited with verifiable references
- 5-6: Some citations but gaps or dubious references
- 1-2: No citations or fabricated references

Penalize: unsupported claims, fabricated citations. Reward: inline [1], [2] citations, real DOIs/URLs."""


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_review(review: dict, opus_baseline: dict) -> dict:
    """Score a review against Opus baseline."""
    scores = review.get("scores", {})
    opus_scores = opus_baseline.get("scores", {})

    # Score deviation from Opus
    deviations = {}
    for key in ["accuracy", "completeness", "clarity", "novelty", "rigor", "citations"]:
        if key in scores and key in opus_scores:
            deviations[key] = scores[key] - opus_scores[key]
    avg_deviation = sum(deviations.values()) / len(deviations) if deviations else 0

    # Review average
    avg_score = sum(scores.values()) / len(scores) if scores else 0

    # Weakness quality
    weaknesses = review.get("weaknesses", [])
    n_weaknesses = len(weaknesses)
    avg_weakness_len = sum(len(w) for w in weaknesses) / n_weaknesses if n_weaknesses else 0

    # Detailed feedback depth
    feedback = review.get("detailed_feedback", "")
    feedback_words = len(feedback.split())
    feedback_chars = len(feedback)

    # Citation-specific checks
    citations_score = scores.get("citations", 10)

    # Check if review mentions specific fabricated/suspicious references
    feedback_lower = (feedback + " ".join(weaknesses)).lower()
    mentions_fabricated = any(kw in feedback_lower for kw in [
        "fabricat", "does not appear", "cannot be verified", "unverifiable",
        "does not exist", "misattribut", "incorrect attribution",
        "not a real paper", "not found in"
    ])

    # Check if review demands formal definitions
    mentions_formal = any(kw in feedback_lower for kw in [
        "formal", "adversary model", "security model", "hardness assumption",
        "proof sketch", "formally define", "theorem"
    ])

    return {
        "avg_score": round(avg_score, 1),
        "opus_avg": round(opus_baseline["average"], 1),
        "avg_deviation": round(avg_deviation, 1),
        "citations_score": citations_score,
        "opus_citations": opus_scores.get("citations", 0),
        "n_weaknesses": n_weaknesses,
        "avg_weakness_len": round(avg_weakness_len),
        "feedback_words": feedback_words,
        "mentions_fabricated_refs": mentions_fabricated,
        "mentions_formal_rigor": mentions_formal,
    }


# ── Test runner ──────────────────────────────────────────────────────────────

async def run_single_review(
    model_name: str,
    provider: str,
    system_prompt: str,
    review_prompt: str,
) -> tuple[dict, float, float]:
    """Run a single review and return (parsed_review, duration, cost)."""
    llm = _create_llm(provider, model_name)

    # Gemini thinking token workaround
    max_tokens = 4096
    if "2.5" in model_name and provider == "google":
        effective_max = max(max_tokens * 8, 8192)
    else:
        effective_max = max_tokens

    t0 = time.time()
    response = await llm.generate(
        prompt=review_prompt,
        system=system_prompt,
        temperature=0.3,
        max_tokens=effective_max,
    )
    duration = time.time() - t0

    review_data = repair_json(response.content)
    pricing = get_pricing(model_name)
    cost = (
        (response.input_tokens or 0) * pricing["input"] / 1_000_000
        + (response.output_tokens or 0) * pricing["output"] / 1_000_000
    )

    review_data["_tokens"] = {
        "input": response.input_tokens,
        "output": response.output_tokens,
        "total": response.total_tokens,
    }

    return review_data, duration, cost


async def run_test():
    """Main test runner."""
    print("=" * 78)
    print(" Reviewer Prompt Enhancement A/B Test")
    print("=" * 78)

    cases = load_test_cases()
    print(f"\nLoaded {len(cases)} test cases from production data\n")

    test_models = [
        ("gemini-3-pro-preview", "google"),
        ("gemini-3-flash-preview", "google"),
    ]

    all_results = []

    for case in cases:
        print(f"{'─' * 78}")
        print(f"  Topic: {case['name']}")
        print(f"  Opus baseline: avg={case['opus_review']['average']}, "
              f"citations={case['opus_review']['scores']['citations']}")
        print(f"{'─' * 78}")

        system_prompt = build_system_prompt(
            case["specialist_name"],
            case["focus_areas"],
            case["topic"],
        )

        prompt_baseline = build_review_prompt(case["manuscript"], enhanced=False)
        prompt_enhanced = build_review_prompt(case["manuscript"], enhanced=True)

        for model_name, provider in test_models:
            for variant, prompt in [("baseline", prompt_baseline), ("enhanced", prompt_enhanced)]:
                label = f"{model_name} ({variant})"
                print(f"\n  Running: {label}...", end=" ", flush=True)

                try:
                    review, duration, cost = await run_single_review(
                        model_name, provider, system_prompt, prompt,
                    )
                    score = score_review(review, case["opus_review"])

                    print(f"avg={score['avg_score']} | "
                          f"cit={score['citations_score']} | "
                          f"dev={score['avg_deviation']:+.1f} | "
                          f"fab={'Y' if score['mentions_fabricated_refs'] else 'N'} | "
                          f"frm={'Y' if score['mentions_formal_rigor'] else 'N'} | "
                          f"fb_words={score['feedback_words']} | "
                          f"${cost:.3f} | {duration:.1f}s")

                    all_results.append({
                        "topic": case["name"],
                        "model": model_name,
                        "variant": variant,
                        "score": score,
                        "cost": round(cost, 4),
                        "duration": round(duration, 1),
                        "review_summary": review.get("summary", "")[:200],
                        "weaknesses": review.get("weaknesses", []),
                        "scores": review.get("scores", {}),
                    })

                except Exception as e:
                    print(f"FAILED: {e}")
                    all_results.append({
                        "topic": case["name"],
                        "model": model_name,
                        "variant": variant,
                        "error": str(e),
                    })

    # ── Summary table ────────────────────────────────────────────────────
    print(f"\n\n{'=' * 78}")
    print(" SUMMARY")
    print(f"{'=' * 78}\n")

    # Group by model
    for model_name, _ in test_models:
        baselines = [r for r in all_results if r["model"] == model_name and r.get("variant") == "baseline" and "score" in r]
        enhanceds = [r for r in all_results if r["model"] == model_name and r.get("variant") == "enhanced" and "score" in r]

        if not baselines or not enhanceds:
            continue

        def avg(items, key):
            vals = [i["score"][key] for i in items]
            return sum(vals) / len(vals) if vals else 0

        def pct(items, key):
            vals = [i["score"][key] for i in items]
            return sum(1 for v in vals if v) / len(vals) * 100 if vals else 0

        print(f"  {model_name}")
        print(f"  {'':20s} {'Baseline':>12s}  {'Enhanced':>12s}  {'Opus':>12s}")
        print(f"  {'─' * 60}")
        print(f"  {'Avg score':20s} {avg(baselines, 'avg_score'):>12.1f}  {avg(enhanceds, 'avg_score'):>12.1f}  {avg(baselines, 'opus_avg'):>12.1f}")
        print(f"  {'Citations score':20s} {avg(baselines, 'citations_score'):>12.1f}  {avg(enhanceds, 'citations_score'):>12.1f}  {avg(baselines, 'opus_citations'):>12.1f}")
        print(f"  {'Dev from Opus':20s} {avg(baselines, 'avg_deviation'):>+12.1f}  {avg(enhanceds, 'avg_deviation'):>+12.1f}  {'+0.0':>12s}")
        print(f"  {'Feedback words':20s} {avg(baselines, 'feedback_words'):>12.0f}  {avg(enhanceds, 'feedback_words'):>12.0f}  —")
        print(f"  {'Fabricated ref flag':20s} {pct(baselines, 'mentions_fabricated_refs'):>11.0f}%  {pct(enhanceds, 'mentions_fabricated_refs'):>11.0f}%  100%")
        print(f"  {'Formal rigor flag':20s} {pct(baselines, 'mentions_formal_rigor'):>11.0f}%  {pct(enhanceds, 'mentions_formal_rigor'):>11.0f}%  100%")
        print(f"  {'Avg cost':20s} ${sum(r['cost'] for r in baselines)/len(baselines):>11.3f}  ${sum(r['cost'] for r in enhanceds)/len(enhanceds):>11.3f}")
        print()

    # ── Save full results ────────────────────────────────────────────────
    output_file = Path("test_reviewer_prompt_results.json")
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Full results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(run_test())
