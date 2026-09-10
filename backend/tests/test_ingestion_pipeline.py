"""End-to-end ingestion pipeline tests against the real test database.

Scenarios (task spec «ПОЛНАЯ ПРОВЕРКА INGESTION»):
1. successful fetch   6. malformed single vacancy (batch survives)
2. HTTP 500           7. duplicate vacancy
3. timeout            8. empty response (success, source not broken)
4. rate limit         9. provider unavailable
5. malformed JSON    10. DB failure (nothing persisted)

The provider is replaced via ``app.services.ingestion.create_job_provider`` so
every downstream step (source resolution, dedup, normalization, persistence,
health tracking, commit) runs for real.
"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.providers.jobs.exceptions import RateLimitError, TransientFetchError
from app.repositories.job import JobRepository, JobSourceRepository
from app.schemas.job import RawJob
from app.services.ingestion import SourceFetchPipeline

INGESTION_TARGET = "app.services.ingestion.create_job_provider"


class FakeProvider:
    """Scriptable provider: returns canned RawJobs or raises."""

    def __init__(self, jobs=None, error=None):
        self._jobs = jobs or []
        self._error = error
        self.calls = 0

    async def fetch_jobs(self, filters=None, limit=100):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def make_raw_job(external_id="hh-1", title="Data Analyst", **overrides):
    payload = {
        "external_id": external_id,
        "title": title,
        "company": "Corp",
        "description": f"SQL and dashboards for {external_id}",
        "url": f"https://hh.kz/vacancy/{external_id}",
        "location": "Almaty",
    }
    payload.update(overrides)
    return RawJob(**payload)


def http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.hh.ru/vacancies")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


@pytest.fixture
async def session_factory(migrate_test_database):
    """Fresh engine + sessionmaker per test; migrations applied, rows cleaned."""
    # Fail fast: the teardown below TRUNCATEs job_sources, so this suite must
    # never point at a production database.
    assert "test" in str(settings.database_url), (
        f"refusing to run ingestion pipeline tests against non-test DB: "
        f"{settings.database_url}"
    )
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory

    async with factory() as session:
        await session.execute(text("TRUNCATE job_sources CASCADE"))
        await session.commit()
    await engine.dispose()


async def make_source(factory, type_="hh_kz", enabled=True, configuration=None):
    async with factory() as session:
        repo = JobSourceRepository(session)
        source = await repo.create(
            {
                "name": f"src-{uuid4().hex[:8]}",
                "type": type_,
                "enabled": enabled,
                "configuration": configuration or {},
            }
        )
        await session.commit()
        return source.id


async def get_source_row(factory, source_id):
    async with factory() as session:
        repo = JobSourceRepository(session)
        source = await repo.get(source_id)
        await session.refresh(source)
        return source


async def count_jobs(factory, source_id):
    async with factory() as session:
        result = await session.execute(
            text("SELECT count(*) FROM jobs WHERE source_id = :sid"),
            {"sid": str(source_id)},
        )
        return result.scalar_one()


# ---------------------------------------------------------------------------
# 1. Successful fetch: provider -> HTTP -> RawJob -> normalize -> DB -> commit
# ---------------------------------------------------------------------------


async def test_successful_fetch_persists_jobs_and_resets_health(
    session_factory, monkeypatch
):
    source_id = await make_source(
        session_factory,
        configuration={"filters": {"text": "sql"}, "limit": 50},
    )
    provider = FakeProvider(
        [make_raw_job("hh-1"), make_raw_job("hh-2"), make_raw_job("hh-3")]
    )
    monkeypatch.setattr(INGESTION_TARGET, lambda *a, **k: provider)

    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    assert result["status"] == "success"
    assert result["total_fetched"] == 3
    assert result["created"] == 3
    assert result["duplicates"] == 0
    assert result["errors"] == 0
    assert await count_jobs(session_factory, source_id) == 3

    source = await get_source_row(session_factory, source_id)
    assert source.fetch_count == 1
    assert source.consecutive_errors == 0
    assert source.last_success_at is not None
    assert source.last_fetch_at is not None


# ---------------------------------------------------------------------------
# 2-5. Transient fetch failures -> pipeline raises for Celery autoretry.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "expected_type"),
    [
        (http_status_error(500), TransientFetchError),  # HTTP 500
        (httpx.ConnectTimeout("timed out"), TransientFetchError),  # timeout
        (http_status_error(429), RateLimitError),  # rate limit
        (json.JSONDecodeError("bad json", "x", 0), TransientFetchError),
        (httpx.ConnectError("connection refused"), TransientFetchError),
    ],
)
async def test_transient_failures_raise_and_record_health(
    session_factory, monkeypatch, error, expected_type
):
    source_id = await make_source(session_factory)
    monkeypatch.setattr(
        INGESTION_TARGET, lambda *a, **k: FakeProvider(error=error)
    )

    with pytest.raises(expected_type):
        await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    # Health recorded, source still enabled (a single transient failure must
    # not disable it); the retry path resets it via on_source_success.
    source = await get_source_row(session_factory, source_id)
    assert source.consecutive_errors == 1
    assert source.error_count == 1
    assert source.enabled is True
    assert "429" in (source.last_error or "") or source.last_error
    assert await count_jobs(session_factory, source_id) == 0


# ---------------------------------------------------------------------------
# 6. Malformed single vacancy: skip the job, keep the rest of the batch.
# ---------------------------------------------------------------------------


async def test_malformed_vacancy_does_not_rollback_batch(
    session_factory, monkeypatch
):
    source_id = await make_source(session_factory)
    provider = FakeProvider(
        [
            make_raw_job("good-1"),
            # Passes RawJob validation but fails JobCreate's salary range rule
            # during normalization -> per-job error, batch continues.
            make_raw_job("bad-1", salary_min=500, salary_max=100),
            make_raw_job("good-2"),
        ]
    )
    monkeypatch.setattr(INGESTION_TARGET, lambda *a, **k: provider)

    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    assert result["status"] == "success"
    assert result["created"] == 2
    assert result["errors"] == 1
    # Both good vacancies are committed despite the bad one.
    assert await count_jobs(session_factory, source_id) == 2
    source = await get_source_row(session_factory, source_id)
    assert source.consecutive_errors == 0  # batch itself succeeded


async def test_db_level_failure_isolated_by_savepoint(session_factory, monkeypatch):
    """A poisoned flush must roll back only its SAVEPOINT, not the batch."""
    source_id = await make_source(session_factory)
    provider = FakeProvider(
        [make_raw_job("before-bad"), make_raw_job("bad-db"), make_raw_job("after-bad")]
    )
    monkeypatch.setattr(INGESTION_TARGET, lambda *a, **k: provider)

    original_create = JobRepository.create

    async def failing_create(self, obj_in):
        if obj_in.get("external_id") == "bad-db":
            # Real DBAPI error shape (e.g. unique/index violation).
            raise IntegrityError("INSERT INTO jobs", None, Exception("db constraint"))
        return await original_create(self, obj_in)

    monkeypatch.setattr(JobRepository, "create", failing_create)

    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    assert result["status"] == "success"
    assert result["errors"] == 1
    # Jobs created before AND after the failed one are all committed.
    assert await count_jobs(session_factory, source_id) == 2


# ---------------------------------------------------------------------------
# 7. Duplicate vacancy: no new row, counted as duplicate, last_seen updated.
# ---------------------------------------------------------------------------


async def test_duplicate_vacancy_is_counted_not_recreated(
    session_factory, monkeypatch
):
    source_id = await make_source(session_factory)
    raw = make_raw_job("dup-1")
    monkeypatch.setattr(INGESTION_TARGET, lambda *a, **k: FakeProvider([raw]))

    first = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)
    assert first["created"] == 1

    second = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)
    assert second["status"] == "success"
    assert second["created"] == 0
    assert second["duplicates"] == 1
    assert await count_jobs(session_factory, source_id) == 1


# ---------------------------------------------------------------------------
# 8. Empty response: success, zero jobs, provider NOT considered broken.
# ---------------------------------------------------------------------------


async def test_empty_response_is_success_and_resets_health(
    session_factory, monkeypatch
):
    source_id = await make_source(session_factory)
    provider = FakeProvider([])
    monkeypatch.setattr(INGESTION_TARGET, lambda *a, **k: provider)

    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    assert result["status"] == "success"
    assert result["total_fetched"] == 0
    assert result["created"] == 0
    source = await get_source_row(session_factory, source_id)
    assert source.consecutive_errors == 0
    assert source.last_error is None
    assert source.enabled is True


async def test_success_after_failures_resets_consecutive_errors(
    session_factory, monkeypatch
):
    """A recovery resets the consecutive-error counter (no auto-disable)."""
    source_id = await make_source(session_factory)

    monkeypatch.setattr(
        INGESTION_TARGET,
        lambda *a, **k: FakeProvider(error=httpx.ConnectError("down")),
    )
    with pytest.raises(TransientFetchError):
        await SourceFetchPipeline(session_factory).fetch_from_source(source_id)
    assert (await get_source_row(session_factory, source_id)).consecutive_errors == 1

    monkeypatch.setattr(
        INGESTION_TARGET, lambda *a, **k: FakeProvider([make_raw_job("back-1")])
    )
    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)
    assert result["status"] == "success"
    source = await get_source_row(session_factory, source_id)
    assert source.consecutive_errors == 0
    assert source.last_error is None
    assert source.enabled is True


# ---------------------------------------------------------------------------
# 9. Provider unavailable (network down) -> transient, retried by Celery.
# ---------------------------------------------------------------------------


async def test_provider_unavailable_is_transient(session_factory, monkeypatch):
    source_id = await make_source(session_factory)
    monkeypatch.setattr(
        INGESTION_TARGET,
        lambda *a, **k: FakeProvider(error=httpx.ConnectError("unreachable")),
    )
    with pytest.raises(TransientFetchError):
        await SourceFetchPipeline(session_factory).fetch_from_source(source_id)
    assert await count_jobs(session_factory, source_id) == 0


# ---------------------------------------------------------------------------
# 10. DB failure on commit -> transient (retried); nothing is persisted.
# ---------------------------------------------------------------------------


class FailingCommitSession(AsyncSession):
    """Session whose final commit fails, simulating a DB outage."""

    async def commit(self):
        raise OperationalError("COMMIT", {}, Exception("db down"))


async def test_db_failure_on_commit_is_transient_and_persists_nothing(
    session_factory, monkeypatch
):
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    failing_factory = async_sessionmaker(
        engine, class_=FailingCommitSession, expire_on_commit=False
    )
    source_id = await make_source(session_factory)
    monkeypatch.setattr(
        INGESTION_TARGET, lambda *a, **k: FakeProvider([make_raw_job("x-1")])
    )

    try:
        with pytest.raises(TransientFetchError):
            await SourceFetchPipeline(failing_factory).fetch_from_source(source_id)
    finally:
        await engine.dispose()

    # The whole transaction rolled back: no jobs persisted.
    assert await count_jobs(session_factory, source_id) == 0


# ---------------------------------------------------------------------------
# Permanent configuration error -> error status (NO retry), health recorded.
# ---------------------------------------------------------------------------


async def test_unknown_source_type_is_permanent_no_retry(session_factory):
    source_id = await make_source(session_factory, type_="nonexistent_provider")

    # No provider monkeypatch: the real factory must reject the unknown type.
    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    # Returned as a status dict (no exception -> no Celery retry).
    assert result["status"] == "error"
    assert "nonexistent_provider" in result["message"]
    source = await get_source_row(session_factory, source_id)
    assert source.consecutive_errors == 1
    assert source.enabled is True


async def test_disabled_source_is_skipped(session_factory, monkeypatch):
    source_id = await make_source(session_factory, enabled=False)
    provider = FakeProvider([make_raw_job()])
    monkeypatch.setattr(INGESTION_TARGET, lambda *a, **k: provider)

    result = await SourceFetchPipeline(session_factory).fetch_from_source(source_id)

    assert result["status"] == "skipped"
    assert provider.calls == 0



