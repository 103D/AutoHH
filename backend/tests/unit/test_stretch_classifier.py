"""Unit tests for the stretch-vacancy classifier."""

import pytest

from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.services.stretch_classifier import StretchClassifier


@pytest.fixture
def candidate() -> CandidateProfile:
    """Data Analyst with 2 years of experience (middle level)."""
    return CandidateProfile(
        id="00000000-0000-0000-0000-000000000001",
        user_id="11111111-1111-1111-1111-111111111111",
        desired_positions=["Data Analyst"],
        skills=["SQL", "PostgreSQL", "Python", "Power BI", "pandas"],
        technologies={"databases": ["PostgreSQL"], "analytics": ["Power BI"]},
        experience_years=2,
        experience_level="middle",
        languages={},
        location="Almaty",
        desired_salary_min=400000,
        desired_salary_max=600000,
        salary_currency="KZT",
        resume_versions={},
    )


def _make_job(**overrides) -> Job:
    """Default job: Senior Data Analyst, 3 years required, Tableau + dashboards."""
    data = {
        "id": "22222222-2222-2222-2222-222222222222",
        "source_id": "33333333-3333-3333-3333-333333333333",
        "external_id": "hh_12345",
        "title": "Senior Data Analyst",
        "company": "Kaspi.kz",
        "description": (
            "We are looking for a Data Analyst with 3 years of experience. "
            "Required: SQL, Python, Tableau. Building dashboards and metrics."
        ),
        "location": "Almaty",
        "salary_min": 500000,
        "salary_max": 700000,
        "currency": "KZT",
        "employment_type": "full_time",
        "work_format": "hybrid",
        "url": "https://hh.kz/vacancy/12345",
        "published_at": "2026-08-20T10:00:00Z",
        "first_seen_at": "2026-08-20T10:00:00Z",
        "last_seen_at": "2026-08-20T10:00:00Z",
        "content_hash": "abc123",
        "url_normalized": "https://hh.kz/vacancy/12345",
        "raw_data": {},
    }
    data.update(overrides)
    return Job(**data)


@pytest.fixture
def classifier() -> StretchClassifier:
    return StretchClassifier()

class TestExtractRequiredExperience:
    """Tests for required-experience extraction."""

    def test_english_years(self, classifier):
        job = _make_job(description="You need 3+ years of experience with SQL.")
        assert classifier.extract_required_experience(job) == 3

    def test_russian_ot_let(self, classifier):
        job = _make_job(description="Требуется опыт от 4 лет анализа данных.")
        assert classifier.extract_required_experience(job) == 4

    def test_russian_goda_opyta(self, classifier):
        job = _make_job(description="3 года опыта в аналитике.")
        assert classifier.extract_required_experience(job) == 3

    def test_no_experience_mentioned(self, classifier):
        job = _make_job(description="Ищем аналитика данных в команду.")
        assert classifier.extract_required_experience(job) is None

class TestFindMissingKeySkills:
    """Tests for missing-skill detection."""

    def test_detects_missing_skill(self, classifier, candidate):
        job = _make_job(description="SQL, Python and Tableau are required.")
        missing = classifier.find_missing_key_skills(candidate, job)

        assert "Tableau" in missing
        assert not any("SQL" in m or "Python" in m for m in missing)

    def test_no_missing_when_all_known(self, classifier, candidate):
        job = _make_job(description="SQL and Python required.")
        assert classifier.find_missing_key_skills(candidate, job) == []

class TestAnalyze:
    """Tests for the full stretch classification."""

    def test_stretch_job_detected(self, classifier, candidate):
        # Senior title (+1 grade), 3 years required (within 1.5x of 2), missing skills
        job = _make_job()
        analysis = classifier.analyze(candidate, job, 75)

        assert analysis.is_stretch is True
        assert analysis.blockers == []
        assert analysis.required_experience_years == 3
        assert analysis.reasons

    def test_solid_job_not_stretch(self, classifier, candidate):
        job = _make_job(
            title="Data Analyst",
            description="SQL and Python required for daily analytics work.",
            salary_max=550000,
        )
        analysis = classifier.analyze(candidate, job, 60)

        assert analysis.is_stretch is False
        assert analysis.reasons == []

    def test_experience_gap_too_large_blocks(self, classifier, candidate):
        job = _make_job(
            title="Lead Data Analyst",
            description="10+ years of experience required for this role.",
        )
        analysis = classifier.analyze(candidate, job, 75)

        assert analysis.is_stretch is False
        assert any("Experience gap too large" in b for b in analysis.blockers)
        assert any("more than one grade" in b for b in analysis.blockers)

    def test_top_tier_company_blocks(self, classifier, candidate):
        job = _make_job(company="Google")
        analysis = classifier.analyze(candidate, job, 75)

        assert analysis.is_stretch is False
        assert any("Top-tier company" in b for b in analysis.blockers)

    def test_salary_above_stretch_allowance_blocks(self, classifier, candidate):
        # desired_max=600000, +40% => 840000; offered 900000 exceeds it
        job = _make_job(salary_max=900000)
        analysis = classifier.analyze(candidate, job, 75)

        assert analysis.is_stretch is False
        assert any("exceeds desired max" in b for b in analysis.blockers)

    def test_salary_within_allowance_is_reason(self, classifier, candidate):
        # 700000 <= 840000 -> reason, not a blocker
        job = _make_job(salary_max=700000)
        analysis = classifier.analyze(candidate, job, 75)

        assert any("stretch allowance" in r for r in analysis.reasons)
        assert analysis.is_stretch is True

    def test_too_many_missing_skills_blocks(self, classifier, candidate):
        job = _make_job(
            description="Requires Tableau, Airflow, dbt, Spark, Kafka, Docker and Git."
        )
        analysis = classifier.analyze(candidate, job, 75)

        assert analysis.is_stretch is False
        assert any("Too many missing key skills" in b for b in analysis.blockers)

    def test_to_dict(self, classifier, candidate):
        analysis = classifier.analyze(candidate, _make_job(), 75)
        data = analysis.to_dict()

        assert data["is_stretch"] is True
        assert isinstance(data["reasons"], list)
        assert data["required_experience_years"] == 3
