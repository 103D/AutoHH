"""Tests for HermesOrchestrator decision flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

from app.hermes.orchestrator import (
    HermesOrchestrator,
    OrchestratorError,
    NoProfileError,
)


class _FakeProfile:
    def __init__(self):
        self.id = uuid4()
        self.experience_years = 3
        self.experience_level = "middle"
        self.desired_salary_min = 100000
        self.desired_salary_max = 200000
        self.location = "Москва"
        self.skills = ["sql", "python"]
        self.technologies = {}
        self.employment_types = ["full_time"]
        self.work_formats = ["remote"]
        self.user_id = uuid4()


class _FakeJob:
    def __init__(self):
        self.id = uuid4()
        self.title = "Data Analyst"
        self.company = "TestCo"
        self.description = "Job description"
        self.location = "Москва"
        self.salary_min = 100000
        self.salary_max = 200000
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


class _FakeMatch:
    def __init__(self, score=75, **kwargs):
        self.score = score
        self.job_id = kwargs.get("job_id", uuid4())
        self.candidate_profile_id = kwargs.get("candidate_profile_id", uuid4())
        self.recommendation = kwargs.get("recommendation", "SOLID_MATCH")
        self.user_override_recommendation = None
        self.matched_skills = ["sql"]
        self.missing_skills = ["tableau"]
        self.strong_matches = []
        self.concerns = []
        self.reasoning_summary = "Test"
        self.score_breakdown = {}
        self.hard_failures = []
        self.analysis_fingerprint = "fp123"
        self.analyzed_at = None


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.candidate_service = MagicMock()
    ctx.candidate_service.resolve_profile = AsyncMock(return_value=_FakeProfile())
    ctx.job_repository = MagicMock()
    ctx.job_repository.get = AsyncMock(return_value=_FakeJob())
    ctx.match_repository = MagicMock()
    ctx.match_repository.get_by_job_and_candidate = AsyncMock(return_value=_FakeMatch())
    ctx.matching_service = MagicMock()
    ctx.matching_service.analyze_job = AsyncMock(return_value=_FakeMatch())
    ctx.action_gate = MagicMock()
    ctx.action_gate.can_read = MagicMock(return_value=True)
    ctx.action_gate.can_mutate = MagicMock(return_value=True)
    return ctx


@pytest.fixture
def orchestrator(mock_ctx):
    return HermesOrchestrator(mock_ctx)


class TestHermesOrchestrator:
    async def test_get_job_for_analysis_returns_job(self, orchestrator, mock_ctx):
        job_id = uuid4()
        mock_ctx.job_repository.get.return_value = _FakeJob()

        result = await orchestrator._get_job_for_analysis(job_id)

        assert result is not None
        mock_ctx.job_repository.get.assert_called_once_with(job_id)

    async def test_get_job_for_analysis_returns_none_if_missing(self, orchestrator, mock_ctx):
        job_id = uuid4()
        mock_ctx.job_repository.get.return_value = None

        result = await orchestrator._get_job_for_analysis(job_id)

        assert result is None

    async def test_resolve_profile_returns_profile(self, orchestrator, mock_ctx):
        profile = _FakeProfile()
        mock_ctx.candidate_service.resolve_profile.return_value = profile

        result = await orchestrator._resolve_profile(None)

        assert result == profile

    async def test_resolve_profile_raises_if_no_profile(self, orchestrator, mock_ctx):
        mock_ctx.candidate_service.resolve_profile.return_value = None

        with pytest.raises(NoProfileError):
            await orchestrator._resolve_profile(None)

    async def test_get_or_create_match_existing(self, orchestrator, mock_ctx):
        job_id = uuid4()
        profile_id = uuid4()
        existing_match = _FakeMatch()
        mock_ctx.match_repository.get_by_job_and_candidate.return_value = existing_match

        result = await orchestrator._get_or_create_match(job_id, profile_id)

        assert result == existing_match

    async def test_get_or_create_match_creates_if_missing(self, orchestrator, mock_ctx):
        job_id = uuid4()
        profile_id = uuid4()
        mock_ctx.match_repository.get_by_job_and_candidate.return_value = None
        mock_ctx.matching_service.analyze_job.return_value = _FakeMatch()

        result = await orchestrator._get_or_create_match(job_id, profile_id)

        mock_ctx.matching_service.analyze_job.assert_called_once()


class TestOrchestratorErrors:
    def test_orchestrator_error_can_be_raised(self):
        with pytest.raises(OrchestratorError):
            raise OrchestratorError("test error")

    def test_no_profile_error_is_orchestrator_error(self):
        with pytest.raises(OrchestratorError):
            raise NoProfileError("no profile")

    def test_no_profile_error_message(self):
        try:
            raise NoProfileError("specific")
        except NoProfileError as e:
            assert str(e) == "specific"
