"""Tests for HermesGapAnalysisService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.hermes.gap_analysis_service import (
    HermesGapAnalysisService,
    GapAnalysisError,
)


class _FakeProfile:
    def __init__(self):
        self.id = uuid4()
        self.experience_years = 3
        self.experience_level = "middle"
        self.desired_salary_min = 100000
        self.desired_salary_max = 200000
        self.location = "Москва"
        self.skills = ["sql", "python", "excel"]
        self.technologies = {"languages": ["python"], "databases": ["postgresql"]}
        self.employment_types = ["full_time"]
        self.work_formats = ["remote"]
        self.specializations = ["DATA_ANALYST"]
        self.user_id = uuid4()


class _FakeJob:
    def __init__(self):
        self.id = uuid4()
        self.title = "Senior Data Analyst"
        self.company = "TestCo"
        self.description = "Looking for a data analyst with SQL and Python..."
        self.location = "Москва"
        self.salary_min = 150000
        self.salary_max = 250000
        self.currency = "RUB"
        self.employment_type = "full_time"
        self.work_format = "remote"
        self.experience_required = 3
        self.specializations = ["DATA_ANALYST"]
        self.url = "https://hh.ru/vacancy/123"
        self.published_at = None
        self.source_type = "hh_kz"
        self.external_id = "ext-123"
        self.content_hash = "abc123"
        self.url_normalized = "https://hh.ru/vacancy/123"
        self.first_seen_at = None
        self.last_seen_at = None
        self.raw_data = {}
        self.score_breakdown = {}
        self.matched_skills = ["sql", "python"]
        self.missing_skills = ["tableau", "airflow"]
        self.strong_matches = ["sql"]
        self.concerns = []
        self.reasoning_summary = "Good match"
        self.hard_failures = []
        self.analysis_fingerprint = "fp123"


class _FakeMatch:
    def __init__(self, score=75, **kwargs):
        self.score = score
        self.job_id = kwargs.get("job_id", uuid4())
        self.candidate_profile_id = kwargs.get("candidate_profile_id", uuid4())
        self.recommendation = kwargs.get("recommendation", "SOLID_MATCH")
        self.user_override_recommendation = None
        self.matched_skills = kwargs.get("matched_skills", ["sql", "python"])
        self.missing_skills = kwargs.get("missing_skills", ["tableau"])
        self.strong_matches = ["sql"]
        self.concerns = []
        self.reasoning_summary = "Test reasoning"
        self.score_breakdown = {"technical": 70, "experience": 80}
        self.hard_failures = []
        self.analysis_fingerprint = "fp123"
        self.analyzed_at = None
        self.ai_provider = None
        self.ai_model = None
        self.ai_tokens_used = None
        self.ai_cost_usd = None


@pytest.fixture
def gap_service():
    mock_ctx = MagicMock()
    return HermesGapAnalysisService(mock_ctx)


class TestHermesGapAnalysisService:
    async def test_analyze_gap_returns_structured_result(self, gap_service):
        job = _FakeJob()
        match = _FakeMatch()
        profile = _FakeProfile()

        result = await gap_service.analyze_gap(job, match, profile)

        assert "overall_score" in result
        assert "match_level" in result
        assert "skill_gaps" in result
        assert "experience_gap" in result
        assert "salary_gap" in result
        assert "recommendations" in result
        assert result["overall_score"] == match.score

    async def test_analyze_gap_skill_gaps_populated(self, gap_service):
        job = _FakeJob()
        match = _FakeMatch(missing_skills=["tableau", "airflow"])
        profile = _FakeProfile()

        result = await gap_service.analyze_gap(job, match, profile)

        assert "tableau" in result["skill_gaps"] or any("tableau" in g for g in result["skill_gaps"])

    async def test_analyze_gap_match_level_solid(self, gap_service):
        job = _FakeJob()
        match = _FakeMatch(score=75, recommendation="SOLID_MATCH")
        profile = _FakeProfile()

        result = await gap_service.analyze_gap(job, match, profile)

        assert result["match_level"] == "SOLID_MATCH"

    async def test_analyze_gap_with_stretch(self, gap_service):
        job = _FakeJob()
        match = _FakeMatch(score=60, recommendation="STRETCH")
        profile = _FakeProfile()

        result = await gap_service.analyze_gap(job, match, profile)

        assert result["match_level"] == "STRETCH"

    async def test_analyze_gap_experience_gap(self, gap_service):
        job = _FakeJob()
        job.experience_required = 5
        match = _FakeMatch()
        profile = _FakeProfile()
        profile.experience_years = 3

        result = await gap_service.analyze_gap(job, match, profile)

        assert result["experience_gap"] is not None
        assert result["experience_gap"] > 0

    async def test_analyze_gap_no_experience_gap(self, gap_service):
        job = _FakeJob()
        job.experience_required = 2
        match = _FakeMatch()
        profile = _FakeProfile()
        profile.experience_years = 4

        result = await gap_service.analyze_gap(job, match, profile)

        # gap should be 0 (no gap when candidate exceeds requirements)
        assert result["experience_gap"] == 0

    async def test_analyze_gap_salary_within_range(self, gap_service):
        job = _FakeJob()
        job.salary_min = 100000
        job.salary_max = 200000
        match = _FakeMatch()
        profile = _FakeProfile()
        profile.desired_salary_min = 120000
        profile.desired_salary_max = 180000

        result = await gap_service.analyze_gap(job, match, profile)

        assert result["salary_gap"] == 0

    async def test_analyze_gap_salary_gap_positive(self, gap_service):
        job = _FakeJob()
        job.salary_min = 100000
        job.salary_max = 150000
        match = _FakeMatch()
        profile = _FakeProfile()
        profile.desired_salary_min = 180000
        profile.desired_salary_max = 220000

        result = await gap_service.analyze_gap(job, match, profile)

        assert result["salary_gap"] > 0

    async def test_analyze_gap_recommendations_generated(self, gap_service):
        job = _FakeJob()
        match = _FakeMatch(missing_skills=["tableau", "airflow"])
        profile = _FakeProfile()

        result = await gap_service.analyze_gap(job, match, profile)

        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) > 0


class TestGapAnalysisError:
    def test_error_can_be_raised(self):
        with pytest.raises(GapAnalysisError):
            raise GapAnalysisError("test error")

    def test_error_message(self):
        try:
            raise GapAnalysisError("specific message")
        except GapAnalysisError as e:
            assert str(e) == "specific message"
