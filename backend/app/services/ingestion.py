"""Source ingestion pipeline (extracted from the Celery task wrapper).

Responsibilities (single bounded pipeline):
- resolve and validate the source (enabled + config);
- fetch raw vacancies via the provider factory;
- ingest each raw job through ``JobService`` (dedup + persist), isolating
  every job write in a SAVEPOINT so one malformed vacancy never rolls back
  the rest of the batch;
- update source stats and health (``source_health``) and commit;
- classify fetch-level failures into transient (re-raised for the Celery
  ``autoretry_for`` retry) and permanent (recorded in source health and
  returned as an error status) — see ``app.providers.jobs.exceptions``;
- emit Prometheus metrics per source/status.

The Celery tasks in ``app.workers.tasks.fetch_jobs`` stay thin: they only
marshal ``asyncio.run()`` and retry configuration around this pipeline, so
the whole fetch flow is testable without a broker/worker (see
``tests/unit/test_ingestion.py`` and ``tests/test_ingestion_pipeline.py``).
"""

import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import metrics
from app.core.database import get_engine
from app.core.logging import get_logger
from app.providers.jobs.exceptions import (
    FetchError,
    PermanentFetchError,
    TransientFetchError,
    classify_fetch_error,
)
from app.providers.jobs.factory import create_job_provider
from app.repositories.job import JobRepository, JobSourceRepository
from app.services.deduplication import DeduplicationService
from app.services.job import JobService, JobSourceService
from app.services.source_health import on_source_failure, on_source_success

logger = get_logger(__name__)


