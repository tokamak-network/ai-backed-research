#!/usr/bin/env python3
"""
Role vs Model isolation test.

Original assignment from e2e run:
  - Gemini 3 Pro  → Role A: "Early 17th Century East Asian Geopolitics & Neutral Diplomacy"
  - Sonnet        → Role B: "Late Joseon Socio-Economic Policy & Fiscal Reform"
  - Sonnet        → Role C: "Joseon Political Philosophy & Historiographical Revisionism"

This test swaps roles to isolate model vs role effects:
  - Gemini 3 Pro  → Role B (Sonnet's original)
  - Gemini 3 Pro  → Role C (Sonnet's original)
  - Sonnet        → Role A (Gemini's original)
"""

import asyncio, json, time, warnings, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
warnings.filterwarnings("ignore", category=FutureWarning)
sys.path.insert(0, str(Path(__file__).parent.parent))

from research_cli.model_config import _create_llm
from research_cli.utils.json_repair import repair_json

RESULT_DIR = Path("results/광해군에-대한-평가-20260215-142444")

# The 3 reviewer roles from the e2e run
ROLES = {
    "A_Geopolitics": {
        "system": """You are a research expert specializing in Early 17th Century East Asian Geopolitics & Neutral Diplomacy.
Your role is to provide rigorous peer review from the perspective of Early 17th Century East Asian Geopolitics & Neutral Diplomacy.

You are reviewing research on: 광해군에 대한 평가

Your specific areas of focus for this review:
- Northeast Asian power dynamics during the Ming-Qing transition
- Gwanghaegun's neutral diplomacy and the Battle of Sarhu
- Tributary system (Sadae) politics and legitimacy

Apply deep domain expertise. Evaluate technical correctness, identify gaps and errors, assess novelty, and provide constructive feedback.""",
    },
    "B_FiscalReform": {
        "system": """You are a research expert specializing in Late Joseon Socio-Economic Policy & Fiscal Reform.
Your role is to provide rigorous peer review from the perspective of Late Joseon Socio-Economic Policy & Fiscal Reform.

You are reviewing research on: 광해군에 대한 평가

Your specific areas of focus for this review:
- Daedongbeop (Uniform Land Tax) implementation and fiscal impact
- Palace construction costs and corvée labor mobilization
- Post-Imjin War agricultural recovery and land surveys (Yangjeon)

Apply deep domain expertise. Evaluate technical correctness, identify gaps and errors, assess novelty, and provide constructive feedback.""",
    },
    "C_Historiography": {
        "system": """You are a research expert specializing in Joseon Political Philosophy & Historiographical Revisionism.
Your role is to provide rigorous peer review from the perspective of Joseon Political Philosophy & Historiographical Revisionism.

You are reviewing research on: 광해군에 대한 평가

Your specific areas of focus for this review:
- Neo-Confucian ethics and political legitimacy (Myeongbun, Peryun)
- Gwanghaegun Ilgi textual criticism and editorial bias
- Evolution of historiographical narratives from Injo era to modern revisionism

Apply deep domain expertise. Evaluate technical correctness, identify gaps and errors, assess novelty, and provide constructive feedback.""",
    },
}

REVIEW_PROMPT_TEMPLATE = """Review this research manuscript (Round 1) from your expert perspective.

NOTE: This is a SURVEY / LITERATURE REVIEW paper. Evaluate accordingly:
- Breadth of coverage: Does it comprehensively cover the field?
- Taxonomy/categorization: Are the surveyed works well-organized?
- Gap identification: Does it clearly identify research gaps and future directions?
- Do NOT penalize for lack of novel experimental results
- Evaluate the quality of synthesis, comparison, and critical analysis of existing work

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

Citations scoring guide:
- 9-10: All major claims properly cited with verifiable references
- 7-8: Most claims cited, references are real and checkable
- 5-6: Some citations present but gaps exist, or some references look dubious
- 3-4: Few citations, many unsupported claims
- 1-2: No citations or clearly fabricated references

Penalize: unsupported claims, unverifiable references, hallucinated citations.
Reward: inline citations [1], [2], proper References section, real DOIs/URLs.

Be honest and constructive. Focus on your domain of expertise."""


