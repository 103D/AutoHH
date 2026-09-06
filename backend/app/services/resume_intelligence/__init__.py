"""Resume Intelligence — deterministic resume analysis layer.

This package implements the Resume Intelligence subsystem (task spec:
PROMPT_FINAL.MD). It analyses a resume as a *document* using deterministic
rules — no LLM is required for structure, ATS, bullet, evidence and quality
analysis. The LLM is only used (optionally) for controlled rewriting.

Public entry points:

- ``ResumeDocument``  — deterministic parse of a resume text into sections
  (``document.py``).
- ``ATSAnalyzer``     — deterministic ATS / machine-readability checks
  (``ats_analyzer.py``).
- ``BulletAnalyzer``  — per-bullet action/result/metric analysis
  (``bullet_analyzer.py``).
- ``ResumeQualityAnalyzer`` — explainable resume quality scoring
  (``quality.py``).
- ``EvidenceAnalyzer`` — requirement -> candidate evidence -> strength map
  (``evidence.py``).
- ``ResumeAnalysisService`` — orchestrates the full pipeline and persists the
  result (``analysis_service.py``).

Design principles (shared with ``app.services.scoring``):

* Every score is explainable — a breakdown is always produced.
* Deterministic computations are pure functions / small classes, unit-testable
  without a database or an LLM.
* No invented facts: analysis only *describes* what is present in the resume.
"""

from app.services.resume_intelligence.analysis_service import (
    FullAnalysisReport,
    ResumeAnalysisService,
)
from app.services.resume_intelligence.ats_analyzer import (
    ATSAnalyzer,
    ATSIssue,
    ATSReport,
    ATSSeverity,
)
from app.services.resume_intelligence.bullet_analyzer import (
    BulletAnalysis,
    BulletAnalyzer,
    BulletStrength,
)
from app.services.resume_intelligence.document import (
    EducationBlock,
    ExperienceEntry,
    ParsedSection,
    ResumeDocument,
    parse_resume_document,
)
from app.services.resume_intelligence.evidence import (
    EvidenceAnalyzer,
    EvidenceItem,
    EvidenceReport,
    EvidenceStrength,
)
from app.services.resume_intelligence.quality import (
    QualityDimension,
    QualityScore,
    ResumeQualityAnalyzer,
    ResumeQualityReport,
)

__all__ = [
    # Document parsing
    "EducationBlock",
    "ExperienceEntry",
    "ParsedSection",
    "ResumeDocument",
    "parse_resume_document",
    # ATS
    "ATSAnalyzer",
    "ATSReport",
    "ATSIssue",
    "ATSSeverity",
    # Bullet
    "BulletAnalyzer",
    "BulletAnalysis",
    "BulletStrength",
    # Quality
    "ResumeQualityAnalyzer",
    "ResumeQualityReport",
    "QualityScore",
    "QualityDimension",
    # Evidence
    "EvidenceAnalyzer",
    "EvidenceReport",
    "EvidenceItem",
    "EvidenceStrength",
    # Orchestration
    "ResumeAnalysisService",
    "FullAnalysisReport",
]
