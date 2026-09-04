"""Serialize/parse SkillMatch objects to/from TEXT[]-safe strings.

matched_skills are stored in a ``TEXT[]`` column as human-readable strings
("SQL (exact, 1.0)"); plain "SQL" means exact/1.0. The AI provider returns
``SkillMatch`` objects; matching persists the serialized form and the API
response parses it back (frontend contract: matched_skills: SkillMatch[]).
"""

import re
from typing import Any

from app.providers.ai.base import SkillMatch

_SKILL_MATCH_RE = re.compile(
    r"^(?P<skill>.+?)\s*\((?P<type>\w+)(?:,\s*(?P<conf>[\d.]+))?\)$"
)


def serialize_skill_matches(skills: Any) -> list[str]:
    """Convert AI SkillMatch objects into TEXT[]-safe strings."""
    result: list[str] = []
    for item in skills or []:
        if isinstance(item, SkillMatch):
            if item.match_type == "exact" and item.confidence == 1.0:
                result.append(item.skill)
            elif item.confidence == 1.0:
                result.append(f"{item.skill} ({item.match_type})")
            else:
                result.append(f"{item.skill} ({item.match_type}, {item.confidence:g})")
        elif isinstance(item, str):
            result.append(item)
        else:
            result.append(str(item))
    return result


def parse_skill_match(raw: str) -> SkillMatch:
    """Restore a SkillMatch from its stored string form."""
    match = _SKILL_MATCH_RE.match((raw or "").strip())
    if not match:
        return SkillMatch(skill=(raw or "").strip())
    confidence = float(match.group("conf")) if match.group("conf") else 1.0
    return SkillMatch(
        skill=match.group("skill"),
        match_type=match.group("type"),
        confidence=confidence,
    )