async def call_model(provider, model, system, prompt):
    llm = _create_llm(provider=provider, model=model)
    effective_max = max(4096 * 8, 8192)
    start = time.time()
    try:
        resp = await llm.generate(prompt=prompt, system=system, temperature=0.3, max_tokens=effective_max)
        elapsed = time.time() - start
        return {"model": model, "output": resp.content, "elapsed": elapsed,
                "in": resp.input_tokens, "out": resp.output_tokens}
    except Exception as e:
        return {"model": model, "output": f"[ERROR: {e}]", "elapsed": time.time()-start, "in": 0, "out": 0}


def analyze_review(output_str):
    """Extract key quality signals from a review."""
    try:
        data = repair_json(output_str)
    except:
        return {"parse_error": True}

    scores = data.get("scores", {})
    weaknesses = data.get("weaknesses", [])
    suggestions = data.get("suggestions", [])
    feedback = data.get("detailed_feedback", "")

    # Count specific scholar mentions
    scholar_keywords = ["한명기", "Han Myung", "Han Myeong", "이태진", "Yi Tae-jin",
                        "최이돈", "Choi Yi-don", "김용섭", "Kim Yong-seop",
                        "Palais", "Deuchler", "Haboush", "Tagawa", "다가와",
                        "만문노당", "Manbun", "Wagner"]
    all_text = " ".join([feedback] + weaknesses + suggestions)
    scholars_mentioned = [s for s in scholar_keywords if s in all_text]

    # Count primary source mentions
    primary_keywords = ["광해군일기", "Gwanghaegun Ilgi", "승정원일기", "Seungjeongwon",
                        "비변사등록", "Bibyeonsa", "선조실록", "인조실록",
                        "만문노당", "Manbun Roto"]
    primaries_mentioned = [p for p in primary_keywords if p in all_text]

    # Citation fraud detection
    fraud_keywords = ["fabricat", "fake", "non-existent", "duplicate", "padded",
                      "inflated", "identical", "does not match", "misattribut"]
    fraud_mentions = [f for f in fraud_keywords if f.lower() in all_text.lower()]

    # Specific historical corrections
    correction_keywords = ["obstacle", "obstructed", "blocked", "reluctant",
                          "이원익", "Yi Won-ik", "공납", "Gongnap", "궁궐 건설",
                          "palace construction"]
    corrections = [c for c in correction_keywords if c.lower() in all_text.lower()]

    return {
        "scores": scores,
        "avg": sum(scores.values()) / len(scores) if scores else 0,
        "feedback_len": len(feedback),
        "weakness_count": len(weaknesses),
        "suggestion_count": len(suggestions),
        "scholars_mentioned": scholars_mentioned,
        "primaries_mentioned": primaries_mentioned,
        "fraud_detected": fraud_mentions,
        "historical_corrections": corrections,
    }


