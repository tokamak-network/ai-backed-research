"""Utility to repair truncated JSON strings from LLM responses."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def repair_json(text: str) -> dict:
    """Parse JSON from LLM response, repairing truncated output if needed.

    Attempts multiple strategies in order:
    1. Direct json.loads
    2. Extract ```json code block
    3. Extract first { ... last } substring
    4. Repair truncated JSON by closing open quotes/brackets/braces

    Args:
        text: Raw LLM response text (may contain markdown, truncated JSON, etc.)

    Returns:
        Parsed dictionary

    Raises:
        ValueError: If JSON cannot be parsed or repaired
    """
    text = text.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text, strict=False)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Extract markdown code block (```json or ``` with JSON content)
    # Try multiple patterns for robustness
    patterns = [
        r'```json\s*\n(.*?)(?:\n```|$)',           # ```json\n{...}\n```
        r'```json\s*(.*?)(?:```|$)',               # ```json{...}``` (no newline)
        r'```\s*\n(\{.*?\})(?:\n```|$)',           # ```\n{...}\n``` (no language)
        r'```\s*(\{.*?\})```',                     # ```{...}``` (compact)
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            block = match.group(1).strip()
            try:
                return json.loads(block, strict=False)
            except (json.JSONDecodeError, ValueError):
                # Try repairing the code block content
                repaired = _repair_truncated(block)
                if repaired is not None:
                    return repaired
            # If this pattern matched but failed, try next pattern
            continue

    # Strategy 3: Extract from first { to last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        substring = text[first_brace:last_brace + 1]
        try:
            return json.loads(substring, strict=False)
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Repair truncated JSON (no closing } found, or parse still failed)
    if first_brace != -1:
        # Take everything from first { to the end
        candidate = text[first_brace:]
        repaired = _repair_truncated(candidate)
        if repaired is not None:
            return repaired

    # Dump raw response for debugging
    _dump_failed_response(text)

    raise ValueError(
        f"Could not parse or repair JSON from LLM response.\n"
        f"Response length: {len(text)}\n"
        f"Preview: {text[:300]}..."
    )


def _dump_failed_response(text: str) -> None:
    """Dump raw LLM response to file for debugging JSON parse failures."""
    try:
        dump_dir = Path("results") / "_debug_json_failures"
        dump_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dump_file = dump_dir / f"raw_response_{ts}.txt"

        # Write raw bytes info + text
        with open(dump_file, "w", encoding="utf-8") as f:
            f.write(f"=== JSON Parse Failure Debug Dump ===\n")
            f.write(f"Timestamp: {ts}\n")
            f.write(f"Response length: {len(text)}\n")
            f.write(f"First 50 bytes (repr): {repr(text[:50])}\n")
            f.write(f"Last 50 bytes (repr): {repr(text[-50:])}\n")
            first_brace_pos = text.find('{')
            last_brace_pos = text.rfind('}')
            f.write(f"First brace found at: {first_brace_pos}\n")
            f.write(f"Last brace found at: {last_brace_pos}\n")
            f.write(f"Contains <think>: {'<think>' in text.lower()}\n")
            f.write(f"Contains ```json: {'```json' in text}\n")
            f.write(f"Non-ASCII chars: {sum(1 for c in text if ord(c) > 127)}\n")
            _whitespace = ('\n', '\r', '\t')
            f.write(f"Control chars (excl newline/tab): {sum(1 for c in text if ord(c) < 32 and c not in _whitespace)}\n")
            f.write(f"\n=== RAW RESPONSE START ===\n")
            f.write(text)
            f.write(f"\n=== RAW RESPONSE END ===\n")

        logger.warning(f"JSON parse failure dumped to: {dump_file}")
    except Exception as e:
        logger.warning(f"Failed to dump debug response: {e}")


def _repair_truncated(text: str) -> dict | None:
    """Attempt to repair a truncated JSON string.

    Walks the string tracking open quotes, brackets, and braces.
    At the truncation point, closes everything in reverse order.

    Returns parsed dict on success, None on failure.
    """
    # Track parser state
    in_string = False
    escape_next = False
    stack = []  # Stack of open brackets/braces: '[' or '{'
    last_good_pos = 0  # Last position where we had valid structure

    i = 0
    while i < len(text):
        ch = text[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if in_string:
            if ch == '\\':
                escape_next = True
            elif ch == '"':
                in_string = False
                last_good_pos = i
            i += 1
            continue

        # Outside string
        if ch == '"':
            in_string = True
        elif ch in ('{', '['):
            stack.append(ch)
            last_good_pos = i
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
                last_good_pos = i
            # Mismatched close — ignore
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()
                last_good_pos = i
        elif ch == ',' or ch == ':':
            last_good_pos = i

        i += 1

    # If everything is closed, try direct parse
    if not stack and not in_string:
        try:
            return json.loads(text, strict=False)
        except (json.JSONDecodeError, ValueError):
            return None

    # Need to repair: truncate at a safe point and close open structures
    # Work backwards from end to find a safe truncation point
    repaired = text

    # If we're inside a string, close it
    if in_string:
        # Find the last complete key-value or array element
        # Truncate just before the unclosed string starts, if possible
        # Find where the unclosed string started
        search_pos = len(text) - 1
        unclosed_string_start = None
        temp_in_string = False
        temp_escape = False
        for j in range(len(text)):
            c = text[j]
            if temp_escape:
                temp_escape = False
                continue
            if temp_in_string:
                if c == '\\':
                    temp_escape = True
                elif c == '"':
                    temp_in_string = False
                continue
            if c == '"':
                temp_in_string = True
                unclosed_string_start = j

        if unclosed_string_start is not None:
            # Option A: Close the string at current position
            repaired_a = text + '"'
            # Option B: Truncate before the unclosed string started
            # and remove any trailing comma/colon
            before = text[:unclosed_string_start].rstrip()
            if before.endswith(','):
                before = before[:-1]
            elif before.endswith(':'):
                # Incomplete key-value — remove the key too
                # Find the previous comma or opening brace
                trim_pos = max(before.rfind(','), before.rfind('{'), before.rfind('['))
                if trim_pos >= 0:
                    before = before[:trim_pos + 1]

            # Try option A first (close the string)
            repaired = repaired_a
        else:
            repaired = text + '"'

    # Remove trailing incomplete tokens (trailing comma, colon, etc.)
    repaired = repaired.rstrip()
    # Remove trailing comma before we close brackets
    while repaired and repaired[-1] in (',', ':'):
        repaired = repaired[:-1].rstrip()

    # Close open brackets/braces in reverse order
    # Re-scan to get the current stack state after our repairs
    stack2 = []
    in_str = False
    esc = False
    for ch in repaired:
        if esc:
            esc = False
            continue
        if in_str:
            if ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in ('{', '['):
            stack2.append(ch)
        elif ch == '}' and stack2 and stack2[-1] == '{':
            stack2.pop()
        elif ch == ']' and stack2 and stack2[-1] == '[':
            stack2.pop()

    # If still in a string after repair, close it
    if in_str:
        repaired += '"'

    # Remove trailing comma before closing
    repaired = repaired.rstrip()
    while repaired and repaired[-1] in (',', ':'):
        repaired = repaired[:-1].rstrip()

    # Close remaining open structures
    for bracket in reversed(stack2):
        if bracket == '{':
            repaired += '}'
        elif bracket == '[':
            repaired += ']'

    try:
        return json.loads(repaired, strict=False)
    except (json.JSONDecodeError, ValueError):
        # Last resort: try more aggressive truncation
        # Find the last complete value (before truncation point)
        return _aggressive_repair(text)


def _aggressive_repair(text: str) -> dict | None:
    """More aggressive repair: find the longest parseable prefix.

    Binary-search style: progressively truncate from the end,
    closing structures at each attempt.
    """
    first_brace = text.find('{')
    if first_brace == -1:
        return None

    text = text[first_brace:]

    # Try truncating at each } or ] or " from the end
    for end_pos in range(len(text), max(0, len(text) - 2000), -1):
        candidate = text[:end_pos].rstrip()

        # Remove trailing incomplete tokens
        while candidate and candidate[-1] in (',', ':', '"'):
            candidate = candidate[:-1].rstrip()

        if not candidate:
            continue

        # Count open structures
        stack = []
        in_str = False
        esc = False
        for ch in candidate:
            if esc:
                esc = False
                continue
            if in_str:
                if ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in ('{', '['):
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()

        if in_str:
            candidate += '"'

        # Remove trailing comma
        candidate = candidate.rstrip()
        while candidate and candidate[-1] in (',', ':'):
            candidate = candidate[:-1].rstrip()

        for bracket in reversed(stack):
            candidate += '}' if bracket == '{' else ']'

        try:
            result = json.loads(candidate, strict=False)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            continue

    return None
