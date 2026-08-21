"""Tests for deterministic scoring engine."""

import pytest

from app.models.candidate import CandidateProfile
from app.models.job import Job
from app.services.scoring import ScoreBreakdown, ScoringEngine


@pytest.fixture
def sample_candidate() -> CandidateProfile:
    """Create a sample candidate profile for testing."""
    return CandidateProfile(
        id="00000000-0000-0000-0000-000000000001",
        user_id="11111111-1111-1111-1111-111111111111",
        desired_positions=["Data Analyst", "Business Analyst"],
        skills=["Python", "SQL", "PostgreSQL", "Pandas", "Data Visualization", "Tableau"],
        technologies=["Python", "PostgreSQL", "Pandas", "Tableau", "Git"],
        experience_years=4,
        education=[{"degree": "Master", "field": "Computer Science"}],
        languages=["English", "Russian"],
        location="Almaty",
        desired_salary_min=400000,
        desired_salary_max=600000,
        salary_currency="KZT",
        employment_types=["full_time"],
        work_formats=["remote", "hybrid"],
        relocation_possible=True,
        business_trips_acceptable=False,
        resume_versions={},
    )


@pytest.fixture
def sample_job() -> Job:
    """Create a sample job for testing."""
    return Job(
        id="22222222-2222-2222-2222-222222222222",
        source_id="33333333-3333-3333-3333-333333333333",
        external_id="hh_12345",
        title="Senior Data Analyst",
        company="TechCorp Kazakhstan",
        description="We are looking for a Senior Data Analyst with Python, SQL, and Tableau experience. 3+ years of experience required. Responsible for building dashboards and analyzing business metrics.",
        location="Almaty",
        salary_min=450000,
        salary_max=650000,
        currency="KZT",
        employment_type="full_time",
        work_format="hybrid",
        url="https://hh.kz/vacancy/12345",
        published_at="2024-01-15T10:00:00Z",
        first_seen_at="2024-01-15T10:00:00Z",
        last_seen_at="2024-01-15T10:00:00Z",
        content_hash="abc123",
        url_normalized="https://hh.kz/vacancy/12345",
        raw_data={},
    )


def test_scoring_engine_initialization():
    """Test that scoring engine initializes with correct weights."""
    engine = ScoringEngine()
    assert "technical" in engine.weights
    assert "experience" in engine.weights
    assert abs(sum(engine.weights.values()) - 1.0) < 0.01


def test_technical_score_excellent_match(sample_candidate, sample_job):
    """Test technical score for excellent skill match."""
    engine = ScoringEngine()
    score = engine.calculate_technical_score(sample_candidate, sample_job)
    # Candidate has Python, SQL, Tableau - all mentioned in job
    assert score >= 80.0


def test_technical_score_partial_match():
    """Test technical score for partial skill match."""
    engine = ScoringEngine()

    candidate = CandidateProfile(
        id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        desired_positions=["Data Analyst"],
        skills=["Java", "C++", "React"],  # None match the job
        technologies=["Java", "Spring"],
        experience_years=3,
    )

    job = Job(
        id="33333333-3333-3333-3333-333333333333",
        source_id="44444444-4444-4444-4444-444444444444",
        external_id="hh_99999",
        title="Python Developer",
        company="TestCo",
        description="Python, Django, PostgreSQL required. Building web applications.",
        location="Almaty",
        salary_min=300000,
        salary_max=500000,
        currency="KZT",
        employment_type="full_time",
        work_format="office",
        url="https://hh.kz/vacancy/99999",
        published_at="2024-01-15T10:00:00Z",
        first_seen_at="2024-01-15T10:00:00Z",
        last_seen_at="2024-01-15T10:00:00Z",
        content_hash="def456",
        url_normalized="https://hh.kz/vacancy/99999",
        raw_data={},
    )

    score = engine.calculate_technical_score(candidate, job)
    assert score <= 50.0  # Low match


def test_experience_score_exact_match(sample_candidate, sample_job):
    """Test experience score for exact match (4 years vs 3+ required)."""
    engine = ScoringEngine()
    score = engine.calculate_experience_score(sample_candidate, sample_job)
    assert score >= 80.0


def test_experience_score_overqualified():
    """Test experience score for overqualified candidate."""
    engine = ScoringEngine()

    candidate = CandidateProfile(
        id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        desired_positions=["Data Analyst"],
        skills=["Python", "SQL"],
        experience_years=10,
    )

    job = Job(
        id="33333333-3333-3333-3333-333333333333",
        source_id="44444444-4444-4444-4444-444444444444",
        external_id="hh_99999",
        title="Junior Data Analyst",
        company="TestCo",
        description="1+ years experience required. Entry level position.",
        location="Almaty",
        salary_min=200000,
        salary_max=300000,
        currency="KZT",
        employment_type="full_time",
        work_format="office",
        url="https://hh.kz/vacancy/99999",
        published_at="2024-01-15T10:00:00Z",
        first_seen_at="2024-01-15T10:00:00Z",
        last_seen_at="2024-01-15T10:00:00Z",
        content_hash="def456",
        url_normalized="https://hh.kz/vacancy/99999",
        raw_data={},
    )

    score = engine.calculate_experience_score(candidate, job)
    assert score >= 90.0  # Overqualified but good


def test_location_score_same_city(sample_candidate, sample_job):
    """Test location score for same city."""
    engine = ScoringEngine()
    score = engine.calculate_location_score(sample_candidate, sample_job)
    assert score >= 90.0