async def main():
    # Load manuscript v1
    ms = (RESULT_DIR / "manuscript_v1.md").read_text()

    prompt = REVIEW_PROMPT_TEMPLATE.format(manuscript=ms)

    # Test matrix: swap roles between models
    tests = [
        # Original assignments (control)
        ("gemini-3-pro-preview", "google",    "A_Geopolitics",    "ORIGINAL"),
        ("claude-sonnet-4-5",    "anthropic", "B_FiscalReform",   "ORIGINAL"),
        ("claude-sonnet-4-5",    "anthropic", "C_Historiography", "ORIGINAL"),
        # Swapped assignments (experiment)
        ("claude-sonnet-4-5",    "anthropic", "A_Geopolitics",    "SWAPPED"),
        ("gemini-3-pro-preview", "google",    "B_FiscalReform",   "SWAPPED"),
        ("gemini-3-pro-preview", "google",    "C_Historiography", "SWAPPED"),
    ]

    results = []

    # Run in pairs to manage API load
    for i in range(0, len(tests), 2):
        batch = tests[i:i+2]
        tasks = [call_model(t[1], t[0], ROLES[t[2]]["system"], prompt) for t in batch]
        outputs = await asyncio.gather(*tasks)
        for (model, provider, role, condition), out in zip(batch, outputs):
            analysis = analyze_review(out.get("output", ""))
            results.append({
                "model": model.replace("gemini-3-pro-preview", "Gemini3Pro").replace("claude-sonnet-4-5", "Sonnet"),
                "role": role,
                "condition": condition,
                "analysis": analysis,
                "elapsed": out["elapsed"],
                "out_tokens": out["out"],
            })
            short_model = model.replace("gemini-3-pro-preview", "Gemini3Pro").replace("claude-sonnet-4-5", "Sonnet")
            avg = analysis.get("avg", 0)
            print(f"  {condition:8s} | {short_model:12s} + {role:20s} | avg={avg:.1f} | {out['elapsed']:.1f}s")

    # Print comparison tables
    print(f"\n{'='*90}")
    print("ROLE vs MODEL ISOLATION ANALYSIS")
    print(f"{'='*90}")

    # Group by role for comparison
    for role_key in ["A_Geopolitics", "B_FiscalReform", "C_Historiography"]:
        print(f"\n{'─'*80}")
        print(f"ROLE: {role_key}")
        print(f"{'─'*80}")

        role_results = [r for r in results if r["role"] == role_key]
        for r in role_results:
            a = r["analysis"]
            if "parse_error" in a:
                print(f"  {r['condition']:8s} {r['model']:12s}: PARSE ERROR")
                continue
            scores = a["scores"]
            print(f"  {r['condition']:8s} {r['model']:12s}:")
            print(f"    Scores: acc={scores.get('accuracy',0)} comp={scores.get('completeness',0)} "
                  f"clar={scores.get('clarity',0)} nov={scores.get('novelty',0)} "
                  f"rig={scores.get('rigor',0)} cit={scores.get('citations',0)}  AVG={a['avg']:.1f}")
            print(f"    Feedback: {a['feedback_len']} chars, {a['weakness_count']} weaknesses, {a['suggestion_count']} suggestions")
            print(f"    Scholars: {a['scholars_mentioned']}")
            print(f"    Primary sources: {a['primaries_mentioned']}")
            print(f"    Citation fraud: {a['fraud_detected']}")
            print(f"    Historical corrections: {a['historical_corrections']}")
            print(f"    Tokens: {r['out_tokens']} out, {r['elapsed']:.1f}s")

    # Model-level summary
    print(f"\n{'='*90}")
    print("MODEL-LEVEL AGGREGATES (across all roles)")
    print(f"{'='*90}")

    for model_name in ["Gemini3Pro", "Sonnet"]:
        model_results = [r for r in results if r["model"] == model_name and "parse_error" not in r["analysis"]]
        if not model_results:
            continue
        avg_score = sum(r["analysis"]["avg"] for r in model_results) / len(model_results)
        avg_feedback = sum(r["analysis"]["feedback_len"] for r in model_results) / len(model_results)
        all_scholars = set()
        all_primaries = set()
        all_fraud = set()
        all_corrections = set()
        for r in model_results:
            all_scholars.update(r["analysis"]["scholars_mentioned"])
            all_primaries.update(r["analysis"]["primaries_mentioned"])
            all_fraud.update(r["analysis"]["fraud_detected"])
            all_corrections.update(r["analysis"]["historical_corrections"])

        print(f"\n  {model_name} (across {len(model_results)} roles):")
        print(f"    Avg score: {avg_score:.1f}")
        print(f"    Avg feedback length: {avg_feedback:.0f} chars")
        print(f"    Unique scholars cited: {sorted(all_scholars)}")
        print(f"    Unique primary sources: {sorted(all_primaries)}")
        print(f"    Citation fraud signals: {sorted(all_fraud)}")
        print(f"    Historical corrections: {sorted(all_corrections)}")


asyncio.run(main())
