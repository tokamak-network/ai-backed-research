"""Benchmark: gemini-3-pro-preview vs claude-sonnet-4-5 for section writing.

Gives the same section spec to both models and compares:
- Latency
- Token usage & cost
- Output quality (word count, citation count, content preview)
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOPIC = "Game-theoretic approaches to mechanism design in decentralized systems"
CATEGORY = "Computer Science → Theory & Algorithms"

# Simulated research notes context (compact)
RESEARCH_CONTEXT = """Key findings from collaborative research:
1. VCG mechanisms face O(n²) communication complexity in decentralized settings
2. Sybil-proof DSIC mechanisms require identity-binding via stake deposits
3. BFT consensus tolerates f<n/3 Byzantine faults but rational deviation changes equilibrium
4. Collusion resilience requires cryptographic commitment schemes
5. EIP-1559 base fee mechanism approximates optimal posted pricing
6. MEV extraction creates negative externalities equivalent to front-running tax
7. DAO governance suffers from low participation and whale dominance
8. Quadratic voting improves preference intensity expression but is Sybil-vulnerable

Key references:
- Roughgarden (2021) "Transaction Fee Mechanism Design"
- Buterin et al. (2019) "Flexible Enough: EIP-1559"
- Daian et al. (2020) "Flash Boys 2.0: MEV on Ethereum"
- Chen & Micali (2019) "Algorand: Scaling Byzantine Agreements"
- Lalley & Weyl (2018) "Quadratic Voting"
"""

SECTION_SPEC = {
    "title": "Strategic Security in Blockchain Protocols",
    "order": 3,
    "purpose": "Analyze game-theoretic security properties of blockchain consensus and DeFi protocols",
    "target_length": 700,
    "key_points": [
        "BFT consensus and rational deviation from honest behavior",
        "MEV extraction as a game-theoretic problem",
        "EIP-1559 fee mechanism analysis",
        "Collusion resilience in on-chain governance"
    ]
}

SYSTEM_PROMPT = """You are an expert academic researcher writing a section of a survey paper.
Write in formal academic prose with inline citations [Author, Year].
Be specific, cite evidence, and maintain scholarly rigor."""

USER_PROMPT = f"""Write section {SECTION_SPEC['order']}: "{SECTION_SPEC['title']}" for a survey paper.

TOPIC: {TOPIC}
CATEGORY: {CATEGORY}
TARGET LENGTH: {SECTION_SPEC['target_length']} words
PURPOSE: {SECTION_SPEC['purpose']}

KEY POINTS TO COVER:
{chr(10).join(f'- {p}' for p in SECTION_SPEC['key_points'])}

RESEARCH CONTEXT:
{RESEARCH_CONTEXT}

Write the section in markdown. Include inline citations [Author, Year].
Do NOT include a references section — just the section body."""

MODELS = [
    {"name": "gemini-3-pro-preview", "provider": "google"},
    {"name": "claude-sonnet-4-5", "provider": "anthropic"},
]

# Pricing per 1M tokens
PRICING = {
    "gemini-3-pro-preview": {"input": 2.0, "output": 12.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
}


async def test_writer(model_name: str, provider: str):
    """Run writing test for a single model."""
    if provider == "google":
        from research_cli.llm.gemini import GeminiLLM
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        llm = GeminiLLM(api_key=api_key, model=model_name)
    else:
        from research_cli.llm.claude import ClaudeLLM
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        llm = ClaudeLLM(api_key=api_key, model=model_name)

    pricing = PRICING[model_name]

    t0 = time.monotonic()
    try:
        response = await llm.generate(
            prompt=USER_PROMPT,
            system=SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=4096,
        )
        elapsed = time.monotonic() - t0

        content = response.content.strip()
        in_tok = response.input_tokens or 0
        out_tok = response.output_tokens or 0
        cost = (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000

        # Metrics
        words = len(content.split())
        citations = content.count('[')
        lines = content.count('\n') + 1

        return {
            "model": model_name,
            "latency_s": round(elapsed, 2),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": round(cost, 6),
            "word_count": words,
            "citation_count": citations,
            "line_count": lines,
            "content": content,
            "error": None,
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {
            "model": model_name,
            "latency_s": round(elapsed, 2),
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0,
            "word_count": 0,
            "citation_count": 0,
            "line_count": 0,
            "content": "",
            "error": str(e),
        }


async def main():
    results = []

    for model_info in MODELS:
        name = model_info["name"]
        provider = model_info["provider"]
        print(f"\n{'='*70}")
        print(f"  Writing with: {name} ({provider})")
        print(f"{'='*70}")

        result = await test_writer(name, provider)
        results.append(result)

        if result["error"]:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  Latency:    {result['latency_s']}s")
            print(f"  Tokens:     {result['input_tokens']} in + {result['output_tokens']} out")
            print(f"  Cost:       ${result['cost_usd']:.5f}")
            print(f"  Words:      {result['word_count']} (target: {SECTION_SPEC['target_length']})")
            print(f"  Citations:  {result['citation_count']}")

    # Side by side comparison
    print(f"\n{'='*70}")
    print(f"  COMPARISON")
    print(f"{'='*70}")

    r1, r2 = results[0], results[1]
    print(f"  {'Metric':<20} {'gemini-3-pro':>16} {'claude-sonnet':>16}")
    print(f"  {'─'*52}")
    print(f"  {'Latency':<20} {r1['latency_s']:>14.1f}s {r2['latency_s']:>14.1f}s")
    print(f"  {'Input tokens':<20} {r1['input_tokens']:>16} {r2['input_tokens']:>16}")
    print(f"  {'Output tokens':<20} {r1['output_tokens']:>16} {r2['output_tokens']:>16}")
    print(f"  {'Cost':<20} ${r1['cost_usd']:>14.5f} ${r2['cost_usd']:>14.5f}")
    print(f"  {'Words':<20} {r1['word_count']:>16} {r2['word_count']:>16}")
    print(f"  {'Citations':<20} {r1['citation_count']:>16} {r2['citation_count']:>16}")

    if r2['latency_s'] > 0:
        speedup = r1['latency_s'] / r2['latency_s']
        print(f"  {'Speed ratio':<20} {'':>16} {speedup:>15.1f}x {'(3-pro slower)' if speedup > 1 else '(sonnet slower)'}")

    # Full content output
    for r in results:
        print(f"\n{'='*70}")
        print(f"  FULL OUTPUT: {r['model']}")
        print(f"  ({r['word_count']} words, {r['citation_count']} citations)")
        print(f"{'='*70}")
        print(r['content'])


if __name__ == "__main__":
    asyncio.run(main())
