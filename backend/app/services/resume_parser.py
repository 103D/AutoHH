"""Resume parsing service: raw resume text -> structured candidate profile data."""

from pathlib import Path

from app.core.exceptions import AIProviderError, ValidationError
from app.core.logging import get_logger
from app.providers.ai.base import AIProvider, ParsedResume
from app.providers.ai.factory import create_ai_provider

logger = get_logger(__name__)

# Normalization maps for values stated in Russian resumes
WORK_FORMAT_ALIASES = {
    "удалённо": "remote",
    "удаленно": "remote",
    "remote": "remote",
    "гибрид": "hybrid",
    "гибридный формат": "hybrid",
    "гибридный": "hybrid",
    "hybrid": "hybrid",
    "на месте работодателя": "office",
    "офис": "office",
    "office": "office",
}

EMPLOYMENT_TYPE_ALIASES = {
    "полная занятость": "full_time",
    "неполная занятость": "part_time",
    "частичная занятость": "part_time",
    "проектная работа": "contract",
    "контракт": "contract",
    "стажировка": "internship",
    "волонтёрство": "volunteer",
    "волонтерство": "volunteer",
}

# Deterministic experience-level thresholds (anti-hallucination: level is never
# taken from AI output, always derived from years of experience)
LEVEL_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (9, "lead"),
    (5, "senior"),
    (2, "middle"),
    (0, "junior"),
)


def _normalize_list(values: list[str] | None) -> list[str]:
    """Normalize a list of strings: strip, drop empties, dedupe case-insensitively."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = " ".join(str(value).split()).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result

class ResumeParserService:
    """Parses raw resume text into structured candidate profile data.

    The heavy lifting (fact extraction) is done by the AI provider, then a
    deterministic post-processing step normalizes and sanitizes the result.
    """

    def __init__(self, ai_provider: AIProvider | None = None):
        self.ai_provider = ai_provider or create_ai_provider()

    async def parse_file(self, path: Path) -> ParsedResume:
        """Read a resume file and parse it into structured data."""
        if not path.exists():
            raise ValidationError(f"Resume file not found: {path}")

        resume_text = path.read_text(encoding="utf-8")
        return await self.parse(resume_text)

    async def parse(self, resume_text: str) -> ParsedResume:
        """Parse resume text via AI and post-process the result."""
        if not resume_text or len(resume_text.strip()) < 50:
            raise ValidationError("Resume text is empty or too short to parse")

        try:
            parsed = await self.ai_provider.parse_resume(resume_text)
        except Exception as e:
            raise AIProviderError(f"Failed to parse resume: {e}") from e

        return self.postprocess(parsed)

    def postprocess(self, parsed: ParsedResume) -> ParsedResume:
        """Apply deterministic normalization to AI parsing output.

        Anti-hallucination measures:
        - experience_level is always derived from experience_years, never from AI
        - work formats / employment types are mapped to internal codes
        - skills, positions and technologies are cleaned and deduplicated
        """
        parsed.desired_positions = _normalize_list(parsed.desired_positions)
        parsed.skills = _normalize_list(parsed.skills)

        normalized_technologies: dict[str, list[str]] = {}
        for category, skills in (parsed.technologies or {}).items():
            category_key = " ".join(str(category).split()).strip().lower() or "other"
            items = _normalize_list([str(s) for s in (skills or [])])
            if items:
                merged = _normalize_list(normalized_technologies.get(category_key, []) + items)
                normalized_technologies[category_key] = merged
        parsed.technologies = normalized_technologies

        parsed.employment_types = _normalize_list(
            normalized
            for normalized in (
                EMPLOYMENT_TYPE_ALIASES.get(str(t).strip().lower())
                for t in parsed.employment_types
            )
            if normalized
        )
        parsed.work_formats = _normalize_list(
            normalized
            for normalized in (
                WORK_FORMAT_ALIASES.get(str(f).strip().lower()) for f in parsed.work_formats
            )
            if normalized
        )

        parsed.languages = {
            " ".join(str(name).split()).strip(): " ".join(str(level).split()).strip()
            for name, level in (parsed.languages or {}).items()
            if str(name).strip() and str(level).strip()
        }

        # Deterministic level: never trust the model on this field; when the
        # years are unknown the level stays unknown too
        parsed.experience_level = (
            self.derive_level(parsed.experience_years)
            if parsed.experience_years is not None
            else None
        )

        return parsed

    @staticmethod
    def derive_level(experience_years: int) -> str:
        """Derive experience level deterministically from years of experience."""
        for min_years, level in LEVEL_THRESHOLDS:
            if experience_years >= min_years:
                return level
        return "junior"

    def to_profile_data(
        self,
        parsed: ParsedResume,
        salary_min: int | None = None,
        salary_max: int | None = None,
        salary_currency: str = "KZT",
    ) -> dict:
        """Convert a parsed resume into a CandidateProfileCreate-compatible dict.

        Optional salary overrides are useful when the resume doesn't state
        salary expectations (the AI never invents them).
        """
        if not parsed.desired_positions:
            raise ValidationError("Parsed resume has no desired positions")
        if not parsed.skills:
            raise ValidationError("Parsed resume has no skills")

        salary_expectations = parsed.salary_expectations
        resolved_min = salary_min
        if resolved_min is None and salary_expectations:
            resolved_min = salary_expectations.min
        resolved_max = salary_max
        if resolved_max is None and salary_expectations:
            resolved_max = salary_expectations.max
        resolved_currency = salary_currency
        if salary_expectations and salary_expectations.currency:
            resolved_currency = salary_expectations.currency

        return {
            "desired_positions": parsed.desired_positions,
            "skills": parsed.skills,
            "technologies": parsed.technologies,
            "experience_years": parsed.experience_years,
            "experience_level": parsed.experience_level,
            "education": [edu.model_dump() for edu in parsed.education] or None,
            "languages": parsed.languages,
            "location": parsed.location,
            "desired_salary_min": resolved_min,
            "desired_salary_max": resolved_max,
            "salary_currency": resolved_currency,
            "employment_types": parsed.employment_types or None,
            "work_formats": parsed.work_formats or None,
            "relocation_possible": parsed.relocation_possible,
            "business_trips_acceptable": parsed.business_trips_acceptable,
        }
