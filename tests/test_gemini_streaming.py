#!/usr/bin/env python3
"""Unit test for GeminiLLM.generate_streaming() method.

Verifies that streaming generation returns a valid LLMResponse
with content, token counts, and stop_reason — matching generate().
"""

import asyncio
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")
sys.path.insert(0, str(Path(__file__).parent))

from research_cli.model_config import _create_llm
from research_cli.llm.base import LLMResponse


MODELS_TO_TEST = [
    ("google", "gemini-3-flash-preview"),
    ("google", "gemini-3-pro-preview"),
]

PROMPT = "Explain what a blockchain is in exactly 3 sentences."
SYSTEM = "You are a concise technical writer."


async def test_generate_streaming(provider: str, model: str) -> dict:
    """Test generate_streaming for one model."""
    llm = _create_llm(provider, model)
    result = {"model": model, "provider": provider}

    # --- Test 1: generate_streaming returns LLMResponse ---
    try:
        response = await llm.generate_streaming(
            prompt=PROMPT,
            system=SYSTEM,
            temperature=0.3,
            max_tokens=256,
        )
        assert isinstance(response, LLMResponse), f"Expected LLMResponse, got {type(response)}"
        result["streaming_ok"] = True
        result["content_preview"] = response.content[:120]
        result["content_len"] = len(response.content)
        result["input_tokens"] = response.input_tokens
        result["output_tokens"] = response.output_tokens
        result["stop_reason"] = response.stop_reason
        result["provider_field"] = response.provider
        result["model_field"] = response.model
    except Exception as e:
        result["streaming_ok"] = False
        result["streaming_error"] = f"{type(e).__name__}: {e}"
        return result

    # --- Test 2: Content is non-empty ---
    assert len(response.content.strip()) > 0, "Streaming returned empty content"
    result["content_nonempty"] = True

    # --- Test 3: Token counts present ---
    result["has_input_tokens"] = response.input_tokens is not None and response.input_tokens > 0
    result["has_output_tokens"] = response.output_tokens is not None and response.output_tokens > 0

    # --- Test 4: Stop reason is valid ---
    result["stop_reason_valid"] = response.stop_reason in ("STOP", "MAX_TOKENS", "stop", "end_turn", None)

    # --- Test 5: Compare with non-streaming generate ---
    try:
        non_stream = await llm.generate(
            prompt=PROMPT,
            system=SYSTEM,
            temperature=0.3,
            max_tokens=256,
        )
        result["generate_ok"] = True
        result["generate_content_len"] = len(non_stream.content)
        result["generate_input_tokens"] = non_stream.input_tokens
        result["generate_output_tokens"] = non_stream.output_tokens
        result["generate_stop_reason"] = non_stream.stop_reason
        # Both should return valid content (not exact match, different calls)
        result["both_have_content"] = len(response.content) > 10 and len(non_stream.content) > 10
    except Exception as e:
        result["generate_ok"] = False
        result["generate_error"] = f"{type(e).__name__}: {e}"

    return result


async def main():
    print("=" * 70)
    print("GeminiLLM.generate_streaming() Unit Test")
    print("=" * 70)

    all_passed = True

    for provider, model in MODELS_TO_TEST:
        print(f"\n--- Testing {model} ---")
        result = await test_generate_streaming(provider, model)

        # Print results
        if result.get("streaming_ok"):
            print(f"  [PASS] generate_streaming returned LLMResponse")
            print(f"         Content ({result['content_len']} chars): {result['content_preview']}...")
            print(f"         Tokens: in={result['input_tokens']}, out={result['output_tokens']}")
            print(f"         Stop reason: {result['stop_reason']}")
        else:
            print(f"  [FAIL] generate_streaming: {result.get('streaming_error')}")
            all_passed = False
            continue

        if result.get("content_nonempty"):
            print(f"  [PASS] Content is non-empty")
        else:
            print(f"  [FAIL] Content is empty")
            all_passed = False

        if result.get("has_input_tokens"):
            print(f"  [PASS] input_tokens present: {result['input_tokens']}")
        else:
            print(f"  [WARN] input_tokens missing (non-fatal)")

        if result.get("has_output_tokens"):
            print(f"  [PASS] output_tokens present: {result['output_tokens']}")
        else:
            print(f"  [WARN] output_tokens missing (non-fatal)")

        if result.get("stop_reason_valid"):
            print(f"  [PASS] stop_reason valid: {result['stop_reason']}")
        else:
            print(f"  [WARN] stop_reason unexpected: {result['stop_reason']}")

        if result.get("generate_ok"):
            print(f"  [PASS] Non-streaming generate() also works")
            print(f"         Streaming: {result['content_len']} chars, Non-streaming: {result['generate_content_len']} chars")
            if result.get("both_have_content"):
                print(f"  [PASS] Both methods return substantial content")
            else:
                print(f"  [FAIL] One method returned very short content")
                all_passed = False
        elif "generate_error" in result:
            print(f"  [FAIL] Non-streaming generate(): {result['generate_error']}")
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("RESULT: ALL TESTS PASSED")
    else:
        print("RESULT: SOME TESTS FAILED")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
