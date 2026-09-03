from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.models.matching import MatchCategory
from app.providers.ai.base import MatchResult as AIMatchResult
from app.providers.ai.base import SkillMatch
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.services.candidate import CandidateService
from app.services.matching import MatchingService
from app.services.scoring import ScoringEngine
from tests.unit.mocks.mock_ai_provider import MockAIProvider


@pytest.fixture
def mock_repo():
    return MagicMock(spec=MatchResultRepository)

@pytest.fixture
def mock_job_repo():
    return MagicMock(spec=JobRepository)

@pytest.fixture
def mock_candidate_service():
    return MagicMock(spec=CandidateService)

@pytest.fixture
def mock_ai():
    return MockAIProvider()

@pytest.fixture
def scoring_engine():
    return ScoringEngine()

@pytest.fixture
def matching_service(mock_job_repo, mock_candidate_service, mock_repo, mock_ai):
    return MatchingService(
        job_repository=mock_job_repo,
        candidate_service=mock_candidate_service,
        match_repository=mock_repo,
        ai_provider=mock_ai,
        scoring_engine=ScoringEngine()
    )

@pytest.fixture
def sample_job():
    return Job(
        id=uuid4(),
        title="Python Developer",
        description="Need a Python expert with FastAPI experience",
        company="Tech Corp",
        external_id="ext123",
        source_id=uuid4(),
        content_hash="hash123",
        url="http://job.com",
        url_normalized="http://job.com",
        raw_data={},
        first_seen_at=None,
        last_seen_at=None
    )

@pytest.fixture
def sample_profile():
    return CandidateProfile(
        id=uuid4(),
        user_id=uuid4(),
        skills=["Python", "FastAPI"],
        technologies={"Python": "Expert", "PostgreSQL": "Intermediate"},
        languages={"English": "C1"},
        experience_years=5,
        salary_currency="USD",
        desired_salary_min=5000,
        relocation_possible=True,
        work_formats=["Remote", "Hybrid"],
        resume_versions={},
    )

@pytest.mark.asyncio
async def test_match_hybrid_success(matching_service, mock_repo, mock_ai, sample_job, sample_profile):
    ai_result = AIMatchResult(
        score=90,
        recommendation="HIGH_PRIORITY",
        matched_skills=[SkillMatch(skill="Python", match_type="exact", confidence=1.0)],
        missing_skills=[],
        strong_matches=["Python expert"],
        concerns=[],
        reasoning_summary="Strong match based on tech stack"
    )
    mock_ai.analyze_job.return_value = ai_result
    mock_repo.get_by_job_and_candidate.return_value = None

    matching_service.job_repository.get = AsyncMock(return_value=sample_job)
    matching_service.candidate_service.resolve_profile = AsyncMock(return_value=sample_profile)
    matching_service.match_repository.create = AsyncMock(return_value=MagicMock(
        job_id=sample_job.id,
        candidate_profile_id=sample_profile.id,
        score=90,
        recommendation="DREAM_JOB",
        user_override_recommendation=None,
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
        hard_failures=[],
        score_breakdown={},
        analyzed_at=datetime.now(UTC)
    ))

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)

    assert result.score > 0
    assert result.recommendation in MatchCategory.ALL
    matching_service.match_repository.create.assert_called_once()

@pytest.mark.asyncio
async def test_match_cache_hit(matching_service, mock_repo, mock_ai, sample_job, sample_profile):
    from app.models.matching import MatchResult as DBMatchResult
    existing_match = DBMatchResult(
        id=uuid4(),
        job_id=sample_job.id,
        candidate_profile_id=sample_profile.id,
        score=85,
        recommendation="APPLY",
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="Cached result",
        analyzed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    mock_repo.get_by_job_and_candidate.return_value = existing_match

    matching_service.job_repository.get = AsyncMock(return_value=sample_job)
    matching_service.candidate_service.resolve_profile = AsyncMock(return_value=sample_profile)

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)

    assert result.score == 85
    mock_ai.analyze_job.assert_not_called()

@pytest.mark.asyncio
async def test_match_ai_fallback(matching_service, mock_repo, mock_ai, sample_job, sample_profile):
    mock_ai.analyze_job.side_effect = Exception("AI API Down")
    mock_repo.get_by_job_and_candidate.return_value = None

    matching_service.job_repository.get = AsyncMock(return_value=sample_job)
    matching_service.candidate_service.resolve_profile = AsyncMock(return_value=sample_profile)
    matching_service.match_repository.create = AsyncMock(return_value=MagicMock(
        job_id=sample_job.id,
        candidate_profile_id=sample_profile.id,
        score=50,
        recommendation="MARKET_RESEARCH",
        user_override_recommendation=None,
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
        hard_failures=[],
        score_breakdown={},
        analyzed_at=datetime.now(UTC)
    ))

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)

    assert result.score is not None
    assert result.recommendation in MatchCategory.ALL


