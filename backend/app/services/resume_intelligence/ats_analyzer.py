"""Deterministic ATS analyzer."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from app.services.resume_intelligence.document import ResumeDocument
from app.services.skill_taxonomy import canonical_key

_SKILL_SEPARATOR_RE = re.compile(r"[,;\n•|]+")
_UNSUPPORTED_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ATSSeverity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"


@dataclass
class ATSIssue:
    check: str
    severity: ATSSeverity
    detail: str
    location: str | None = None


@dataclass
class ATSReport:
    score: int
    issues: list[ATSIssue] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ATSSeverity.CRITICAL)


class ATSAnalyzer:
    """Deterministic ATS analyzer."""

    def analyze(self, doc: ResumeDocument) -> ATSReport:
        issues, passed = [], []

        # Table detection.
        if "|" in doc.raw_text or "╔" in doc.raw_text:
            issues.append(ATSIssue("table", ATSSeverity.CRITICAL, "Table detected", "document"))
        else:
            passed.append("table")

        # Core sections.
        if "experience" not in doc.section_keys and not doc.experience:
            issues.append(ATSIssue("missing_exp", ATSSeverity.CRITICAL, "No experience section", "document"))
        else:
            passed.append("experience")

        if "skills" not in doc.section_keys:
            issues.append(ATSIssue("missing_skills", ATSSeverity.CRITICAL, "No skills section", "document"))
        else:
            passed.append("skills")

        if "education" not in doc.section_keys:
            issues.append(ATSIssue("missing_education", ATSSeverity.WARNING, "No education section", "document"))
        else:
            passed.append("education")

        # Contact check.
        if not doc.phones and not doc.emails:
            issues.append(ATSIssue("no_contact", ATSSeverity.CRITICAL, "No contact info", "preamble"))
        else:
            passed.append("contact")

        if doc.experience and any(not entry.period for entry in doc.experience):
            issues.append(
                ATSIssue(
                    "missing_experience_dates",
                    ATSSeverity.WARNING,
                    "One or more experience entries have no date range",
                    "experience",
                )
            )
        elif doc.experience:
            passed.append("experience_dates")

        skill_items = [
            canonical_key(item.strip().lstrip("-*–— "))
            for item in _SKILL_SEPARATOR_RE.split(doc.section_text("skills"))
            if item.strip()
        ]
        duplicates = sorted(
            skill for skill, count in Counter(skill_items).items() if skill and count > 1
        )
        if duplicates:
            issues.append(
                ATSIssue(
                    "duplicate_skills",
                    ATSSeverity.WARNING,
                    f"Duplicate skills: {', '.join(duplicates)}",
                    "skills",
                )
            )
        elif "skills" in doc.section_keys:
            passed.append("duplicate_skills")

        if _UNSUPPORTED_CONTROL_RE.search(doc.raw_text):
            issues.append(
                ATSIssue(
                    "unsupported_characters",
                    ATSSeverity.WARNING,
                    "Unsupported control characters detected",
                    "document",
                )
            )
        else:
            passed.append("supported_characters")

        # Score calculation.
        score = 100
        for i in issues:
            score -= 20 if i.severity == ATSSeverity.CRITICAL else 5

        return ATSReport(score=max(0, score), issues=issues, passed_checks=passed)


__all__ = ["ATSAnalyzer", "ATSReport", "ATSIssue", "ATSSeverity"]
