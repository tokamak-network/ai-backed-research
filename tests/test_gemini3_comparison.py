#!/usr/bin/env python3
"""
Gemini 3 vs 2.5 Quality Comparison
Tests gemini-3-pro-preview vs gemini-2.5-pro and gemini-3-flash-preview vs gemini-2.5-flash
across 4 production roles: reviewer, moderator, team_composer, research_notes.

Usage:
    python3 tests/test_gemini3_comparison.py
"""

import json
import asyncio
import time
import warnings
import sys
from pathlib import Path
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()

warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from research_cli.model_config import _create_llm, get_pricing
from research_cli.utils.json_repair import repair_json

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
MODELS = {
    "gemini-3-pro-preview":   {"provider": "google", "model": "gemini-3-pro-preview",   "short": "3-Pro"},
    "gemini-2.5-pro":         {"provider": "google", "model": "gemini-2.5-pro",          "short": "2.5-Pro"},
    "gemini-3-flash-preview": {"provider": "google", "model": "gemini-3-flash-preview",  "short": "3-Flash"},
    "gemini-2.5-flash":       {"provider": "google", "model": "gemini-2.5-flash",        "short": "2.5-Flash"},
}

# ---------------------------------------------------------------------------
# Data Loader
# ---------------------------------------------------------------------------
RESULTS_DIR = Path(__file__).parent / "results"