@pytest.mark.asyncio
async def test_match_hard_failure_not_eligible(matching_service, mock_repo, mock_ai, sample_profile):
    """Critical hard-requirement failure => NOT_ELIGIBLE, LLM never called
    (task specs #8 and #29)."""
    ineligible_job = Job(
        id=uuid4(),
        title="Principal Data Engineer",
        description="Requires 10+ years of experience leading data platforms",
        company="Tech Corp",
        external_id="ext999",
        source_id=uuid4(),
        content_hash="hash999",
        url="http://job.com/999",
        url_normalized="http://job.com/999",
        raw_data={},
        experience_required=10,
    )
    mock_repo.get_by_job_and_candidate.return_value = None
    matching_service.job_repository.get = AsyncMock(return_value=ineligible_job)
    matching_service.candidate_service.resolve_profile = AsyncMock(return_value=sample_profile)
    matching_service.match_repository.create = AsyncMock(return_value=MagicMock(
        job_id=ineligible_job.id,
        candidate_profile_id=sample_profile.id,
        score=20,
        recommendation=MatchCategory.NOT_ELIGIBLE,
        user_override_recommendation=None,
        hard_failures=["experience: vacancy requires 10+ years, candidate has 5"],
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
        score_breakdown={},
        analyzed_at=datetime.now(UTC)
    ))

    result = await matching_service.analyze_job(ineligible_job.id, sample_profile.id)

    assert result.recommendation == MatchCategory.NOT_ELIGIBLE
    mock_ai.analyze_job.assert_not_called()
    persisted = matching_service.match_repository.create.call_args[0][0]
    assert persisted["hard_failures"]
    assert persisted["recommendation"] == MatchCategory.NOT_ELIGIBLE


@pytest.mark.asyncio
async def test_match_llm_gate_skips_ai_for_low_scores(
    matching_service, mock_repo, mock_ai, sample_job, sample_profile, monkeypatch
):
    """LLM gate (task spec #29): deterministic score below threshold => no AI call."""
    monkeypatch.setattr(settings, "llm_gate_enabled", True)
    monkeypatch.setattr(settings, "llm_gate_min_deterministic_score", 100)
    mock_repo.get_by_job_and_candidate.return_value = None
    matching_service.job_repository.get = AsyncMock(return_value=sample_job)
    matching_service.candidate_service.resolve_profile = AsyncMock(return_value=sample_profile)
    matching_service.match_repository.create = AsyncMock(return_value=MagicMock(
        job_id=sample_job.id,
        candidate_profile_id=sample_profile.id,
        score=30,
        recommendation=MatchCategory.MARKET_RESEARCH,
        user_override_recommendation=None,
        hard_failures=[],
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
        score_breakdown={},
        analyzed_at=datetime.now(UTC)
    ))

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)

    mock_ai.analyze_job.assert_not_called()
    assert result.recommendation in MatchCategory.ALL


@pytest.mark.asyncio
async def test_soft_match_returns_score_and_breakdown(matching_service, sample_job, sample_profile):
    """soft_match returns a SoftMatchResponse with score, breakdown, skills (no persistence)."""
    from app.schemas.matching import SoftMatchResponse

    result = await matching_service.soft_match(sample_job, sample_profile)

    assert isinstance(result, SoftMatchResponse)
    assert 0 <= result.score <= 100
    assert result.recommendation
    assert isinstance(result.score_breakdown, dict)
    assert "technical" in result.score_breakdown
    # Python/FastAPI are in both candidate skills and job description
    assert "python" in result.matched_skills
    assert "fastapi" in result.matched_skills
    # No persistence
    matching_service.match_repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_soft_match_hard_filter_not_eligible(matching_service, sample_profile):
    """soft_match returns NOT_ELIGIBLE when hard filters fail (no persistence)."""
    from app.schemas.matching import SoftMatchResponse

    ineligible_job = Job(
        id=uuid4(),
        title="Principal Data Engineer",
        description="Requires 10+ years of experience leading data platforms",
        company="BigTech",
        external_id="ext999",
        source_id=uuid4(),
        content_hash="hash999",
        url="http://job.com/999",
        url_normalized="http://job.com/999",
        raw_data={},
        experience_required=10,
    )

    result = await matching_service.soft_match(ineligible_job, sample_profile)

    assert isinstance(result, SoftMatchResponse)
    assert result.score == 0
    assert result.recommendation == "NOT_ELIGIBLE"
    matching_service.match_repository.create.assert_not_called()


@pytest.mark.asyncio
async def test_soft_match_does_not_call_llm(matching_service, sample_job, sample_profile, monkeypatch):
    """soft_match is deterministic — LLM must never be invoked."""
    monkeypatch.setattr(settings, "llm_gate_enabled", True)
    monkeypatch.setattr(settings, "llm_gate_min_deterministic_score", 0)

    result = await matching_service.soft_match(sample_job, sample_profile)

    matching_service.ai_provider.analyze_job.assert_not_called()
    assert result.score >= 0
