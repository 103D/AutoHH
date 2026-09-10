"""Integration tests for append-only MatchResult revision semantics."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.candidate import CandidateProfile
from app.models.job import Job, JobSource
from app.models.matching import MatchResult
from app.repositories.matching import MatchResultRepository


def _payload(job_id, candidate_id, *, fingerprint: str, score: int = 50):
    return {
        "job_id": job_id,
        "candidate_profile_id": candidate_id,
        "score": score,
        "recommendation": "SOLID_MATCH",
        "matched_skills": [],
        "missing_skills": [],
        "strong_matches": [],
        "concerns": [],
        "reasoning_summary": f"rev {fingerprint[:8]}",
        "score_breakdown": {},
        "hard_failures": [],
        "analyzed_at": datetime.now(UTC).isoformat(),
        "analysis_fingerprint": fingerprint,
        "candidate_fingerprint": "c" * 64,
        "job_fingerprint": "j" * 64,
        "scoring_fingerprint": "s" * 64,
        "taxonomy_fingerprint": "t" * 64,
        "taxonomy_version": "taxonomy-v1",
        "engine_version": "match-v3",
        "prompt_version": "v7",
    }


@pytest.fixture
async def repo_factory(migrate_test_database):
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with factory() as session:
        await session.execute(text("TRUNCATE match_results CASCADE"))
        await session.execute(text("TRUNCATE jobs CASCADE"))
        await session.execute(text("TRUNCATE candidate_profiles CASCADE"))
        await session.execute(text("TRUNCATE job_sources CASCADE"))
        await session.commit()
    await engine.dispose()


async def _seed_pair(session: AsyncSession) -> tuple[object, object]:
    """Persist a real job (with source) and candidate so FKs resolve."""
    source = JobSource(
        name=f"src-{uuid4().hex[:8]}",
        type="manual",
        enabled=True,
        configuration={},
    )
    session.add(source)
    await session.flush()

    job = Job(
        source_id=source.id,
        external_id=f"ext-{uuid4().hex[:8]}",
        title="Data Analyst",
        company="Corp",
        description="SQL and dashboards",
        url="https://example.com/vacancy/1",
        content_hash=uuid4().hex,
        url_normalized="https://example.com/vacancy/1",
        raw_data={},
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    candidate = CandidateProfile(
        user_id=uuid4(),
        desired_positions=["Data Analyst"],
        skills=["SQL"],
        technologies={},
        languages={},
        salary_currency="KZT",
        resume_versions={},
    )
    session.add(candidate)
    await session.flush()
    return job, candidate


@pytest.mark.asyncio
async def test_first_revision_is_current(repo_factory):
    async with repo_factory() as session:
        repo = MatchResultRepository(session)
        job, candidate = await _seed_pair(session)
        obj = await repo.create_revision(
            _payload(job.id, candidate.id, fingerprint="fp-1")
        )
        await session.commit()
        assert obj.revision == 1
        assert obj.is_current is True

        loaded = await repo.get_by_job_and_candidate(
            obj.job_id, obj.candidate_profile_id
        )
        assert loaded is not None
        assert loaded.id == obj.id
        assert loaded.is_current is True


@pytest.mark.asyncio
async def test_new_revision_supersedes_old(repo_factory):
    async with repo_factory() as session:
        repo = MatchResultRepository(session)
        job, candidate = await _seed_pair(session)
        job_id, candidate_id = job.id, candidate.id
        first = await repo.create_revision(
            _payload(job_id, candidate_id, fingerprint="fp-1")
        )
        await session.commit()

        second = await repo.create_revision(
            _payload(job_id, candidate_id, fingerprint="fp-2", score=80)
        )
        await session.commit()

        assert second.revision == 2
        assert second.is_current is True

        loaded = await repo.get_by_job_and_candidate(job_id, candidate_id)
        assert loaded is not None
        assert loaded.id == second.id

        await session.refresh(first)
        assert first.is_current is False

        history = await repo.get_revision_history(job_id, candidate_id)
        assert [row.revision for row in history] == [1, 2]
        assert history[0].score == 50
        assert history[1].score == 80


@pytest.mark.asyncio
async def test_current_fingerprint_is_reused_not_replicated(repo_factory):
    async with repo_factory() as session:
        repo = MatchResultRepository(session)
        job, candidate = await _seed_pair(session)
        job_id, candidate_id = job.id, candidate.id
        first = await repo.create_revision(
            _payload(job_id, candidate_id, fingerprint="same")
        )
        await session.commit()

        duplicate = await repo.create_revision(
            _payload(job_id, candidate_id, fingerprint="same")
        )
        await session.commit()

        assert duplicate.id == first.id
        assert duplicate.revision == 1
        assert (await repo.get_revision_history(job_id, candidate_id))[-1].revision == 1


@pytest.mark.asyncio
async def test_concurrent_revisions_keep_single_current(repo_factory):
    async with repo_factory() as session:
        job, candidate = await _seed_pair(session)
        await session.commit()
    job_id, candidate_id = job.id, candidate.id

    async def _insert(fingerprint: str) -> MatchResult:
        async with repo_factory() as session:
            repo = MatchResultRepository(session)
            obj = await repo.create_revision(
                _payload(job_id, candidate_id, fingerprint=fingerprint)
            )
            await session.commit()
            return obj

    first, second = await asyncio.gather(
        _insert("a" * 64),
        _insert("b" * 64),
    )

    async with repo_factory() as session:
        repo = MatchResultRepository(session)
        current = await repo.get_by_job_and_candidate(job_id, candidate_id)
        history = await repo.get_revision_history(job_id, candidate_id)
        assert current is not None
        assert [row.revision for row in history] in ([1, 2], [2, 1])
        assert len(history) == 2
        assert first.id != second.id


@pytest.mark.asyncio
async def test_candidate_and_job_lists_return_only_current(repo_factory):
    async with repo_factory() as session:
        repo = MatchResultRepository(session)
        job, candidate = await _seed_pair(session)
        job_id, candidate_id = job.id, candidate.id
        await repo.create_revision(_payload(job_id, candidate_id, fingerprint="fp-1"))
        await session.commit()
        await repo.create_revision(_payload(job_id, candidate_id, fingerprint="fp-2"))
        await session.commit()

        for_candidate = await repo.get_for_candidate(candidate_id)
        assert len(for_candidate) == 1
        assert for_candidate[0].revision == 2

        for_job = await repo.get_for_job(job_id)
        assert len(for_job) == 1
        assert for_job[0].revision == 2