def find_best_workflow() -> Dict:
    """Find a workflow with reviews and manuscript for testing."""
    for d in sorted(RESULTS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        wf_file = d / "workflow_complete.json"
        ms_file = d / "manuscript_v1.md"
        if wf_file.exists() and ms_file.exists():
            wf = json.loads(wf_file.read_text())
            ms = ms_file.read_text()
            rounds = wf.get("rounds", [])
            if rounds and rounds[0].get("reviews") and len(ms) > 500:
                return {
                    "topic": wf.get("topic", d.name),
                    "workflow": wf,
                    "manuscript": ms,
                    "reviews": rounds[0]["reviews"],
                    "moderator_decision": rounds[0].get("moderator_decision", {}),
                    "expert_team": wf.get("expert_team", []),
                    "research_type": wf.get("research_type", "survey"),
                }
    raise RuntimeError("No workflow with reviews found in tests/results/")


# ---------------------------------------------------------------------------
# Prompt Builders (from test_model_comparison.py)
# ---------------------------------------------------------------------------

def build_reviewer_prompt(manuscript: str, research_type: str = "survey") -> Dict:
    system = """You are a senior peer reviewer specializing in AI systems and machine learning.
Your expertise includes agent architectures, tool use, reasoning, and evaluation.
You provide thorough, constructive reviews grounded in technical knowledge."""

    research_note = ""
    if research_type == "survey":
        research_note = """NOTE: This is a SURVEY paper. Evaluate accordingly:
- Breadth and depth of coverage
- Quality of taxonomy/categorization
- Gap identification and future directions
- Do NOT penalize for lack of novel experiments

"""

    prompt = f"""Review this research manuscript from your expert perspective.

{research_note}MANUSCRIPT:
{manuscript[:12000]}

---

Provide your review in JSON format:

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
  "detailed_feedback": "<paragraph of detailed feedback>"
}}

Scoring: 9-10 exceptional, 7-8 strong, 5-6 adequate, 3-4 weak, 1-2 poor.
Be honest and constructive."""

    return {"system": system, "prompt": prompt, "temperature": 0.3, "max_tokens": 4096}


def build_moderator_prompt(manuscript: str, reviews: List[Dict]) -> Dict:
    system = """You are the Editor-in-Chief for a leading research publication.
Exercise EDITORIAL JUDGMENT, not mechanical score calculation.
Synthesize reviewer feedback and make accept/reject decisions."""

    reviews_text = []
    for i, r in enumerate(reviews, 1):
        s = r.get("scores", {})
        reviews_text.append(f"""REVIEWER {i} ({r.get("specialist_name", "Unknown")}):
Avg Score: {r.get("average", 0)}/10
Scores: Accuracy={s.get("accuracy",0)}, Completeness={s.get("completeness",0)}, Clarity={s.get("clarity",0)}, Novelty={s.get("novelty",0)}, Rigor={s.get("rigor",0)}, Citations={s.get("citations",0)}
Summary: {r.get("summary", "")}
Strengths: {', '.join(r.get("strengths", [])[:2])}
Weaknesses: {', '.join(r.get("weaknesses", [])[:2])}""")

    prompt = f"""Review this manuscript submission. Exercise editorial judgment.

SUBMISSION: Round 1 of 3, Threshold: 7.0/10

PEER REVIEWS:
{chr(10).join(reviews_text)}

---

MANUSCRIPT (first 3000 chars):
{manuscript[:3000]}

---

Make your decision in JSON:
{{
  "decision": "ACCEPT|MINOR_REVISION|MAJOR_REVISION|REJECT",
  "confidence": <1-5>,
  "meta_review": "<2-3 paragraphs synthesizing reviews>",
  "key_strengths": ["<s1>", "<s2>", "<s3>"],
  "key_weaknesses": ["<w1>", "<w2>", "<w3>"],
  "required_changes": ["<c1>", "<c2>", "<c3>"],
  "recommendation": "<clear guidance>"
}}"""

    return {"system": system, "prompt": prompt, "temperature": 0.3, "max_tokens": 2048}


def build_team_composer_prompt(topic: str) -> Dict:
    system = """You are an expert research coordinator specializing in assembling optimal peer review teams.
Propose diverse, complementary expert teams for rigorous peer review."""

    prompt = f"""Analyze the following research topic and propose a team of 3 expert reviewers.

RESEARCH TOPIC: {topic}

Respond in JSON:
{{
  "analysis": "<brief analysis>",
  "experts": [
    {{
      "expert_domain": "<specific domain>",
      "rationale": "<2-3 sentences>",
      "focus_areas": ["<area 1>", "<area 2>", "<area 3>"],
      "suggested_model": "claude-opus-4-6",
      "suggested_provider": "anthropic"
    }}
  ]
}}

REQUIREMENTS: Exactly 3 experts, distinct domains, specific focus areas."""

    return {"system": system, "prompt": prompt, "temperature": 0.7, "max_tokens": 4096}


def build_research_notes_prompt(topic: str) -> Dict:
    return {
        "system": """You are a research assistant conducting literature review.
Search for relevant sources, extract key findings, identify important quotes.""",
        "prompt": f"""Conduct literature search for:

TOPIC: {topic}

RESEARCH QUESTIONS:
- What are the current approaches and architectures?
- What are the main challenges and limitations?
- What are the emerging trends and future directions?

Output in JSON:
{{
  "sources": [
    {{
      "source": "Paper/Doc title",
      "source_type": "paper|documentation|blog",
      "key_findings": ["Finding 1", "Finding 2"],
      "quotes": ["Quote 1"],
      "relevance": "How this relates"
    }}
  ]
}}

Include 3-5 relevant sources.""",
        "temperature": 0.7,
        "max_tokens": 4096,
    }


# ---------------------------------------------------------------------------
# LLM Call
# ---------------------------------------------------------------------------

async def call_model(provider: str, model: str, prompt: str, system: str,
                     temperature: float, max_tokens: int) -> Dict:
    llm = _create_llm(provider=provider, model=model)

    # Thinking token overhead for Gemini models
    effective_max = max_tokens
    if provider == "google":
        effective_max = max(max_tokens * 8, 8192)

    start = time.time()
    try:
        resp = await llm.generate(
            prompt=prompt, system=system,
            temperature=temperature, max_tokens=effective_max,
        )
        elapsed = time.time() - start
        content = resp.content
        input_tokens = resp.input_tokens or 0
        output_tokens = resp.output_tokens or 0
    except Exception as e:
        elapsed = time.time() - start
        return {
            "model": model, "error": str(e),
            "elapsed": elapsed, "input_tokens": 0, "output_tokens": 0, "cost": 0,
        }

    pricing = get_pricing(model)
    cost = (input_tokens * pricing["input"] / 1_000_000 +
            output_tokens * pricing["output"] / 1_000_000)

    return {
        "model": model, "output": content, "elapsed": elapsed,
        "input_tokens": input_tokens, "output_tokens": output_tokens, "cost": cost,
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_json_output(output: str, role: str) -> Dict[str, Any]:
    """Score output quality across multiple dimensions."""
    scores = {
        "json_valid": False,
        "format_complete": False,
        "content_depth": 0,  # 1-5
        "specificity": 0,    # 1-5
        "output_length": len(output) if output else 0,
    }

    if not output or output.startswith("[ERROR"):
        return scores

    try:
        data = repair_json(output)
        scores["json_valid"] = True
    except (ValueError, KeyError):
        return scores

    if role == "reviewer":
        s = data.get("scores", {})
        has_all_scores = all(k in s for k in ["accuracy", "completeness", "clarity", "novelty", "rigor", "citations"])
        has_text = bool(data.get("summary")) and bool(data.get("detailed_feedback"))
        has_lists = len(data.get("strengths", [])) >= 2 and len(data.get("weaknesses", [])) >= 2
        scores["format_complete"] = has_all_scores and has_text and has_lists

        # Content depth: based on detailed_feedback length
        fb = data.get("detailed_feedback", "")
        if len(fb) > 800: scores["content_depth"] = 5
        elif len(fb) > 500: scores["content_depth"] = 4
        elif len(fb) > 300: scores["content_depth"] = 3
        elif len(fb) > 100: scores["content_depth"] = 2
        else: scores["content_depth"] = 1

        # Specificity: weaknesses that reference specific sections/issues
        weaknesses = data.get("weaknesses", [])
        specific = sum(1 for w in weaknesses if any(kw in w.lower() for kw in ["section", "citation", "reference", "table", "figure", "equation", "page", "paragraph", "line"]))
        scores["specificity"] = min(5, specific + 1)

        scores["avg_score"] = sum(s.values()) / len(s) if s else 0
        scores["scores"] = s

    elif role == "moderator":
        decision = data.get("decision", "").upper()
        valid = {"ACCEPT", "MINOR_REVISION", "MAJOR_REVISION", "REJECT"}
        scores["format_complete"] = decision in valid and bool(data.get("meta_review"))
        scores["decision"] = decision

        meta = data.get("meta_review", "")
        if len(meta) > 500: scores["content_depth"] = 5
        elif len(meta) > 300: scores["content_depth"] = 4
        elif len(meta) > 150: scores["content_depth"] = 3
        else: scores["content_depth"] = 2

        changes = data.get("required_changes", [])
        specific = sum(1 for c in changes if len(c) > 50)
        scores["specificity"] = min(5, specific + 1)

    elif role == "team_composer":
        experts = data.get("experts", [])
        scores["format_complete"] = len(experts) == 3 and all(
            e.get("expert_domain") and e.get("rationale") and e.get("focus_areas")
            for e in experts
        )

        domains = set(e.get("expert_domain", "") for e in experts)
        scores["content_depth"] = min(5, len(domains) + 2)

        focus_total = sum(len(e.get("focus_areas", [])) for e in experts)
        scores["specificity"] = min(5, focus_total // 2)

    elif role == "research_notes":
        sources = data.get("sources", [])
        scores["format_complete"] = len(sources) >= 3 and all(
            s.get("source") and s.get("key_findings") for s in sources
        )

        scores["content_depth"] = min(5, len(sources))
        findings_total = sum(len(s.get("key_findings", [])) for s in sources)
        scores["specificity"] = min(5, findings_total // 3)

    return scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_comparison():
    print("=" * 80)
    print("GEMINI 3 vs 2.5 QUALITY COMPARISON")
    print("=" * 80)

    # Load test data
    print("\nLoading test data...")
    wf = find_best_workflow()
    print(f"  Topic: {wf['topic']}")
    print(f"  Manuscript: {len(wf['manuscript'])} chars")
    print(f"  Reviews: {len(wf['reviews'])}")

    # Build prompts for each role
    prompts = {
        "reviewer": build_reviewer_prompt(wf["manuscript"], wf["research_type"]),
        "moderator": build_moderator_prompt(wf["manuscript"], wf["reviews"]),
        "team_composer": build_team_composer_prompt(wf["topic"]),
        "research_notes": build_research_notes_prompt(wf["topic"]),
    }

    # Run all model x role combinations
    results = {}
    model_keys = list(MODELS.keys())

    for role, prompt_data in prompts.items():
        print(f"\n{'─' * 60}")
        print(f"ROLE: {role}")
        print(f"{'─' * 60}")

        # Run models for this role concurrently
        tasks = []
        for mk in model_keys:
            m = MODELS[mk]
            tasks.append(call_model(
                provider=m["provider"], model=m["model"],
                prompt=prompt_data["prompt"], system=prompt_data["system"],
                temperature=prompt_data["temperature"],
                max_tokens=prompt_data["max_tokens"],
            ))

        outputs = await asyncio.gather(*tasks)

        for mk, out in zip(model_keys, outputs):
            key = f"{role}:{mk}"
            score = score_json_output(out.get("output", ""), role)
            results[key] = {**out, **score}
            short = MODELS[mk]["short"]

            if out.get("error"):
                print(f"  {short:10s} ERROR: {out['error'][:60]}")
            else:
                print(f"  {short:10s} {out['elapsed']:5.1f}s  "
                      f"in={out['input_tokens']:5d}  out={out['output_tokens']:5d}  "
                      f"${out['cost']:.4f}  "
                      f"json={'OK' if score['json_valid'] else 'FAIL'}  "
                      f"fmt={'OK' if score['format_complete'] else 'FAIL'}  "
                      f"depth={score['content_depth']}  spec={score['specificity']}")

    # Summary table
    print(f"\n{'=' * 80}")
    print("SUMMARY COMPARISON TABLE")
    print(f"{'=' * 80}")

    # Pro comparison
    print(f"\n{'─' * 70}")
    print("PRO TIER: gemini-3-pro-preview vs gemini-2.5-pro")
    print(f"{'─' * 70}")
    print(f"{'Role':<18} {'Metric':<15} {'3-Pro':>10} {'2.5-Pro':>10} {'Winner':>10}")
    print(f"{'─' * 70}")

    for role in prompts:
        k3 = f"{role}:gemini-3-pro-preview"
        k25 = f"{role}:gemini-2.5-pro"
        r3, r25 = results.get(k3, {}), results.get(k25, {})

        # Time
        t3, t25 = r3.get("elapsed", 0), r25.get("elapsed", 0)
        winner_t = "3-Pro" if t3 < t25 else "2.5-Pro"
        print(f"{role:<18} {'Latency (s)':<15} {t3:>10.1f} {t25:>10.1f} {winner_t:>10}")

        # Cost
        c3, c25 = r3.get("cost", 0), r25.get("cost", 0)
        winner_c = "3-Pro" if c3 < c25 else "2.5-Pro"
        print(f"{'':<18} {'Cost ($)':<15} {c3:>10.4f} {c25:>10.4f} {winner_c:>10}")

        # Content depth
        d3, d25 = r3.get("content_depth", 0), r25.get("content_depth", 0)
        winner_d = "3-Pro" if d3 > d25 else ("2.5-Pro" if d25 > d3 else "Tie")
        print(f"{'':<18} {'Depth (1-5)':<15} {d3:>10} {d25:>10} {winner_d:>10}")

        # Specificity
        s3, s25 = r3.get("specificity", 0), r25.get("specificity", 0)
        winner_s = "3-Pro" if s3 > s25 else ("2.5-Pro" if s25 > s3 else "Tie")
        print(f"{'':<18} {'Specific (1-5)':<15} {s3:>10} {s25:>10} {winner_s:>10}")

        # JSON valid
        j3 = "OK" if r3.get("json_valid") else "FAIL"
        j25 = "OK" if r25.get("json_valid") else "FAIL"
        print(f"{'':<18} {'JSON':<15} {j3:>10} {j25:>10}")

        # Format complete
        f3 = "OK" if r3.get("format_complete") else "FAIL"
        f25 = "OK" if r25.get("format_complete") else "FAIL"
        print(f"{'':<18} {'Format':<15} {f3:>10} {f25:>10}")

        # Role-specific
        if role == "reviewer":
            avg3 = r3.get("avg_score", 0)
            avg25 = r25.get("avg_score", 0)
            print(f"{'':<18} {'Avg Score':<15} {avg3:>10.1f} {avg25:>10.1f}")
        elif role == "moderator":
            dec3 = r3.get("decision", "N/A")
            dec25 = r25.get("decision", "N/A")
            print(f"{'':<18} {'Decision':<15} {dec3:>10} {dec25:>10}")

        print()

    # Flash comparison
    print(f"{'─' * 70}")
    print("FLASH TIER: gemini-3-flash-preview vs gemini-2.5-flash")
    print(f"{'─' * 70}")
    print(f"{'Role':<18} {'Metric':<15} {'3-Flash':>10} {'2.5-Flash':>10} {'Winner':>10}")
    print(f"{'─' * 70}")

    for role in prompts:
        k3 = f"{role}:gemini-3-flash-preview"
        k25 = f"{role}:gemini-2.5-flash"
        r3, r25 = results.get(k3, {}), results.get(k25, {})

        t3, t25 = r3.get("elapsed", 0), r25.get("elapsed", 0)
        winner_t = "3-Flash" if t3 < t25 else "2.5-Flash"
        print(f"{role:<18} {'Latency (s)':<15} {t3:>10.1f} {t25:>10.1f} {winner_t:>10}")

        c3, c25 = r3.get("cost", 0), r25.get("cost", 0)
        winner_c = "3-Flash" if c3 < c25 else "2.5-Flash"
        print(f"{'':<18} {'Cost ($)':<15} {c3:>10.4f} {c25:>10.4f} {winner_c:>10}")

        d3, d25 = r3.get("content_depth", 0), r25.get("content_depth", 0)
        winner_d = "3-Flash" if d3 > d25 else ("2.5-Flash" if d25 > d3 else "Tie")
        print(f"{'':<18} {'Depth (1-5)':<15} {d3:>10} {d25:>10} {winner_d:>10}")

        s3, s25 = r3.get("specificity", 0), r25.get("specificity", 0)
        winner_s = "3-Flash" if s3 > s25 else ("2.5-Flash" if s25 > s3 else "Tie")
        print(f"{'':<18} {'Specific (1-5)':<15} {s3:>10} {s25:>10} {winner_s:>10}")

        j3 = "OK" if r3.get("json_valid") else "FAIL"
        j25 = "OK" if r25.get("json_valid") else "FAIL"
        print(f"{'':<18} {'JSON':<15} {j3:>10} {j25:>10}")

        f3 = "OK" if r3.get("format_complete") else "FAIL"
        f25 = "OK" if r25.get("format_complete") else "FAIL"
        print(f"{'':<18} {'Format':<15} {f3:>10} {f25:>10}")

        if role == "reviewer":
            avg3 = r3.get("avg_score", 0)
            avg25 = r25.get("avg_score", 0)
            print(f"{'':<18} {'Avg Score':<15} {avg3:>10.1f} {avg25:>10.1f}")
        elif role == "moderator":
            dec3 = r3.get("decision", "N/A")
            dec25 = r25.get("decision", "N/A")
            print(f"{'':<18} {'Decision':<15} {dec3:>10} {dec25:>10}")

        print()

    # Total cost comparison
    print(f"{'─' * 70}")
    print("TOTAL COST ACROSS ALL ROLES")
    print(f"{'─' * 70}")
    for mk in model_keys:
        short = MODELS[mk]["short"]
        total_cost = sum(results.get(f"{r}:{mk}", {}).get("cost", 0) for r in prompts)
        total_time = sum(results.get(f"{r}:{mk}", {}).get("elapsed", 0) for r in prompts)
        print(f"  {short:15s}  ${total_cost:.4f}  {total_time:.1f}s total")


if __name__ == "__main__":
    asyncio.run(run_comparison())
