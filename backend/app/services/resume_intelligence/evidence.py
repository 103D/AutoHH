"""Evidence Analyzer — maps job requirements to candidate evidence.

This is the core of the Resume Intelligence system: connects what a job
requires to what the candidate actually has proven in their resume.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.resume_intelligence.document import ResumeDocument
from app.services.skill_taxonomy import skill_variants


class EvidenceStrength(Enum):
    """How strongly a skill is evidenced in the resume."""

    EXPLICIT = "explicit"  # Directly in experience
    INDIRECT = "indirect"  # Related context
    WEAK = "weak"          # Only in skills list
    MISSING = "missing"    # Not found


@dataclass
class EvidenceItem:
    """Evidence for a single requirement."""

    requirement: str
    importance: str
    strength: EvidenceStrength
    source: str | None = None
    details: str | None = None


@dataclass
class EvidenceReport:
    """Complete evidence analysis."""

    job_title: str | None = None
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    weak_evidenced: list[str] = field(default_factory=list)

    @property
    def missing_required_count(self) -> int:
        return len(self.missing_required)


def _contains_skill(text: str, skill: str) -> bool:
    """Match exact canonical variants, never merely related technologies."""
    lowered = text.lower()
    return any(
        re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", lowered)
        for variant in skill_variants(skill)
    )


def _find_in_experience(doc: ResumeDocument, tech: str) -> tuple[bool, str | None]:
    """Check if technology appears in experience section."""
    for i, entry in enumerate(doc.experience):
        if _contains_skill(entry.all_text, tech):
            return True, f"Experience #{i + 1}"
    return False, None


def _find_in_skills(doc: ResumeDocument, tech: str) -> bool:
    """Check if technology appears in skills section."""
    return _contains_skill(doc.section_text("skills"), tech)


def _requirement_value(requirement: Any, field: str, default: str) -> str:
    """Read a requirement from a validated schema object or plain mapping."""
    if isinstance(requirement, dict):
        return str(requirement.get(field, default))
    return str(getattr(requirement, field, default))


class EvidenceAnalyzer:
    """Analyzes how well resume evidences job requirements."""

    def analyze(self, doc: ResumeDocument, requirements: list[dict]) -> EvidenceReport:
        """Analyze resume against job requirements."""
        items: list[EvidenceItem] = []
        missing_required: list[str] = []
        weak_evidenced: list[str] = []

        for req in requirements:
            skill = _requirement_value(req, "skill", "").strip()
            importance = _requirement_value(req, "importance", "PREFERRED").upper()
            if not skill:
                continue

            in_exp, exp_source = _find_in_experience(doc, skill)
            if in_exp:
                items.append(EvidenceItem(
                    requirement=skill, importance=importance,
                    strength=EvidenceStrength.EXPLICIT, source=exp_source))
                continue

            in_skills = _find_in_skills(doc, skill)
            if in_skills:
                if importance == "REQUIRED":
                    weak_evidenced.append(skill)
                items.append(EvidenceItem(
                    requirement=skill, importance=importance,
                    strength=EvidenceStrength.WEAK, source="Skills section"))
                continue

            if importance == "REQUIRED":
                missing_required.append(skill)
            items.append(EvidenceItem(
                requirement=skill, importance=importance,
                strength=EvidenceStrength.MISSING, source=None))

        return EvidenceReport(
            evidence_items=items,
            missing_required=missing_required,
            weak_evidenced=weak_evidenced,
        )


__all__ = ["EvidenceAnalyzer", "EvidenceReport", "EvidenceItem", "EvidenceStrength"]
