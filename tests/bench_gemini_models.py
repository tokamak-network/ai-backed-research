"""Benchmark: gemini-3-flash-preview vs gemini-2.5-flash across light-tier roles.

Tests 5 core roles with realistic prompts from the actual workflow,
measuring latency, token usage, cost, and output quality.
"""

import asyncio
import json
import os
import time

TOPIC = "Game-theoretic approaches to mechanism design in decentralized systems"
MANUSCRIPT_SNIPPET = """## TL;DR

- Mechanism design in decentralized systems faces unique challenges due to the absence of a trusted central authority.
- Game-theoretic frameworks, particularly those leveraging incentive compatibility and individual rationality, provide formal tools for designing robust decentralized protocols.
- Recent advances integrate cryptographic commitments with economic incentive layers to achieve strategy-proofness in blockchain consensus, decentralized exchanges, and DAO governance.

## Introduction: Designing Rules for Rational Agents

The design of decentralized systems—blockchains, decentralized autonomous organizations (DAOs), and peer-to-peer marketplaces—fundamentally requires reasoning about strategic behavior. Unlike centralized platforms, where a single entity can enforce rules, decentralized systems must ensure that rational, self-interested participants find it optimal to follow the intended protocol.

## Theoretical Foundations

### The Revelation Principle in Decentralized Settings

The revelation principle states that for any mechanism with an equilibrium, there exists a direct mechanism where truthful reporting is an equilibrium strategy. In decentralized contexts, this principle must be adapted."""

MODELS = ["gemini-3-flash-preview", "gemini-2.5-flash"]

# Gemini pricing (per 1M tokens)
PRICING = {
    "gemini-3-flash-preview": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
}

ROLE_TESTS = {
    "categorizer": {
        "system": "You classify research topics into academic categories. Respond with ONLY JSON.",
        "prompt": f"""Classify this research topic into academic categories.

TOPIC: {TOPIC}

Respond in JSON format:
{{
  "primary_major": "<field>",
  "primary_subfield": "<subfield>",
  "secondary_major": "<field or null>",
  "secondary_subfield": "<subfield or null>",
  "confidence": 0.9,
  "reasoning": "<brief>"
}}""",
        "temperature": 0.3,
        "max_tokens": 512,
        "json_mode": True,
        "quality_check": lambda d: d.get("primary_major") and d.get("confidence", 0) > 0.5,
    },

    "team_composer": {
        "system": "You are an expert at assembling research teams. Respond with ONLY JSON.",
        "prompt": f"""Propose a 3-person expert research team for the following topic:

TOPIC: {TOPIC}

For each expert, provide:
- expert_domain: their area of expertise
- rationale: why they're suited for this topic
- focus_areas: list of 2-3 specific focus areas

Return JSON:
{{
  "experts": [
    {{"expert_domain": "...", "rationale": "...", "focus_areas": ["...", "..."]}}
  ]
}}""",
        "temperature": 0.7,
        "max_tokens": 2048,
        "json_mode": True,
        "quality_check": lambda d: isinstance(d.get("experts"), list) and len(d.get("experts", [])) >= 2,
    },

    "moderator": {
        "system": "You are a peer review moderator. Synthesize reviewer feedback into an actionable revision plan. Respond with ONLY JSON.",
        "prompt": f"""Synthesize the following reviewer feedback into a revision plan.

TOPIC: {TOPIC}
ROUND: 1
AVERAGE SCORE: 5.3/10

REVIEWER 1 (Score: 5.0):
Strengths: Clear theoretical framing
Weaknesses: Lacks concrete examples, citations are generic
Suggestions: Add specific protocol analysis (e.g., Ethereum EIP-1559)

REVIEWER 2 (Score: 5.5):
Strengths: Good coverage of mechanism design fundamentals
Weaknesses: Missing discussion of computational complexity constraints
Suggestions: Include bounded rationality considerations

REVIEWER 3 (Score: 5.3):
Strengths: Well-structured argument
Weaknesses: No empirical evidence or case studies
Suggestions: Add comparison table of existing mechanisms

Return JSON:
{{
  "decision": "MAJOR_REVISION",
  "key_issues": ["issue1", "issue2"],
  "revision_priorities": ["priority1", "priority2"],
  "specific_actions": ["action1", "action2"]
}}""",
        "temperature": 0.3,
        "max_tokens": 2048,
        "json_mode": True,
        "quality_check": lambda d: d.get("decision") in ("MAJOR_REVISION", "MINOR_REVISION", "ACCEPT", "REJECT") and len(d.get("key_issues", [])) >= 1,
    },

    "title_generator": {
        "system": "You generate concise English titles from manuscript content. Respond with only the title text.",
        "prompt": f"""Based on the following research manuscript, generate a concise title IN ENGLISH.

ORIGINAL TOPIC: {TOPIC}

MANUSCRIPT PREVIEW:
{MANUSCRIPT_SNIPPET}

REQUIREMENTS:
- 8-15 words maximum
- Specific to the actual research focus
- Title case
- No quotes, no explanation

Respond with ONLY the title text on a single line.""",
        "temperature": 0.7,
        "max_tokens": 100,
        "json_mode": False,
        "quality_check": lambda t: 15 <= len(t) <= 200 and '\n' not in t.strip(),
    },

    "desk_editor": {
        "system": "You are a desk editor performing initial screening. Respond with ONLY JSON.",
        "prompt": f"""Perform desk screening on this manuscript submission.

TOPIC: {TOPIC}

MANUSCRIPT (first 500 chars):
{MANUSCRIPT_SNIPPET[:500]}

Check:
1. Is the topic within academic scope?
2. Is the writing quality acceptable for review?
3. Are there obvious issues (plagiarism indicators, off-topic, etc.)?

Return JSON:
{{
  "pass": true,
  "scope_ok": true,
  "quality_ok": true,
  "issues": [],
  "notes": "brief assessment"
}}""",
        "temperature": 0.1,
        "max_tokens": 512,
        "json_mode": True,
        "quality_check": lambda d: isinstance(d.get("pass"), bool) and isinstance(d.get("scope_ok"), bool),
    },
}


