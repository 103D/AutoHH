"""Deterministic extraction of required experience from vacancy text.

Providers report ``experience_required`` as a normalized integer (years) so the
matching engine and stretch classifier can rely on a single representation
instead of re-parsing raw text on every call.
"""

import re

# Patterns to extract required years of experience from vacancy text.
# Russian patterns first (KZ/RU market), then English.
EXPERIENCE_PATTERNS = [
    r"(\d+)\s*\+?\s*(?:год(?:а|ы)?|лет)\s*опыта",
    r"опыт[а-яё]*\s*(?:от|:)?\s*(\d+)\s*(?:год(?:а|ы)?|лет)",
    r"от\s*(\d+)\s*(?:год(?:а|ы)?|лет)",
    r"(\d+)\s*\+?\s*(?:years?|yrs?)",
    r"(\d+)\s*\+?\s*years?\s*(?:of\s*)?experience",
]

# HeadHunter experience level ids -> minimal years requirement.
HH_EXPERIENCE_IDS = {
    "noExperience": 0,
    "between1And3": 1,
    "between3And6": 3,
    "moreThan6": 6,
}


def extract_required_experience_years(text: str | None) -> int | None:
    """Extract required years of experience from a vacancy description.

    Deterministic: returns None when the text does not state a numeric
    requirement (so callers can distinguish "no info" from 0).
    """
    if not text:
        return None
    lowered = text.lower()
    for pattern in EXPERIENCE_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def experience_years_from_hh_id(experience_id: str | None) -> int | None:
    """Map HeadHunter ``experience.id`` values to a minimal year count."""
    if not experience_id:
        return None
    return HH_EXPERIENCE_IDS.get(experience_id)
