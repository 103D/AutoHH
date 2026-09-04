"""Shared text helpers for the scoring engine (match model v3).

Kept as pure module-level functions so every component (skills, resume keyword
matching, ...) uses exactly the same normalization instead of re-implementing
regexes in several files.
"""

import re
from typing import Any

_TOKEN_RE = re.compile(r"[a-zA-Z0-9+.#-]+")


def tokenize_text(text: str | None) -> set[str]:
    """Split text into lowercase tokens for skill matching."""
    return set(_TOKEN_RE.findall((text or "").lower()))


def normalize_skills(value: Any) -> set[str]:
    """Normalize skills/technologies from list/dict/set to lowercase strings."""
    if value is None:
        return set()

    if isinstance(value, dict):
        items = value.keys()
    elif isinstance(value, list | tuple | set):
        items = value
    else:
        return set()

    return {str(item).lower().strip() for item in items if item}