async def test_model(model_name: str):
    """Run all role tests against a single model."""
    from research_cli.llm.gemini import GeminiLLM
    from research_cli.utils.json_repair import repair_json

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    llm = GeminiLLM(api_key=api_key, model=model_name)
    pricing = PRICING.get(model_name, {"input": 0.15, "output": 0.60})

    results = {}

    for role, config in ROLE_TESTS.items():
        t0 = time.monotonic()
        try:
            response = await llm.generate(
                prompt=config["prompt"],
                system=config["system"],
                temperature=config["temperature"],
                max_tokens=config["max_tokens"],
                json_mode=config.get("json_mode", False),
            )
            elapsed = time.monotonic() - t0

            content = response.content.strip()
            in_tok = response.input_tokens or 0
            out_tok = response.output_tokens or 0
            cost = (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000

            # Quality check
            if config["json_mode"]:
                parsed = repair_json(content)
                quality_ok = config["quality_check"](parsed)
                output_preview = json.dumps(parsed, ensure_ascii=False)[:120]
            else:
                quality_ok = config["quality_check"](content)
                output_preview = content[:120]

            results[role] = {
                "latency_s": round(elapsed, 2),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(cost, 6),
                "quality_ok": quality_ok,
                "output_preview": output_preview,
                "error": None,
            }
        except Exception as e:
            elapsed = time.monotonic() - t0
            results[role] = {
                "latency_s": round(elapsed, 2),
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0,
                "quality_ok": False,
                "output_preview": "",
                "error": str(e),
            }

    return results


async def main():
    all_results = {}
    for model in MODELS:
        print(f"\n{'='*60}")
        print(f"  Testing: {model}")
        print(f"{'='*60}")
        results = await test_model(model)
        all_results[model] = results

        total_latency = 0
        total_cost = 0
        quality_pass = 0

        for role, r in results.items():
            status = "✓" if r["quality_ok"] else ("✗ " + (r["error"] or "quality fail"))
            print(f"  {role:<20} {r['latency_s']:>7.1f}s  {r['input_tokens']:>5}+{r['output_tokens']:<5} tok  ${r['cost_usd']:.5f}  {status}")
            total_latency += r["latency_s"]
            total_cost += r["cost_usd"]
            if r["quality_ok"]:
                quality_pass += 1

        print(f"  {'─'*58}")
        print(f"  {'TOTAL':<20} {total_latency:>7.1f}s  {'':>12}  ${total_cost:.5f}  {quality_pass}/{len(results)} pass")

    # Comparison summary
    print(f"\n{'='*60}")
    print(f"  COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Role':<20} {'3-flash-preview':>16} {'2.5-flash':>12} {'Speedup':>9}")
    print(f"  {'─'*58}")
    for role in ROLE_TESTS:
        r3 = all_results[MODELS[0]][role]
        r25 = all_results[MODELS[1]][role]
        speedup = r3["latency_s"] / r25["latency_s"] if r25["latency_s"] > 0 else float("inf")
        q3 = "✓" if r3["quality_ok"] else "✗"
        q25 = "✓" if r25["quality_ok"] else "✗"
        print(f"  {role:<20} {r3['latency_s']:>7.1f}s {q3}   {r25['latency_s']:>7.1f}s {q25}   {speedup:>6.1f}x")

    t3_total = sum(r["latency_s"] for r in all_results[MODELS[0]].values())
    t25_total = sum(r["latency_s"] for r in all_results[MODELS[1]].values())
    c3_total = sum(r["cost_usd"] for r in all_results[MODELS[0]].values())
    c25_total = sum(r["cost_usd"] for r in all_results[MODELS[1]].values())

    print(f"  {'─'*58}")
    print(f"  {'TOTAL LATENCY':<20} {t3_total:>7.1f}s      {t25_total:>7.1f}s      {t3_total/t25_total if t25_total > 0 else 0:>6.1f}x")
    print(f"  {'TOTAL COST':<20} ${c3_total:>.5f}      ${c25_total:>.5f}")


if __name__ == "__main__":
    asyncio.run(main())
