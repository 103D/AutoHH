import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, UTC
from app.services.matching import MatchingService
from app.services.scoring import ScoringEngine
from app.repositories.matching import MatchResultRepository
from app.repositories.job import JobRepository
from app.services.candidate import CandidateService
from app.providers.ai.base import MatchResult as AIMatchResult, SkillMatch
from app.models.candidate import CandidateProfile
from app.models.job import Job
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
    matching_service.candidate_service.get_profile = AsyncMock(return_value=sample_profile)
    matching_service.match_repository.create = AsyncMock(return_value=MagicMock(
        job_id=sample_job.id,
        candidate_profile_id=sample_profile.id,
        score=90,
        recommendation="HIGH_PRIORITY",
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
        analyzed_at=datetime.now(UTC)
    ))

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)
    
    assert result.score > 0
    assert result.recommendation == "HIGH_PRIORITY"
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
    matching_service.candidate_service.get_profile = AsyncMock(return_value=sample_profile)

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)
    
    assert result.score == 85
    mock_ai.analyze_job.assert_not_called()

@pytest.mark.asyncio
async def test_match_ai_fallback(matching_service, mock_repo, mock_ai, sample_job, sample_profile):
    mock_ai.analyze_job.side_effect = Exception("AI API Down")
    mock_repo.get_by_job_and_candidate.return_value = None
    
    matching_service.job_repository.get = AsyncMock(return_value=sample_job)
    matching_service.candidate_service.get_profile = AsyncMock(return_value=sample_profile)
    matching_service.match_repository.create = AsyncMock(return_value=MagicMock(
        job_id=sample_job.id,
        candidate_profile_id=sample_profile.id,
        score=50,
        recommendation="REVIEW",
        matched_skills=[],
        missing_skills=[],
        strong_matches=[],
        concerns=[],
        reasoning_summary="",
        analyzed_at=datetime.now(UTC)
    ))

    result = await matching_service.analyze_job(sample_job.id, sample_profile.id)
    
    assert result.score is not None
    assert result.recommendation in ["HIGH_PRIORITY", "APPLY", "REVIEW", "IGNORE"]
