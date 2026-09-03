"""Unit tests for the career analytics service."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.matching import MatchCategory
from app.services.career_analytics import CareerAnalyticsService

PROFILE = SimpleNamespace(id=uuid4())


def _match(score, category, override=None, missing=None):
    return SimpleNamespace(
        id=uuid4(),
        job_id=None,  # set by helper below
        score=score,
        recommendation=category,
        user_override_recommendation=override,
        missing_skills=missing or [],
        strong_matches=[],
    )


def _job(title="Data Analyst", company="Kaspi.kz", salary_min=None, salary_max=None, description="SQL Python"):
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        company=company,
        salary_min=salary_min,
        salary_max=salary_max,
        currency="KZT",
        description=description,
        url="https://hh.kz/vacancy/x",
    )


def _make_service(pairs):
    """Build the analytics service over canned (match, job) pairs."""
    job_by_id = {job.id: job for _match, job in pairs}

    async def get_job(job_id):
        return job_by_id.get(job_id)

    async def get_matches(profile_id):
        return [match for match, _job in pairs]

    async def get_profile(profile_id):
        return PROFILE

    service = CareerAnalyticsService(
        SimpleNamespace(get_for_candidate=get_matches),
        SimpleNamespace(get=get_job),
        SimpleNamespace(
            get_profile=get_profile,
            repository=SimpleNamespace(get_multi=lambda *a: _async([PROFILE])),
        ),
    )
    return service


async def _async(value):
    return value


def _link(match, job):
    match.job_id = job.id


@pytest.mark.asyncio
async def test_market_overview_aggregates():
    m1, j1 = _match(92, MatchCategory.DREAM_JOB), _job(salary_min=500000, salary_max=700000)
    m2, j2 = _match(75, MatchCategory.STRETCH), _job(company="Halyk", salary_min=400000)
    m3, j3 = _match(30, MatchCategory.LEARNING_OPPORTUNITY), _job(company="Ignored Corp")
    _link(m1, j1)
    _link(m2, j2)
    _link(m3, j3)
    service = _make_service([(m1, j1), (m2, j2), (m3, j3)])

    result = await service.market_overview()

    assert result["total_analyzed"] == 3
    assert result["by_category"] == {
        MatchCategory.DREAM_JOB: 1,
        MatchCategory.STRETCH: 1,
        MatchCategory.LEARNING_OPPORTUNITY: 1,
    }
    # Only target categories count for companies
    assert {c["company"] for c in result["top_companies"]} == {"Kaspi.kz", "Halyk"}
    # Salary averaged only over present values
    assert result["salary"]["avg_min"] == 450000
    assert result["salary"]["avg_max"] == 700000


@pytest.mark.asyncio
async def test_market_overview_empty():
    service = _make_service([])

    result = await service.market_overview()

    assert result["total_analyzed"] == 0
    assert result["salary"]["avg_min"] is None
    assert result["demanded_skills"] == []


@pytest.mark.asyncio
async def test_skill_gap_counts_missing():
    j = _job()
    m1 = _match(75, MatchCategory.STRETCH, missing=["Tableau", "Airflow"])
    m2 = _match(72, MatchCategory.STRETCH, missing=["Tableau"])
    m3 = _match(60, MatchCategory.SOLID_MATCH, missing=["Tableau", "dbt"])
    m4 = _match(90, MatchCategory.DREAM_JOB, missing=["Kafka"])
    for m in (m1, m2, m3, m4):
        _link(m, j)
    service = _make_service([(m1, j), (m2, j), (m3, j), (m4, j)])

    result = await service.skill_gap()

    assert result["analyzed_vacancies"] == 4
    gaps = {g["skill"]: g for g in result["gaps"]}
    assert gaps["Tableau"]["in_jobs"] == 3
    assert gaps["Tableau"]["priority"] == "high"
    assert gaps["Airflow"]["priority"] == "low"
    # DREAM_JOB counts as a target category too
    assert gaps["Kafka"]["in_jobs"] == 1


@pytest.mark.asyncio
async def test_skill_gap_ignores_non_target_categories():
    j = _job()
    m1 = _match(45, MatchCategory.MARKET_RESEARCH, missing=["Tableau"])
    _link(m1, j)
    service = _make_service([(m1, j)])

    result = await service.skill_gap()

    assert result["analyzed_vacancies"] == 0
    assert result["gaps"] == []


@pytest.mark.asyncio
async def test_learning_roadmap_ordered():
    j = _job()
    m1 = _match(75, MatchCategory.STRETCH, missing=["Tableau", "Airflow"])
    m2 = _match(72, MatchCategory.STRETCH, missing=["Tableau"])
    _link(m1, j)
    _link(m2, j)
    service = _make_service([(m1, j), (m2, j)])

    result = await service.learning_roadmap()

    assert result["total"] == 2
    assert result["steps"][0]["skill"] == "Tableau"
    assert result["steps"][0]["position"] == 1
    assert "2 из 2" in result["steps"][0]["rationale"]
    assert result["steps"][1]["skill"] == "Airflow"


@pytest.mark.asyncio
async def test_dream_jobs_filtering_and_order():
    j1 = _job(title="Dream A", salary_min=700000, salary_max=900000)
    j2 = _job(title="Dream B")
    j3 = _job(title="Solid")
    m1 = _match(88, MatchCategory.DREAM_JOB)
    m2 = _match(60, MatchCategory.SOLID_MATCH, override=MatchCategory.DREAM_JOB)
    m3 = _match(95, MatchCategory.SOLID_MATCH)
    _link(m1, j1)
    _link(m2, j2)
    _link(m3, j3)
    service = _make_service([(m1, j1), (m2, j2), (m3, j3)])

    result = await service.dream_jobs()

    assert result["total"] == 2
    # Higher score first
    assert [item["title"] for item in result["jobs"]] == ["Dream A", "Dream B"]
    assert result["jobs"][0]["is_override"] is False
    assert result["jobs"][1]["is_override"] is True
    assert result["jobs"][0]["salary"]["max"] == 900000
