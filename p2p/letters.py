"""Canonicalize multiple-choice answer text to one letter."""

from __future__ import annotations

import re


_LETTER = r"([A-E])"
_PREFIX = r"(?:OPTION\s+|THE\s+ANSWER\s+IS\s+)"


def canonical_letter(value: str) -> str:
    """Return A-E for common answer forms, or an empty string if ambiguous."""
    text = str(value or "").strip().upper().strip("*_` ")
    match = re.fullmatch(rf"(?:{_PREFIX})?{_LETTER}(?:\s*[):=.-].*)?", text)
    return match.group(1) if match else ""