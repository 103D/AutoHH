"""Bullet point analyzer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.services.resume_intelligence.document import ResumeDocument


class BulletStrength(Enum):
    STRONG = "strong"     # action + result + metric
    MODERATE = "moderate" # action + result
    WEAK = "weak"         # action only
    VERY_WEAK = "very_weak"


@dataclass
class BulletAnalysis:
    bullet: str
    strength: BulletStrength
    has_action: bool
    has_result: bool
    has_metric: bool
    issues: list[str]


# Action verbs.
_ACTION_VERBS = {
    "achieved", "analyzed", "applied", "built", "created", "delivered",
    "developed", "designed", "enhanced", "executed", "implemented",
    "improved", "increased", "led", "managed", "optimized", "performed",
    "reduced", "resolved", "streamlined", "анализировал", "внедрил",
    "разработал", "создал", "сократил", "снизил", "увеличил", "улучшил",
    "управлял", "ускорил", "реализовал",
}

_RESULT_MARKERS = {
    "achieved", "decreased", "improved", "increased", "reduced", "saved",
    "ускорил", "увеличил", "улучшил", "уменьшил", "снизил", "сократил",
}
_METRIC_RE = re.compile(
    r"(?:\b\d+(?:[.,]\d+)?\s*(?:%|процент(?:а|ов)?|раз(?:а)?|час(?:а|ов)?|"
    r"дн(?:я|ей)|минут(?:а|ы)?|секунд(?:а|ы)?|клиент(?:а|ов)?|пользовател(?:я|ей)|"
    r"филиал(?:а|ов)?|позиц(?:ия|ии|ий)|₸|₽|\$|€)(?!\w)|"
    r"(?:₸|₽|\$|€)\s*\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _analyze_bullet(text: str) -> BulletAnalysis:
    first = text.strip().split()[0].lower() if text.strip() else ""
    has_action = first in _ACTION_VERBS
    lowered = text.lower()
    has_result = any(marker in lowered for marker in _RESULT_MARKERS)
    has_metric = bool(_METRIC_RE.search(text))

    if has_action and has_result and has_metric:
        strength = BulletStrength.STRONG
        issues = []
    elif has_action and has_result:
        strength = BulletStrength.MODERATE
        issues = ["Add metric"]
    elif has_action:
        strength = BulletStrength.WEAK
        issues = ["Add result", "Add context"]
    else:
        strength = BulletStrength.VERY_WEAK
        issues = ["Start with action verb"]

    return BulletAnalysis(bullet=text, strength=strength, has_action=has_action, has_result=has_result, has_metric=has_metric, issues=issues)


class BulletAnalyzer:
    """Analyzes bullet points."""

    def analyze(self, doc: ResumeDocument) -> list[list[BulletAnalysis]]:
        results = []
        for entry in doc.experience:
            bullets = [_analyze_bullet(b) for b in entry.bullets if b.strip()]
            results.append(bullets)
        return results


__all__ = ["BulletAnalyzer", "BulletAnalysis", "BulletStrength"]
