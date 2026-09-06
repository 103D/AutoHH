"""Unit tests for the application package service."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.services.application_package import ApplicationPackageService

ORIGINAL_RESUME = (
    "Муллахимов Дияр\nАналитик данных\nОпыт 2 года\n"
    "Навыки: SQL, PostgreSQL, Python, pandas, Power BI\n"
    "Анализ данных розничной сети, отчеты и автоматизация.\n"
)

ADAPTED_RESUME = (
    "Муллахимов Дияр\nData Analyst\nОпыт 2 года (dashboards)\n"
    "Навыки: SQL, PostgreSQL, Python, pandas, Power BI, dashboards, etl\n"
    "Анализ данных розничной сети, dashboards, etl-процессы, аналитик.\n"
)

COVER_LETTER = "Здравствуйте! Меня заинтересовала вакансия аналитика. Есть опыт SQL и Python."

JOB = SimpleNamespace(
    id=uuid4(),
    title="Data Analyst",
    company="Kaspi.kz",
    description=(
        "We need an analyst with SQL, Python, dashboards and etl experience. "
        "Experience with a b2c retailer is a plus."
    ),
    url="https://hh.kz/vacancy/1",
)

PROFILE = SimpleNamespace(
    id=uuid4(),
    skills=["SQL", "PostgreSQL", "Python", "pandas", "Power BI", "ETL"],
    technologies={"databases": ["PostgreSQL"]},
    experience_years=2,
    desired_positions=["Аналитик данных", "Data Analyst"],
    education=[{"degree": "Bachelor", "field": "IT"}],
    experience=[{"company": "Safia", "title": "Аналитик данных"}],
    projects=[{"name": "Retail Dashboard", "role": "Data Analyst"}],
    certifications=[{"name": "Google Data Analytics", "issuer": "Google"}],
    additional_preferences={"full_name": "Дияр Муллахимов"},
    resume_versions={"original": ORIGINAL_RESUME},
)


class FakeAIPackage:
    """AI provider stub for adapt_resume / generate_cover_letter."""

    def __init__(self, adapted: str = ADAPTED_RESUME, letter: str = COVER_LETTER):
        self.adapted = adapted
        self.letter = letter
        self.adapt_calls: list[dict] = []

    async def adapt_resume(self, resume_text, job_title, job_description, key_requirements):
        self.adapt_calls.append(
            {
                "resume_text": resume_text,
                "job_title": job_title,
                "key_requirements": key_requirements,
            }
        )
        return self.adapted

    async def generate_cover_letter(
        self, candidate_name, job_title, company_name, job_description, key_matches, style="professional"
    ):
        return self.letter


async def _async(value):
    return value


def _make_service(adapted: str = ADAPTED_RESUME):
    """Build the package service with mocked application service and repos."""
    application = SimpleNamespace(
        id=uuid4(),
        job_id=JOB.id,
        candidate_profile_id=PROFILE.id,
        status="SAVED",
        package_data=None,
    )

    async def get_application(app_id):
        return application

    async def update_application(app_id, update):
        application.status = "PREPARED"
        return application

    async def update_repo(obj, data):
        for key, value in data.items():
            setattr(obj, key, value)
        return obj

    application_service = SimpleNamespace(
        get_application=get_application,
        update_application=update_application,
        application_repo=SimpleNamespace(update=update_repo),
        candidate_service=SimpleNamespace(
            get_profile=lambda profile_id: _async(PROFILE)
        ),
    )

    async def get_job(job_id):
        return JOB

    async def get_match(job_id, profile_id):
        return SimpleNamespace(
            missing_skills=["Tableau"],
            strong_matches=["SQL", "Python"],
        )

    ai = FakeAIPackage(adapted)
    service = ApplicationPackageService(
        application_service,
        SimpleNamespace(get=get_job),
        SimpleNamespace(get_by_job_and_candidate=get_match),
        ai_provider=ai,
    )
    return service, application, ai

class TestBuildPackage:
    """Tests for the full package build flow."""

    @pytest.mark.asyncio
    async def test_builds_package_and_sets_prepared(self):
        service, application, ai = _make_service()

        result = await service.build_package(application.id)

        assert result.status == "PREPARED"
        package = result.package_data
        assert package["adapted_resume"] == ADAPTED_RESUME
        assert package["cover_letter"] == COVER_LETTER
        assert package["diff"]["added_lines"] > 0
        assert package["generated_at"]
        assert package["ai_model"]

        # Resume was adapted from the original stored text
        assert ai.adapt_calls[0]["resume_text"] == ORIGINAL_RESUME
        assert ai.adapt_calls[0]["job_title"] == "Data Analyst"
        # Job requirements are context for the rewriter, not candidate claims.
        assert "Tableau" in ai.adapt_calls[0]["key_requirements"]

    @pytest.mark.asyncio
    async def test_validation_issues_detected(self):
        hallucinated = ORIGINAL_RESUME + "\nРаботал с React и Kubernetes.\n"
        service, application, _ = _make_service(adapted=hallucinated)

        with pytest.raises(ValidationError, match="unsupported claims"):
            await service.build_package(application.id)

        assert application.status == "SAVED"
        assert application.package_data is None

    @pytest.mark.asyncio
    async def test_improvement_score_positive(self):
        service, application, _ = _make_service()

        result = await service.build_package(application.id)

        coverage = result.package_data["keyword_coverage"]
        # The adapted resume mentions dashboards/etl from the job description
        assert coverage["after"] > coverage["before"]
        assert result.package_data["improvement_score"] > 0

    @pytest.mark.asyncio
    async def test_missing_resume_raises(self):
        service, application, _ = _make_service()
        # Break the profile: no stored resume
        service.application_service.candidate_service = SimpleNamespace(
            get_profile=lambda profile_id: _async(
                SimpleNamespace(
                    id=PROFILE.id,
                    skills=["SQL"],
                    technologies={},
                    experience_years=2,
                    desired_positions=["Analyst"],
                    education=[],
                    additional_preferences={},
                    resume_versions={},
                )
            )
        )

        with pytest.raises(ValidationError, match="No original resume"):
            await service.build_package(application.id)

    @pytest.mark.asyncio
    async def test_missing_job_raises(self):
        service, application, _ = _make_service()

        async def get_job(job_id):
            return None

        service.job_repo = SimpleNamespace(get=get_job)

        with pytest.raises(NotFoundError):
            await service.build_package(application.id)

    @pytest.mark.asyncio
    async def test_ai_failure_keeps_original_resume_without_claiming_job_requirements(self):
        service, application, _ = _make_service()

        async def fail_adaptation(**_kwargs):
            raise RuntimeError("provider unavailable")

        service.ai_provider.adapt_resume = fail_adaptation

        result = await service.build_package(application.id)

        assert result.status == "PREPARED"
        assert result.package_data["adapted_resume"] == ORIGINAL_RESUME
        assert result.package_data["ai_used"] is False
        assert "Tableau" not in result.package_data["adapted_resume"]

    @pytest.mark.asyncio
    async def test_cover_letter_may_name_target_job_without_claiming_it_as_experience(self):
        service, application, _ = _make_service()
        PROFILE.desired_positions = ["Аналитик данных"]
        service.ai_provider.adapted = ORIGINAL_RESUME
        service.ai_provider.letter = (
            "I am applying for the Data Analyst position. "
            "My verified experience includes Python and SQL."
        )

        try:
            result = await service.build_package(application.id)
        finally:
            PROFILE.desired_positions = ["Аналитик данных", "Data Analyst"]

        assert result.status == "PREPARED"
        assert result.package_data["validation"]["cover_letter"]["is_valid"] is True

class TestDiffHelpers:
    """Tests for diff and coverage helpers."""

    def test_compute_diff_counts(self):
        service, _, _ = _make_service()
        diff = service._compute_diff("line1\nline2", "line1\nline3")

        assert diff["added_lines"] == 1
        assert diff["removed_lines"] == 1
        assert "-line2" in diff["unified_diff"]
        assert "+line3" in diff["unified_diff"]

    def test_identical_text_zero_diff(self):
        service, _, _ = _make_service()
        diff = service._compute_diff("same\nlines", "same\nlines")

        assert diff["added_lines"] == 0
        assert diff["removed_lines"] == 0
        assert diff["unified_diff"] == ""

    def test_coverage_counts_job_keywords(self):
        service, _, _ = _make_service()
        job = SimpleNamespace(
            title="Analyst",
            description="SQL Python dashboards etl",
        )
        coverage = service._coverage("SQL dashboards", job)

        # 2 of 5 job keywords covered (analyst, sql, python, dashboards, etl)
        assert coverage == 40.0

    def test_candidate_name_from_preferences(self):
        service, _, _ = _make_service()
        assert service._candidate_name(PROFILE) == "Дияр Муллахимов"

    def test_candidate_name_fallback(self):
        service, _, _ = _make_service()
        profile = SimpleNamespace(additional_preferences={})
        assert service._candidate_name(profile) == "Candidate"
