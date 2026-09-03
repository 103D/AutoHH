"""Unit tests for the resume parsing service."""

from pathlib import Path

import pytest

from app.core.exceptions import AIProviderError, ValidationError
from app.providers.ai.base import ParsedResume
from app.providers.ai.factory import FallbackAIProvider
from app.services.resume_parser import ResumeParserService


class FakeAIParser:
    """AI provider stub that returns a canned ParsedResume."""

    def __init__(self, result: ParsedResume | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def parse_resume(self, resume_text: str) -> ParsedResume:
        self.calls.append(resume_text)
        if self.error:
            raise self.error
        return self.result


def _make_parsed_resume(**overrides) -> ParsedResume:
    """Build a ParsedResume similar to what AI would return for a Russian resume."""
    data = {
        "full_name": "Муллахимов Дияр",
        "desired_positions": ["Аналитик данных", "Аналитик данных", "BI-аналитик"],
        "skills": ["SQL", "PostgreSQL", "Power BI", "Python", "SQL"],
        "technologies": {
            "Databases": ["PostgreSQL"],
            "analytics": ["Power BI", "pandas"],
        },
        "experience_years": 2,
        "experience_level": "senior",  # AI hallucination attempt, must be overridden
        "education": [
            {
                "degree": "Неоконченное высшее",
                "field": "Информационной технологии",
                "institution": "IITU",
                "graduation_year": 2025,
            }
        ],
        "languages": {"Русский": "Родной", "Английский": "C1"},
        "location": "Алматы",
        "salary_expectations": None,
        "employment_types": ["полная занятость", "unknown_type"],
        "work_formats": ["на месте работодателя", "удалённо", "unknown_format"],
        "relocation_possible": False,
        "business_trips_acceptable": True,
        "summary": "Аналитик данных с опытом в розничной сети",
    }
    data.update(overrides)
    return ParsedResume(**data)


LONG_RESUME_TEXT = "Резюме аналитика данных. " * 10  # > 50 chars


@pytest.fixture
def service() -> ResumeParserService:
    return ResumeParserService(ai_provider=FakeAIParser(result=_make_parsed_resume()))

class TestPostprocess:
    """Tests for deterministic post-processing of AI output."""

    async def test_parse_dedupes_and_cleans_lists(self, service):
        parsed = await service.parse(LONG_RESUME_TEXT)

        # "Аналитик данных" duplicated, "SQL" duplicated -> deduped
        assert parsed.desired_positions == ["Аналитик данных", "BI-аналитик"]
        assert parsed.skills == ["SQL", "PostgreSQL", "Power BI", "Python"]

    async def test_parse_normalizes_technology_categories(self, service):
        parsed = await service.parse(LONG_RESUME_TEXT)

        # Category keys are lowercased, values deduped
        assert set(parsed.technologies.keys()) == {"databases", "analytics"}
        assert parsed.technologies["databases"] == ["PostgreSQL"]
        assert parsed.technologies["analytics"] == ["Power BI", "pandas"]

    async def test_parse_maps_russian_work_formats(self, service):
        parsed = await service.parse(LONG_RESUME_TEXT)

        # Russian terms mapped to internal codes, unknown dropped
        assert parsed.work_formats == ["office", "remote"]

    async def test_parse_maps_russian_employment_types(self, service):
        parsed = await service.parse(LONG_RESUME_TEXT)

        assert parsed.employment_types == ["full_time"]

    async def test_experience_level_derived_deterministically(self, service):
        parsed = await service.parse(LONG_RESUME_TEXT)

        # AI claimed "senior" for 2 years - must be overridden to "middle"
        assert parsed.experience_years == 2
        assert parsed.experience_level == "middle"

    async def test_level_reset_when_experience_unknown(self):
        provider = FakeAIParser(
            result=_make_parsed_resume(experience_years=None, experience_level="senior")
        )
        service = ResumeParserService(ai_provider=provider)

        parsed = await service.parse(LONG_RESUME_TEXT)

        # No years -> level is reset to None, never trusted from AI
        assert parsed.experience_level is None

class TestDeriveLevel:
    """Tests for deterministic experience-level derivation."""

    def test_junior(self):
        assert ResumeParserService.derive_level(0) == "junior"
        assert ResumeParserService.derive_level(1) == "junior"

    def test_middle(self):
        assert ResumeParserService.derive_level(2) == "middle"
        assert ResumeParserService.derive_level(4) == "middle"

    def test_senior(self):
        assert ResumeParserService.derive_level(5) == "senior"
        assert ResumeParserService.derive_level(8) == "senior"

    def test_lead(self):
        assert ResumeParserService.derive_level(9) == "lead"
        assert ResumeParserService.derive_level(15) == "lead"

class TestToProfileData:
    """Tests for conversion into CandidateProfileCreate-compatible data."""

    def test_converts_parsed_resume(self, service):
        parsed = service.postprocess(_make_parsed_resume())
        data = service.to_profile_data(parsed)

        assert data["desired_positions"] == ["Аналитик данных", "BI-аналитик"]
        assert data["experience_years"] == 2
        assert data["experience_level"] == "middle"
        assert data["location"] == "Алматы"
        assert data["work_formats"] == ["office", "remote"]
        assert data["employment_types"] == ["full_time"]
        assert data["languages"] == {"Русский": "Родной", "Английский": "C1"}
        assert data["education"][0]["institution"] == "IITU"
        assert data["salary_currency"] == "KZT"
        # No salary in resume -> None (never invented)
        assert data["desired_salary_min"] is None
        assert data["desired_salary_max"] is None

    def test_salary_overrides(self, service):
        parsed = service.postprocess(_make_parsed_resume())
        data = service.to_profile_data(parsed, salary_min=400000, salary_max=700000)

        assert data["desired_salary_min"] == 400000
        assert data["desired_salary_max"] == 700000

    def test_salary_from_resume_used_when_no_override(self):
        provider = FakeAIParser(
            result=_make_parsed_resume(
                salary_expectations={"min": 300000, "max": 500000, "currency": "KZT"}
            )
        )
        service = ResumeParserService(ai_provider=provider)

        parsed = service.postprocess(provider.result)
        data = service.to_profile_data(parsed)

        assert data["desired_salary_min"] == 300000
        assert data["desired_salary_max"] == 500000

    def test_rejects_empty_positions(self):
        provider = FakeAIParser(result=_make_parsed_resume(desired_positions=[]))
        service = ResumeParserService(ai_provider=provider)

        parsed = service.postprocess(provider.result)
        with pytest.raises(ValidationError, match="desired positions"):
            service.to_profile_data(parsed)

    def test_rejects_empty_skills(self):
        provider = FakeAIParser(result=_make_parsed_resume(skills=[]))
        service = ResumeParserService(ai_provider=provider)

        parsed = service.postprocess(provider.result)
        with pytest.raises(ValidationError, match="no skills"):
            service.to_profile_data(parsed)

class TestParseErrors:
    """Tests for input validation and error wrapping."""

    async def test_rejects_too_short_text(self, service):
        with pytest.raises(ValidationError, match="too short"):
            await service.parse("short")

    async def test_rejects_empty_text(self, service):
        with pytest.raises(ValidationError):
            await service.parse("   ")

    async def test_wraps_ai_errors(self):
        provider = FakeAIParser(error=RuntimeError("API is down"))
        service = ResumeParserService(ai_provider=provider)

        with pytest.raises(AIProviderError, match="Failed to parse resume"):
            await service.parse(LONG_RESUME_TEXT)

    async def test_parse_file_missing(self, service, tmp_path: Path):
        with pytest.raises(ValidationError, match="not found"):
            await service.parse_file(tmp_path / "missing.txt")

    async def test_parse_file_reads_text(self, tmp_path: Path):
        provider = FakeAIParser(result=_make_parsed_resume())
        service = ResumeParserService(ai_provider=provider)
        resume_file = tmp_path / "resume.txt"
        resume_file.write_text(LONG_RESUME_TEXT, encoding="utf-8")

        parsed = await service.parse_file(resume_file)

        assert parsed.full_name == "Муллахимов Дияр"
        assert provider.calls == [LONG_RESUME_TEXT]


class TestFallbackProvider:
    """Tests for parse_resume delegation in FallbackAIProvider."""

    async def test_primary_used(self):
        primary = FakeAIParser(result=_make_parsed_resume(experience_years=3))
        fallback = FakeAIParser(result=_make_parsed_resume(experience_years=10))
        provider = FallbackAIProvider(primary, fallback)

        result = await provider.parse_resume(LONG_RESUME_TEXT)

        assert result.experience_years == 3
        assert primary.calls and not fallback.calls

    async def test_fallback_used_on_primary_failure(self):
        primary = FakeAIParser(error=RuntimeError("down"))
        fallback = FakeAIParser(result=_make_parsed_resume(experience_years=10))
        provider = FallbackAIProvider(primary, fallback)

        result = await provider.parse_resume(LONG_RESUME_TEXT)

        assert result.experience_years == 10
        assert fallback.calls

    async def test_raises_without_fallback(self):
        primary = FakeAIParser(error=RuntimeError("down"))
        provider = FallbackAIProvider(primary, None)

        with pytest.raises(RuntimeError, match="down"):
            await provider.parse_resume(LONG_RESUME_TEXT)
