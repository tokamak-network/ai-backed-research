#!/usr/bin/env python3
"""Quick test script to verify basic setup."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from research_cli.config import Config
from research_cli.llm import ClaudeLLM


async def test_basic_setup():
    """Test that basic infrastructure works."""
    print("Testing AI Research Setup...")
    print("-" * 50)

    # Test 1: Config loading
    print("\n1. Testing configuration loading...")
    try:
        config = Config()
        print(f"   ✓ Config loaded")
        print(f"   - Results dir: {config.results_dir}")
        print(f"   - Max rounds: {config.max_review_rounds}")
        print(f"   - Threshold: {config.score_threshold}")
    except Exception as e:
        print(f"   ✗ Config failed: {e}")
        return False

    # Test 2: API key validation
    print("\n2. Checking API key configuration...")
    validation = config.validate()
    for provider, configured in validation.items():
        status = "✓" if configured else "✗"
        print(f"   {status} {provider}: {'configured' if configured else 'missing'}")

    if not validation["anthropic"]:
        print("\n   [WARNING] No LLM API key found.")
        print("   Set LLM_API_KEY or ANTHROPIC_API_KEY in .env file to test LLM functionality.")
        return True  # Not a failure, just can't test LLM

    # Test 3: LLM provider instantiation
    print("\n3. Testing LLM provider...")
    try:
        llm_config = config.get_llm_config("anthropic")
        llm = ClaudeLLM(api_key=llm_config.api_key, model=llm_config.model)
        print(f"   ✓ ClaudeLLM initialized")
        print(f"   - Model: {llm.model}")
        print(f"   - Provider: {llm.provider_name}")

        # Test 4: Simple generation
        print("\n4. Testing text generation...")
        response = await llm.generate(
            prompt="Say 'Setup test successful!' and nothing else.",
            max_tokens=50
        )
        print(f"   ✓ Generation successful")
        print(f"   - Response: {response.content}")
        print(f"   - Tokens: {response.total_tokens}")

    except Exception as e:
        print(f"   ✗ LLM test failed: {e}")
        return False

    print("\n" + "=" * 50)
    print("✓ All tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_basic_setup())
    sys.exit(0 if success else 1)
