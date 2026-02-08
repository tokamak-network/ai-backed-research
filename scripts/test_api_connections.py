#!/usr/bin/env python3
"""Test API connections for all configured models.

Usage:
    python scripts/test_api_connections.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_cli.model_config import _load_config, _create_llm


async def test_model(provider: str, model: str) -> dict:
    """Test a single model with a minimal prompt."""
    try:
        llm = _create_llm(provider, model)
        response = await llm.generate(
            prompt="Say hello in exactly 5 words.",
            temperature=0.1,
            max_tokens=50,
        )
        return {
            "model": model,
            "provider": provider,
            "status": "OK",
            "response": response.content[:80],
            "tokens": response.total_tokens,
        }
    except Exception as e:
        return {
            "model": model,
            "provider": provider,
            "status": "FAIL",
            "error": str(e)[:120],
        }


async def main():
    config = _load_config()
    pricing = config.get("pricing", {})

    # Collect unique model+provider pairs from all roles
    seen = set()
    tests = []
    for role_name, role_data in config["roles"].items():
        primary = role_data["primary"]
        key = (primary["provider"], primary["model"])
        if key not in seen:
            seen.add(key)
            tests.append(key)
        for fb in role_data.get("fallback", []):
            key = (fb["provider"], fb["model"])
            if key not in seen:
                seen.add(key)
                tests.append(key)

    print(f"Testing {len(tests)} unique model+provider combinations...\n")
    print(f"{'Provider':12s} {'Model':30s} {'Status':8s} {'Details'}")
    print("-" * 90)

    results = await asyncio.gather(*[test_model(p, m) for p, m in tests])

    ok = 0
    fail = 0
    for r in results:
        if r["status"] == "OK":
            detail = f"{r['response'][:50]}... ({r['tokens']} tokens)"
            ok += 1
        else:
            detail = r["error"]
            fail += 1
        print(f"{r['provider']:12s} {r['model']:30s} {r['status']:8s} {detail}")

    print(f"\n{ok} OK, {fail} FAIL out of {len(tests)} models")
    return fail == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
