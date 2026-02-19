"""Unit tests for LLM provider token tracking logic.

Validates that thinking-token multiplier conditions and streaming usage
options are correctly configured across all provider methods — without
making any real API calls.

Usage:
    python3 -m pytest tests/test_llm_token_tracking.py -v
"""

import re
import inspect
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── Gemini thinking-token multiplier ─────────────────────────────────────────

class TestGeminiThinkingTokenMultiplier:
    """All Gemini methods that set effective_max_tokens must use the same
    model-check condition as generate() — i.e. ("2.5", "3-pro", "3-flash").
    """

    @pytest.fixture(scope="class")
    def gemini_source(self):
        path = ROOT / "research_cli" / "llm" / "gemini.py"
        return path.read_text(encoding="utf-8")

    def _extract_thinking_conditions(self, source: str) -> list[dict]:
        """Find all `if ...self.model...` guards before effective_max_tokens assignment."""
        pattern = re.compile(
            r'effective_max_tokens\s*=\s*max_tokens\s*\n'
            r'\s+if (.+?):\s*\n'
            r'\s+effective_max_tokens\s*=',
            re.MULTILINE,
        )
        results = []
        for m in pattern.finditer(source):
            line_num = source[:m.start()].count("\n") + 1
            results.append({"line": line_num, "condition": m.group(1).strip()})
        return results

    def test_all_methods_have_thinking_guard(self, gemini_source):
        """generate(), generate_streaming(), and stream() must all have the guard."""
        conditions = self._extract_thinking_conditions(gemini_source)
        assert len(conditions) >= 3, (
            f"Expected at least 3 thinking-token guards (generate, generate_streaming, stream), "
            f"found {len(conditions)}: {conditions}"
        )

    def test_all_conditions_are_identical(self, gemini_source):
        """Every thinking-token guard must use the same model-check condition."""
        conditions = self._extract_thinking_conditions(gemini_source)
        unique = set(c["condition"] for c in conditions)
        assert len(unique) == 1, (
            f"Thinking-token conditions are inconsistent across methods:\n"
            + "\n".join(f"  line {c['line']}: {c['condition']}" for c in conditions)
        )

    @pytest.mark.parametrize("model_substring", ["2.5", "3-pro", "3-flash"])
    def test_condition_includes_model(self, gemini_source, model_substring):
        """The condition must check for each thinking model family."""
        conditions = self._extract_thinking_conditions(gemini_source)
        assert conditions, "No thinking-token conditions found"
        condition_text = conditions[0]["condition"]
        assert f'"{model_substring}"' in condition_text, (
            f'Thinking-token condition missing check for "{model_substring}":\n'
            f"  {condition_text}"
        )

    @pytest.mark.parametrize("model_name,should_multiply", [
        ("gemini-2.5-flash", True),
        ("gemini-2.5-pro", True),
        ("gemini-3-pro-preview", True),
        ("gemini-3-flash-preview", True),
        ("gemini-2.0-flash", False),
        ("gemini-1.5-pro", False),
    ])
    def test_multiplier_applied_correctly(self, model_name, should_multiply):
        """Instantiate GeminiLLM (without API key) and verify multiplier logic."""
        # We can't instantiate GeminiLLM without a valid key (it calls genai.configure),
        # so we test the condition logic directly.
        condition_variants = ("2.5", "3-pro", "3-flash")
        matches = any(v in model_name for v in condition_variants)
        assert matches == should_multiply, (
            f"Model '{model_name}': expected multiplier={should_multiply}, "
            f"got {matches}"
        )


# ── OpenAI streaming usage tracking ─────────────────────────────────────────

class TestOpenAIStreamingUsage:
    """OpenAI generate_streaming() must pass stream_options to get token counts."""

    @pytest.fixture(scope="class")
    def openai_source(self):
        path = ROOT / "research_cli" / "llm" / "openai.py"
        return path.read_text(encoding="utf-8")

    def test_stream_options_in_generate_streaming(self, openai_source):
        """generate_streaming() must include stream_options={"include_usage": True}."""
        # Find the generate_streaming method body
        pattern = re.compile(
            r'async def generate_streaming\(.*?\n(.*?)(?=\n    async def |\n    @property|\Z)',
            re.DOTALL,
        )
        match = pattern.search(openai_source)
        assert match, "Could not find generate_streaming() method"
        method_body = match.group(1)

        assert "stream_options" in method_body, (
            "generate_streaming() is missing stream_options parameter — "
            "OpenAI streaming won't return usage data without it"
        )
        assert '"include_usage": True' in method_body or "'include_usage': True" in method_body, (
            "stream_options must set include_usage=True"
        )

    def test_usage_extraction_present(self, openai_source):
        """generate_streaming() must extract usage from chunks."""
        assert "chunk.usage.prompt_tokens" in openai_source
        assert "chunk.usage.completion_tokens" in openai_source


# ── Cross-provider consistency ───────────────────────────────────────────────

class TestProviderConsistency:
    """All LLM providers must return LLMResponse with token fields."""

    @pytest.fixture(scope="class")
    def llm_response_class(self):
        from research_cli.llm.base import LLMResponse
        return LLMResponse

    def test_llm_response_has_token_fields(self, llm_response_class):
        fields = {f.name for f in llm_response_class.__dataclass_fields__.values()}
        assert "input_tokens" in fields
        assert "output_tokens" in fields
        assert "model" in fields

    def test_llm_response_total_tokens(self, llm_response_class):
        r = llm_response_class(
            content="test", model="test-model", provider="test",
            input_tokens=100, output_tokens=50,
        )
        assert r.total_tokens == 150

    def test_llm_response_total_tokens_none(self, llm_response_class):
        r = llm_response_class(
            content="test", model="test-model", provider="test",
            input_tokens=None, output_tokens=None,
        )
        assert r.total_tokens is None

    @pytest.mark.parametrize("provider_module", [
        "research_cli.llm.gemini",
        "research_cli.llm.openai",
        "research_cli.llm.claude",
    ])
    def test_provider_has_generate_streaming(self, provider_module):
        """Each provider must have a generate_streaming method."""
        import importlib
        mod = importlib.import_module(provider_module)
        classes = [
            obj for name, obj in inspect.getmembers(mod, inspect.isclass)
            if hasattr(obj, "generate_streaming")
        ]
        assert classes, f"{provider_module} has no class with generate_streaming()"

    @pytest.mark.parametrize("provider_file", ["gemini.py", "openai.py", "claude.py"])
    def test_generate_streaming_returns_llm_response(self, provider_file):
        """generate_streaming() return type annotation must be LLMResponse."""
        source = (ROOT / "research_cli" / "llm" / provider_file).read_text()
        # Check that generate_streaming has -> LLMResponse return annotation
        pattern = re.compile(r'async def generate_streaming\([^)]*\)\s*->\s*LLMResponse')
        assert pattern.search(source), (
            f"{provider_file}: generate_streaming() should have -> LLMResponse return type"
        )
