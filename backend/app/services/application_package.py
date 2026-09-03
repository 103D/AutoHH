"""Application package service: adapted resume + cover letter + diff.

Builds the complete application package for manual applying:
- adapts the original resume for the specific job (AI)
- generates a cover letter (AI)
- validates both against hallucinations (AntiHallucinationValidator)
- computes a text diff and keyword-coverage improvement
- stores everything in Application.package_data and moves the status to PREPARED
"""

import difflib
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.providers.ai.factory import create_ai_provider
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.application import ApplicationUpdate
from app.services.application import ApplicationService
from app.services.validation import AntiHallucinationValidator

logger = get_logger(__name__)

COMMON_WORDS = {
    "the", "and", "for", "with", "you", "are", "our", "your", "this",
    "that", "from", "have", "will", "can", "not", "but", "all", "any",
    "who", "what", "when", "how", "why", "was", "were", "been", "being",
    "their", "there", "them", "then", "than", "into", "out", "about",
    "they", "she", "him", "her", "his", "its", "one", "two", "new",
    "use", "used", "using", "get", "got", "put", "set", "let",
}


class ApplicationPackageService:
    """Builds and stores the application package for a specific job."""

    def __init__(
        self,
        application_service: ApplicationService,
        job_repo: JobRepository,
        match_repo: MatchResultRepository,
        ai_provider: Any = None,
        validator: AntiHallucinationValidator | None = None,
    ):
        self.application_service = application_service
        self.job_repo = job_repo
        self.match_repo = match_repo
        self.ai_provider = ai_provider or create_ai_provider()
        self.validator = validator or AntiHallucinationValidator()

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Tokenize text into meaningful keywords."""
        tokens = re.findall(r"[a-zA-Zа-яА-Я0-9+.#-]+", text.lower())
        return {t for t in tokens if len(t) > 2 and t not in COMMON_WORDS}

    def _build_key_requirements(
        self,
        profile: CandidateProfile,
        job: Job,
        match: Any | None,
    ) -> list[str]:
        """Key requirements to highlight: title + missing skills (or top skills)."""
        requirements = [job.title]
        if match is not None and match.missing_skills:
            requirements.extend(str(s) for s in match.missing_skills[:5])
        elif profile.skills:
            requirements.extend(str(s) for s in profile.skills[:5])
        return requirements[:8]

    def _candidate_name(self, profile: CandidateProfile) -> str:
        prefs = profile.additional_preferences or {}
        return str(prefs.get("full_name") or "Candidate")

    def _compute_diff(self, original: str, adapted: str) -> dict:
        """Unified text diff plus added/removed line counts."""
        diff = list(
            difflib.unified_diff(
                original.splitlines(),
                adapted.splitlines(),
                fromfile="original",
                tofile="adapted",
                lineterm="",
            )
        )
        added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
        return {
            "added_lines": added,
            "removed_lines": removed,
            "unified_diff": "\n".join(diff),
        }

    def _coverage(self, resume_text: str, job: Job) -> float:
        """Share of job keywords covered by the resume text, %."""
        job_tokens = self._tokenize(f"{job.title} {job.description}")
        if not job_tokens:
            return 0.0
        covered = job_tokens & self._tokenize(resume_text)
        return round(len(covered) / len(job_tokens) * 100, 1)

    def _key_matches(
        self, profile: CandidateProfile, match: Any | None
    ) -> list[str]:
        """Surface top skills the candidate has that match the job."""
        if match is not None and getattr(match, "matched_skills", None):
            return [str(s) for s in match.matched_skills[:5]]
        return [str(s) for s in (profile.skills or [])[:5]]

    def _deterministic_adapt_resume(
        self, resume_text: str, job: Job, key_requirements: list[str]
    ) -> str:
        """Append a 'Targeted Highlights' block when AI is unavailable.

        Keeps the original resume intact and adds a small block that surfaces
        the key requirements for the job, so the diff/coverage metrics still
        have something meaningful to show. Never fabricates experience.
        """
        highlights = "".join(f"- {req}\n" for req in key_requirements)
        block = (
            "\n\n# Targeted Highlights (auto-generated)\n"
            f"Position: {job.title} @ {job.company}\n"
            "Relevant focus areas:\n"
            f"{highlights}"
        )
        return resume_text.rstrip() + block

    def _template_cover_letter(
        self,
        profile: CandidateProfile,
        job: Job,
        key_matches: list[str],
    ) -> str:
        """Plain text cover-letter template used when AI is unavailable."""
        name = self._candidate_name(profile)
        matches = ", ".join(key_matches) if key_matches else "the role's core stack"
        return (
            f"Dear Hiring Team at {job.company},\n\n"
            f"I am applying for the {job.title} position. With my background in "
            f"{matches}, I am confident I can contribute to your team.\n\n"
            "My resume provides additional detail on the projects and technologies "
            "I have worked with. I would welcome the opportunity to discuss how "
            "my experience aligns with the goals of your team.\n\n"
            f"Best regards,\n{name}\n"
        )

    async def build_package(self, application_id) -> Any:
        """Generate and store the application package, moving status to PREPARED."""
        application = await self.application_service.get_application(application_id)

        job = await self.job_repo.get(application.job_id)
        if not job:
            raise NotFoundError(f"Job {application.job_id} not found")

        profile = await self.candidate_service().get_profile(
            application.candidate_profile_id
        )

        resume_text = (profile.resume_versions or {}).get("original")
        if not resume_text:
            raise ValidationError(
                "No original resume stored in profile.resume_versions['original']. "
                "Run scripts/init_candidate.py first."
            )

        match = await self.match_repo.get_by_job_and_candidate(
            application.job_id, application.candidate_profile_id
        )
        key_requirements = self._build_key_requirements(profile, job, match)

        # 1) Adapt resume (AI) - with graceful fallback when AI is unavailable
        try:
            adapted_resume = await self.ai_provider.adapt_resume(
                resume_text=resume_text,
                job_title=job.title,
                job_description=job.description,
                key_requirements=key_requirements,
            )
            ai_used = True
        except Exception as e:
            logger.warning(
                f"AI adapt_resume failed ({e}); using deterministic fallback"
            )
            adapted_resume = self._deterministic_adapt_resume(
                resume_text, job, key_requirements
            )
            ai_used = False

        # 2) Cover letter (AI) - with graceful fallback
        try:
            cover_letter = await self.ai_provider.generate_cover_letter(
                candidate_name=self._candidate_name(profile),
                job_title=job.title,
                company_name=job.company,
                job_description=job.description,
                key_matches=self._key_matches(profile, match),
            )
        except Exception as e:
            logger.warning(
                f"AI generate_cover_letter failed ({e}); using template fallback"
            )
            cover_letter = self._template_cover_letter(
                profile, job, self._key_matches(profile, match)
            )

        # 3) Anti-hallucination validation
        resume_validation = self.validator.validate_resume(resume_text, adapted_resume)
        profile_dict = {
            "skills": profile.skills,
            "technologies": profile.technologies,
            "experience_years": profile.experience_years,
            "desired_positions": profile.desired_positions,
            "education": profile.education,
        }
        letter_validation = self.validator.validate_cover_letter(profile_dict, cover_letter)

        # 4) Diff + improvement metrics
        coverage_before = self._coverage(resume_text, job)
        coverage_after = self._coverage(adapted_resume, job)

        package = {
            "adapted_resume": adapted_resume,
            "cover_letter": cover_letter,
            "diff": self._compute_diff(resume_text, adapted_resume),
            "keyword_coverage": {
                "before": coverage_before,
                "after": coverage_after,
            },
            "improvement_score": round(coverage_after - coverage_before, 1),
            "validation": {
                "resume": {
                    "is_valid": resume_validation.is_valid,
                    "issues": resume_validation.issues,
                },
                "cover_letter": {
                    "is_valid": letter_validation.is_valid,
                    "issues": letter_validation.issues,
                },
            },
            "generated_at": datetime.now(UTC).isoformat(),
            "ai_model": settings.ai_model,
            "ai_used": ai_used,
        }

        # 5) Persist: status PREPARED + package_data
        application = await self.application_service.update_application(
            application.id,
            ApplicationUpdate(status="PREPARED", comment="Application package generated"),
        )
        application = await self.application_service.application_repo.update(
            application, {"package_data": package}
        )

        logger.info(
            f"Application package built: {application.id} "
            f"(improvement {package['improvement_score']}pp, "
            f"resume valid={resume_validation.is_valid}, "
            f"letter valid={letter_validation.is_valid})"
        )
        return application

    def candidate_service(self):
        """Shortcut to the candidate service (kept injectable for tests)."""
        return self.application_service.candidate_service

    def _key_matches(self, profile: CandidateProfile, match: Any | None) -> list[str]:
        """Key matching points for the cover letter."""
        if match is not None and match.strong_matches:
            return [str(s) for s in match.strong_matches[:5]]
        return [str(s) for s in profile.skills[:5]]