def test_location_score_remote_job():
    """Test location score for remote job."""
    engine = ScoringEngine()

    candidate = CandidateProfile(
        id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        desired_positions=["Data Analyst"],
        skills=["Python"],
        location="Astana",
        work_formats=["remote"],
        relocation_possible=False,
    )

    job = Job(
        id="33333333-3333-3333-3333-333333333333",
        source_id="44444444-4444-4444-4444-444444444444",
        external_id="hh_99999",
        title="Data Analyst",
        company="TestCo",
        description="Remote position.",
        location="Almaty",
        salary_min=300000,
        salary_max=500000,
        currency="KZT",
        employment_type="full_time",
        work_format="remote",
        url="https://hh.kz/vacancy/99999",
        published_at="2024-01-15T10:00:00Z",
        first_seen_at="2024-01-15T10:00:00Z",
        last_seen_at="2024-01-15T10:00:00Z",
        content_hash="def456",
        url_normalized="https://hh.kz/vacancy/99999",
        raw_data={},
    )

    score = engine.calculate_location_score(candidate, job)
    assert score >= 80.0


def test_salary_score_overlap(sample_candidate, sample_job):
    """Test salary score when ranges overlap."""
    engine = ScoringEngine()
    score = engine.calculate_salary_score(sample_candidate, sample_job)
    assert score >= 80.0  # Good overlap


def test_salary_score_job_offers_more():
    """Test salary score when job offers more than candidate wants."""
    engine = ScoringEngine()

    candidate = CandidateProfile(
        id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        desired_positions=["Data Analyst"],
        skills=["Python"],
        desired_salary_min=300000,
        desired_salary_max=400000,
        salary_currency="KZT",
    )

    job = Job(
        id="33333333-3333-3333-3333-333333333333",
        source_id="44444444-4444-4444-4444-444444444444",
        external_id="hh_99999",
        title="Data Analyst",
        company="TestCo",
        description="Great salary.",
        location="Almaty",
        salary_min=500000,
        salary_max=700000,
        currency="KZT",
        employment_type="full_time",
        work_format="office",
        url="https://hh.kz/vacancy/99999",
        published_at="2024-01-15T10:00:00Z",
        first_seen_at="2024-01-15T10:00:00Z",
        last_seen_at="2024-01-15T10:00:00Z",
        content_hash="def456",
        url_normalized="https://hh.kz/vacancy/99999",
        raw_data={},
    )

    score = engine.calculate_salary_score(candidate, job)
    assert score >= 90.0  # Job offers more


def test_work_format_score_match(sample_candidate, sample_job):
    """Test work format score for matching format."""
    engine = ScoringEngine()
    score = engine.calculate_work_format_score(sample_candidate, sample_job)
    # Candidate wants remote/hybrid, job is hybrid
    assert score >= 70.0


def test_full_scoring_calculation(sample_candidate, sample_job):
    """Test full scoring calculation returns reasonable results."""
    engine = ScoringEngine()
    final_score, breakdown = engine.calculate(sample_candidate, sample_job)

    assert 0 <= final_score <= 100
    assert isinstance(breakdown, ScoreBreakdown)
    assert breakdown.technical >= 0
    assert breakdown.experience >= 0
    assert breakdown.location >= 0
    assert breakdown.salary >= 0
    assert breakdown.work_format >= 0
    assert breakdown.education >= 0
    assert breakdown.language >= 0


def test_recommendation_thresholds():
    """Test recommendation level determination."""
    engine = ScoringEngine()

    assert engine.get_recommendation(95) == "HIGH_PRIORITY"
    assert engine.get_recommendation(85) == "APPLY"
    assert engine.get_recommendation(70) == "REVIEW"
    assert engine.get_recommendation(40) == "IGNORE"


def test_score_breakdown_to_dict():
    """Test ScoreBreakdown serialization."""
    breakdown = ScoreBreakdown(
        technical=85.5,
        experience=90.0,
        location=95.0,
        salary=80.0,
        work_format=75.0,
        education=70.0,
        language=85.0,
    )

    d = breakdown.to_dict()
    assert "technical" in d
    assert d["technical"] == 85.5
    assert d["experience"] == 90.0
    assert all(isinstance(v, float) for v in d.values())


def test_candidate_with_no_skills():
    """Test scoring with candidate having no skills."""
    engine = ScoringEngine()

    candidate = CandidateProfile(
        id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        desired_positions=["Data Analyst"],
        skills=[],
        technologies=[],
        experience_years=3,
    )

    job = Job(
        id="33333333-3333-3333-3333-333333333333",
        source_id="44444444-4444-4444-4444-444444444444",
        external_id="hh_99999",
        title="Data Analyst",
        company="TestCo",
        description="Python, SQL required.",
        location="Almaty",
        salary_min=300000,
        salary_max=500000,
        currency="KZT",
        employment_type="full_time",
        work_format="office",
        url="https://hh.kz/vacancy/99999",
        published_at="2024-01-15T10:00:00Z",
        first_seen_at="2024-01-15T10:00:00Z",
        last_seen_at="2024-01-15T10:00:00Z",
        content_hash="def456",
        url_normalized="https://hh.kz/vacancy/99999",
        raw_data={},
    )

    score = engine.calculate_technical_score(candidate, job)
    assert score == 50.0  # Neutral when no skills specified
