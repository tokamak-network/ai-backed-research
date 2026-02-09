"""Tests for the JSON repair utility."""

import pytest
from research_cli.utils.json_repair import repair_json


class TestRepairJsonDirect:
    """Test direct JSON parsing (strategy 1)."""

    def test_valid_json(self):
        result = repair_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_valid_json_with_whitespace(self):
        result = repair_json('  \n  {"key": "value"}  \n  ')
        assert result == {"key": "value"}


class TestRepairJsonCodeBlock:
    """Test ```json code block extraction (strategy 2)."""

    def test_json_code_block(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        result = repair_json(text)
        assert result == {"key": "value"}

    def test_json_code_block_no_closing(self):
        """Code block without closing ``` (truncated response)."""
        text = 'Result:\n```json\n{"key": "value", "items": [1, 2, 3]}'
        result = repair_json(text)
        assert result["key"] == "value"
        assert result["items"] == [1, 2, 3]


class TestRepairJsonBraceExtraction:
    """Test first-{ to last-} extraction (strategy 3)."""

    def test_json_surrounded_by_text(self):
        text = 'Here is my analysis:\n{"score": 8, "comment": "good"}\nThat is all.'
        result = repair_json(text)
        assert result == {"score": 8, "comment": "good"}


class TestRepairJsonTruncated:
    """Test truncated JSON repair (strategy 4)."""

    def test_truncated_string_value(self):
        """JSON cut off mid-string value."""
        text = '{"title": "Some research about topi'
        result = repair_json(text)
        assert "title" in result

    def test_truncated_array(self):
        """JSON cut off inside an array."""
        text = '{"items": [1, 2, 3'
        result = repair_json(text)
        assert "items" in result
        assert isinstance(result["items"], list)

    def test_truncated_nested_object(self):
        """JSON cut off inside a nested object."""
        text = '{"outer": {"inner": "val"'
        result = repair_json(text)
        assert "outer" in result

    def test_truncated_after_comma(self):
        """JSON cut off right after a comma."""
        text = '{"a": 1, "b": 2,'
        result = repair_json(text)
        assert result["a"] == 1
        assert result["b"] == 2

    def test_truncated_after_colon(self):
        """JSON cut off after a key colon."""
        text = '{"a": 1, "b":'
        result = repair_json(text)
        assert result["a"] == 1

    def test_truncated_complex(self):
        """Realistic LLM response truncation with nested structures."""
        text = '''{
  "findings": [
    {
      "title": "Finding 1",
      "description": "Description of finding 1",
      "evidence": "Evidence for finding 1",
      "confidence": "high"
    },
    {
      "title": "Finding 2",
      "description": "Description of finding 2 that was cut off becau'''
        result = repair_json(text)
        assert "findings" in result
        assert len(result["findings"]) >= 1
        assert result["findings"][0]["title"] == "Finding 1"

    def test_truncated_in_code_block(self):
        """Truncated JSON inside a code block."""
        text = '```json\n{"scores": {"accuracy": 8, "completeness": 7'
        result = repair_json(text)
        assert "scores" in result

    def test_deeply_nested_truncation(self):
        """Truncation with multiple nesting levels."""
        text = '{"a": {"b": {"c": [1, 2, {"d": "val'
        result = repair_json(text)
        assert "a" in result

    def test_truncated_with_escape_in_string(self):
        """JSON with escape sequences truncated."""
        text = r'{"text": "line 1\nline 2", "other": "trunc'
        result = repair_json(text)
        assert "text" in result


class TestRepairJsonEdgeCases:
    """Test edge cases."""

    def test_empty_object(self):
        result = repair_json("{}")
        assert result == {}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            repair_json("This is just plain text with no JSON at all.")

    def test_strict_false_control_chars(self):
        """Control characters in strings should be tolerated."""
        text = '{"text": "line1\\nline2\\ttab"}'
        result = repair_json(text)
        assert "text" in result

    def test_review_like_response(self):
        """Realistic review JSON that might come from LLM."""
        text = '''{
  "scores": {
    "accuracy": 8,
    "completeness": 7,
    "clarity": 9,
    "novelty": 6,
    "rigor": 7,
    "citations": 8
  },
  "summary": "This is a well-written manuscript.",
  "strengths": ["Good coverage", "Clear writing"],
  "weaknesses": ["Limited scope"],
  "suggestions": ["Add more examples"],
  "detailed_feedback": "The manuscript provides a comprehensive overview..."
}'''
        result = repair_json(text)
        assert result["scores"]["accuracy"] == 8
        assert len(result["strengths"]) == 2
