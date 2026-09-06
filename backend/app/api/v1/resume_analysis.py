"""Resume Analysis API."""

from fastapi import APIRouter, HTTPException, status

from app.schemas.resume import ResumeAnalysisRequest, ResumeAnalysisResponse
from app.services.resume_intelligence import ResumeAnalysisService

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post(
    "/analyze",
    response_model=ResumeAnalysisResponse,
    summary="Analyze resume quality and ATS readiness",
    description="""
Deterministic resume analysis without LLM. Analyzes:
- ATS readability (tables, sections, contact info)
- Resume quality (structure, content, experience, clarity, impact)
- Bullet point strength (action, result, metrics)
- Evidence mapping (job requirements → resume evidence)

Optionally accepts job requirements to run evidence analysis.
""",
)
async def analyze_resume(request: ResumeAnalysisRequest) -> ResumeAnalysisResponse:
    """Analyze a resume text."""
    if not request.resume_text or len(request.resume_text.strip()) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume text must be at least 50 characters",
        )

    service = ResumeAnalysisService()
    report = service.analyze_full(
        resume_text=request.resume_text,
        job_requirements=request.job_requirements,
    )

    # Build response.
    ats_issues = []
    if report.ats:
        for issue in report.ats.issues:
            ats_issues.append({
                "check": issue.check,
                "severity": issue.severity.value,
                "detail": issue.detail,
                "location": issue.location,
            })

    quality_issues = []
    if report.quality:
        for ds in report.quality.dimension_scores:
            quality_issues.append({
                "dimension": ds.dimension.value,
                "score": ds.score,
                "issues": ds.issues,
                "positives": ds.positives,
            })

    evidence_items = []
    if report.evidence:
        for item in report.evidence.evidence_items:
            evidence_items.append({
                "requirement": item.requirement,
                "importance": item.importance,
                "strength": item.strength.value,
                "source": item.source,
                "details": item.details,
            })

    bullet_summary = []
    for experience_index, entry_bullets in enumerate(report.bullet_analysis):
        for bullet_index, b in enumerate(entry_bullets):
            bullet_summary.append({
                "bullet": b.bullet,
                "experience_index": experience_index,
                "bullet_index": bullet_index,
                "strength": b.strength.value,
                "has_action": b.has_action,
                "has_result": b.has_result,
                "has_metric": b.has_metric,
                "issues": b.issues,
            })

    bullet_limit = 20

    return ResumeAnalysisResponse(
        overall_ats_score=report.overall_ats_score,
        overall_quality_score=report.overall_quality_score,
        ats_issues=ats_issues,
        ats_passed_checks=report.ats.passed_checks if report.ats else [],
        quality_issues=quality_issues,
        bullet_analysis=bullet_summary[:bullet_limit],
        bullet_analysis_total=len(bullet_summary),
        bullet_analysis_truncated=len(bullet_summary) > bullet_limit,
        evidence=evidence_items,
        missing_required=report.evidence.missing_required if report.evidence else [],
        weak_evidenced=report.evidence.weak_evidenced if report.evidence else [],
        recommendations=report.recommendations,
    )
