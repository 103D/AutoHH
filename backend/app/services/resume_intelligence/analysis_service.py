"""Resume Analysis Service — orchestrates all analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.resume_intelligence.ats_analyzer import ATSAnalyzer, ATSReport
from app.services.resume_intelligence.bullet_analyzer import BulletAnalysis, BulletAnalyzer
from app.services.resume_intelligence.document import ResumeDocument, parse_resume_document
from app.services.resume_intelligence.evidence import EvidenceAnalyzer, EvidenceReport
from app.services.resume_intelligence.quality import ResumeQualityAnalyzer, ResumeQualityReport


@dataclass
class FullAnalysisReport:
    """Complete resume analysis combining all analyzers."""

    # Document parsing.
    document: ResumeDocument

    # Individual reports.
    ats: ATSReport | None = None
    quality: ResumeQualityReport | None = None
    bullet_analysis: list[list[BulletAnalysis]] = field(default_factory=list)
    evidence: EvidenceReport | None = None

    # Summary.
    overall_ats_score: int = 0
    overall_quality_score: int = 0
    recommendations: list[str] = field(default_factory=list)


class ResumeAnalysisService:
    """Orchestrates all resume intelligence analyzers.

    Example:
        >>> service = ResumeAnalysisService()
        >>> report = service.analyze_full(resume_text)
        >>> print(f"ATS: {report.overall_ats_score}, Quality: {report.overall_quality_score}")
    """

    def __init__(self) -> None:
        self.ats_analyzer = ATSAnalyzer()
        self.quality_analyzer = ResumeQualityAnalyzer()
        self.bullet_analyzer = BulletAnalyzer()
        self.evidence_analyzer = EvidenceAnalyzer()

    def analyze_full(
        self,
        resume_text: str,
        job_requirements: list[dict] | None = None,
    ) -> FullAnalysisReport:
        """Run full analysis on resume text.

        Args:
            resume_text: Raw resume text.
            job_requirements: Optional list of job requirements for evidence analysis.
                              Each should be a dict with 'skill' and 'importance' keys.
        """
        # Parse document.
        document = parse_resume_document(resume_text)

        # Run analyzers.
        ats_report = self.ats_analyzer.analyze(document)
        quality_report = self.quality_analyzer.analyze(document)
        bullet_results = self.bullet_analyzer.analyze(document)

        evidence_report = None
        if job_requirements:
            evidence_report = self.evidence_analyzer.analyze(document, job_requirements)

        # Generate recommendations.
        recommendations = self._generate_recommendations(
            ats_report, quality_report, bullet_results, evidence_report
        )

        return FullAnalysisReport(
            document=document,
            ats=ats_report,
            quality=quality_report,
            bullet_analysis=bullet_results,
            evidence=evidence_report,
            overall_ats_score=ats_report.score,
            overall_quality_score=quality_report.overall_score,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        ats: ATSReport,
        quality: ResumeQualityReport,
        bullets: list[list[BulletAnalysis]],
        evidence: EvidenceReport | None,
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        # ATS recommendations.
        if ats.critical_count > 0:
            recs.append(f"Fix {ats.critical_count} critical ATS issues")
        if ats.score < 70:
            recs.append("Improve ATS readability (avoid tables, special chars)")

        # Quality recommendations.
        if quality.critical_issues:
            for issue in quality.critical_issues[:3]:
                recs.append(issue)

        # Bullet recommendations.
        weak_count = sum(
            1 for entry in bullets for b in entry if b.strength.value in ("weak", "very_weak")
        )
        if weak_count > 3:
            recs.append(f"Improve {weak_count} weak bullet points — add results and metrics")

        # Evidence recommendations.
        if evidence:
            if evidence.missing_required:
                recs.append(f"Missing required skills: {', '.join(evidence.missing_required[:3])}")
            if evidence.weak_evidenced:
                recs.append(f"Weak evidence for: {', '.join(evidence.weak_evidenced[:3])}")

        return recs[:5]  # Limit to top 5


__all__ = ["ResumeAnalysisService", "FullAnalysisReport"]