class SourceFetchPipeline:
    """Orchestrates one source fetch: fetch -> ingest -> health -> commit."""

    def __init__(self, session_factory: async_sessionmaker | None = None):
        # Optional override for tests; the production path lazily builds a
        # factory from the shared engine in ``_resolve_session_factory``.
        self._session_factory_override = session_factory

    def _resolve_session_factory(self) -> async_sessionmaker:
        """Return the injected factory or build one from the shared engine."""
        if self._session_factory_override is not None:
            return self._session_factory_override
        engine = get_engine()
        return async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    async def fetch_from_source(self, source_id: UUID) -> dict:
        """Fetch all jobs from a single source; returns a status dict.

        Raises ``TransientFetchError`` (incl. ``RateLimitError``) so the
        Celery wrapper can retry; permanent failures are recorded in source
        health and returned as ``{"status": "error" | "disabled", ...}``.
        """
        started = time.perf_counter()
        factory = self._resolve_session_factory()
        async with factory() as session:
            source = None
            try:
                source_service = JobSourceService(JobSourceRepository(session))
                source = await source_service.get_source(source_id)

                if not source.enabled:
                    logger.info(
                        "Source disabled, skipping fetch",
                        extra={
                            "source": source.name,
                            "operation": "fetch_jobs",
                            "status": "skipped",
                            "reason": "disabled",
                        },
                    )
                    metrics.inc_job_fetch(source.type, "skipped")
                    return {
                        "status": "skipped",
                        "source": source.name,
                        "reason": "disabled",
                    }

                logger.info(
                    "Fetching jobs from source",
                    extra={
                        "source": source.name,
                        "type": source.type,
                        "operation": "fetch_jobs",
                    },
                )

                # An unknown source type or invalid provider configuration is
                # permanent: retrying cannot fix it.
                try:
                    provider = create_job_provider(source.type, source.configuration)
                except Exception as e:  # noqa: BLE001 - re-wrapped as permanent
                    raise PermanentFetchError(
                        f"cannot build provider for source type "
                        f"{source.type!r}: {e}"
                    ) from e

                raw_jobs = await provider.fetch_jobs(
                    filters=source.configuration.get("filters", {}),
                    limit=source.configuration.get("limit", 100),
                )

                logger.info(
                    "Raw jobs fetched",
                    extra={
                        "source": source.name,
                        "jobs_received": len(raw_jobs),
                        "operation": "fetch_jobs",
                    },
                )

                job_service = JobService(JobRepository(session))
                dedup_service = DeduplicationService(JobRepository(session))

                created_count = 0
                duplicate_count = 0
                error_count = 0

                for raw_job in raw_jobs:
                    # Each job write runs in a SAVEPOINT: a malformed vacancy
                    # (validation error, constraint violation) rolls back only
                    # itself, never the whole batch.
                    try:
                        async with session.begin_nested():
                            _, status = await job_service.ingest_raw_job(
                                source_id, raw_job, dedup_service
                            )
                        if status == "created":
                            created_count += 1
                        elif status == "duplicate":
                            duplicate_count += 1
                        metrics.inc_job_ingested(source.type, status)
                    except Exception as e:
                        logger.warning(
                            "Error processing raw job",
                            extra={
                                "source": source.name,
                                "external_id": getattr(raw_job, "external_id", None),
                                "error": str(e),
                                "operation": "fetch_jobs",
                                "status": "job_error",
                            },
                        )
                        metrics.inc_job_ingested(source.type, "error")
                        error_count += 1

                # Update source stats and reset health state
                source.last_fetch_at = datetime.now(UTC)
                source.fetch_count += 1
                on_source_success(source)

                await session.commit()

                result = {
                    "status": "success",
                    "source": source.name,
                    "total_fetched": len(raw_jobs),
                    "created": created_count,
                    "duplicates": duplicate_count,
                    "errors": error_count,
                }

                logger.info(
                    "Job fetch completed",
                    extra={
                        "source": source.name,
                        "operation": "fetch_jobs",
                        "status": "success",
                        "jobs_received": len(raw_jobs),
                        "jobs_created": created_count,
                        "jobs_duplicate": duplicate_count,
                        "jobs_error": error_count,
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000, 1
                        ),
                    },
                )
                metrics.inc_job_fetch(source.type, "success")
                return result

            except Exception as e:
                classified = classify_fetch_error(e)
                # Snapshot display fields BEFORE rollback: rollback expires
                # ORM instances, and lazy-loading an expired attribute from a
                # sync context (logging, arithmetic) raises MissingGreenlet.
                source_name = source.name if source is not None else None
                source_type = source.type if source is not None else None
                await session.rollback()

                disabled = False
                if source is not None:
                    disabled = await self._record_source_failure(
                        session, source, source_name, classified, started
                    )

                if isinstance(classified, TransientFetchError):
                    # Re-raise so the Celery task's ``autoretry_for`` retries
                    # with backoff. Source health was already recorded above;
                    # a successful retry resets it via ``on_source_success``.
                    if source_type is not None:
                        metrics.inc_job_fetch(source_type, "error")
                    raise classified from e

                status = "disabled" if disabled else "error"
                if source_type is not None:
                    metrics.inc_job_fetch(source_type, status)
                    return {
                        "status": status,
                        "source": source_name,
                        "disabled": disabled,
                        "message": str(classified),
                    }

                logger.error(
                    "Job fetch failed before source resolution",
                    extra={
                        "source_id": str(source_id),
                        "operation": "fetch_jobs",
                        "status": "error",
                        "error": str(classified),
                        "error_type": type(classified).__name__,
                    },
                )
                return {
                    "status": "error",
                    "source": str(source_id),
                    "message": str(classified),
                }

    async def _record_source_failure(
        self,
        session: AsyncSession,
        source,
        source_name: str | None,
        error: FetchError,
        started: float,
    ) -> bool:
        """Update source health after a fetch failure; best-effort commit.

        Returns ``True`` when this failure disabled the source. The commit is
        best-effort because the failure itself may be a DB outage — health
        persistence must never mask the original error.
        """
        # The preceding rollback expired the ORM instance; reload it inside an
        # async context before touching (or reading) any attribute.
        try:
            await session.refresh(source)
        except Exception:
            pass

        source.last_fetch_at = datetime.now(UTC)
        source.error_count = (source.error_count or 0) + 1
        disabled = on_source_failure(source, error)
        consecutive = source.consecutive_errors  # snapshot before commit/rollback
        try:
            await session.commit()
        except Exception:
            await session.rollback()

        logger.error(
            "Job fetch failed",
            extra={
                "source": source_name or "<unknown>",
                "operation": "fetch_jobs",
                "status": "disabled" if disabled else "error",
                "error": str(error),
                "error_type": type(error).__name__,
                "transient": isinstance(error, TransientFetchError),
                "consecutive_errors": consecutive,
                "disabled": disabled,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return disabled
