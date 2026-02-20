"""Shared reference normalization helpers for dedup."""

import re

# DOI values that LLMs hallucinate instead of leaving as None
_BOGUS_DOI_PATTERNS = {
    "not provided", "n/a", "na", "none", "unknown", "null", "",
}


def normalize_title(title: str) -> str:
    """Normalize a reference title for dedup comparison.

    - Strips leading arXiv IDs like ``[2412.01708]``
    - Removes trailing site-name suffixes (``| Journal``, ``- PMC``, etc.)
    - Strips punctuation and collapses whitespace
    """
    t = title.lower().strip()
    # Strip leading arXiv ID like "[2412.01708] "
    t = re.sub(r"^\[\d{4}\.\d{4,5}]\s*", "", t)
    # Remove trailing " | journal", " - site" style suffixes
    t = re.split(r"\s*[|\u2013\u2014]\s*|\s+[-]\s+", t)[0]
    # Remove all punctuation except alphanumeric and spaces
    t = re.sub(r"[^\w\s]", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clean_doi(doi: str | None) -> str | None:
    """Return a cleaned DOI string, or None if the value is bogus/empty."""
    if doi is None:
        return None
    stripped = doi.strip()
    if stripped.lower() in _BOGUS_DOI_PATTERNS:
        return None
    # Must look vaguely like a DOI (contains "10." or "arXiv:")
    if not stripped.startswith("10.") and not stripped.startswith("arXiv:"):
        return None
    return stripped
