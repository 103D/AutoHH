"""Resume Quality Analyzer — deterministic quality scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.services.resume_intelligence.document import ResumeDocument


class QualityDimension(Enum):
    STRUCTURE = "structure"
    CONTENT = "content"
    EXPERIENCE = "experience"
    CLARITY = "clarity"
    IMPACT = "impact"


@dataclass
class QualityScore:
    dimension: QualityDimension
    score: int
    issues: list[str] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)


@dataclass
class ResumeQualityReport:
    overall_score: int
    dimension_scores: list[QualityScore] = field(default_factory=list)
    summary: str = ""

    @property
    def critical_issues(self) -> list[str]:
        return [i for ds in self.dimension_scores for i in ds.issues if ds.score < 40]


class ResumeQualityAnalyzer:
    """Analyzes resume quality across multiple dimensions."""

    def analyze(self, doc: ResumeDocument) -> ResumeQualityReport:
        dim_scores = [
            self._structure_score(doc),
            self._content_score(doc),
            self._experience_score(doc),
            self._clarity_score(doc),
            self._impact_score(doc),
        ]
        overall = sum(ds.score for ds in dim_scores) // len(dim_scores)
        return ResumeQualityReport(
            overall_score=overall,
            dimension_scores=dim_scores,
            summary=self._generate_summary(dim_scores),
        )

    def _structure_score(self, doc: ResumeDocument) -> QualityScore:
        issues, positives, score = [], [], 100
        required = {"experience", "skills"}
        for sec in required:
            if sec not in doc.section_keys:
                issues.append(f"Missing '{sec}' section")
                score -= 20
        if not doc.phones and not doc.emails:
            issues.append("No contact info")
            score -= 15
        return QualityScore(dimension=QualityDimension.STRUCTURE, score=max(0, score), issues=issues, positives=positives)

    def _content_score(self, doc: ResumeDocument) -> QualityScore:
        issues, positives, score = [], [], 100
        bullets = sum(len(e.bullets) for e in doc.experience)
        if bullets < 3:
            issues.append(f"Only {bullets} bullets")
            score -= 15
        if len(doc.section_text("skills")) < 20:
            issues.append("Skills section too short")
            score -= 10
        return QualityScore(dimension=QualityDimension.CONTENT, score=max(0, score), issues=issues, positives=positives)

    def _experience_score(self, doc: ResumeDocument) -> QualityScore:
        issues, positives, score = [], [], 100
        if not doc.experience:
            return QualityScore(
                dimension=QualityDimension.EXPERIENCE,
                score=20,
                issues=["No structured experience entries"],
                positives=positives,
            )
        for i, e in enumerate(doc.experience):
            if not e.bullets:
                issues.append(f"Entry {i+1} no bullets")
                score -= 10
        return QualityScore(dimension=QualityDimension.EXPERIENCE, score=max(0, score), issues=issues, positives=positives)

    def _clarity_score(self, doc: ResumeDocument) -> QualityScore:
        issues, positives, score = [], [], 100
        if doc.total_words < 100:
            issues.append("Too short")
            score -= 20
        elif doc.total_words > 2000:
            issues.append("Too long")
            score -= 10
        return QualityScore(dimension=QualityDimension.CLARITY, score=max(0, score), issues=issues, positives=positives)

    def _impact_score(self, doc: ResumeDocument) -> QualityScore:
        issues, positives, score = [], [], 50
        metrics = sum(1 for e in doc.experience for b in e.bullets if any(c.isdigit() for c in b))
        if metrics >= 3:
            score = 80
            positives.append(f"{metrics} metrics")
        return QualityScore(dimension=QualityDimension.IMPACT, score=max(0, score), issues=issues, positives=positives)

    def _generate_summary(self, dim_scores: list[QualityScore]) -> str:
        critical = [ds for ds in dim_scores if ds.score < 50]
        if critical:
            return f"Focus on: {', '.join(ds.dimension.value for ds in critical)}"
        return "Resume looks good"


__all__ = ["ResumeQualityAnalyzer", "ResumeQualityReport", "QualityScore", "QualityDimension"]
