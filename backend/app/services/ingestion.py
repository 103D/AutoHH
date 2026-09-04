"""Source ingestion pipeline (extracted from the Celery task wrapper).

Responsibilities (single bounded pipeline):
- resolve and validate the source (enabled + config);
- fetch raw vacancies via the provider factory;
- ingest each raw job through ``JobService`` (dedup + persist);
- update source stats and health (``source_health``) and commit;
- emit Prometheus metrics per source/status.

The Celery tasks in ``app.workers.tasks.fetch_jobs`` stay thin: they only
marshal ``asyncio.run()`` and retry configuration around this pipeline, so
the whole fetch flow is testable without a broker/worker (see
``tests/unit/test_ingestion.py``).
"""

import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import metrics
from app.core.database import get_engine
from app.core.logging import get_logger
from app.providers.jobs.factory import create_job_provider
from app.repositories.job import JobRepository, JobSourceRepository
from app.services.deduplication import DeduplicationService
from app.services.job import JobService, JobSourceService
from app.services.source_health import on_source_failure, on_source_success

logger = get_logger(__name__)


class SourceFetchPipeline:
    """Orchestrates one source fetch: fetch -> ingest -> health -> commit."""

    def __init__(self, session_factory: async_sessionmaker | None = None):
        self._session_factory = session_factory

    def _session_factory(self) -> async_sessionmaker:
        if self._session_factory is not None:
            return self._session_factory
        engine = get_engine()
        return async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    async def fetch_from_source(self, source_id: UUID) -> dict:
        """Fetch all jobs from a single source; returns a status dict."""
        started = time.perf_counter()
        factory = self._session_factory()
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

                provider = create_job_provider(source.type, source.configuration)
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
                    try:
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
                                "external_id": raw_job.external_id,
                                "error": str(e),
                                "operation": "fetch_jobs",
                                "status": "job_error",
                            },
                        )
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
                await session.rollback()

                if source:
                    source.last_fetch_at = datetime.now(UTC)
                    source.error_count = (source.error_count or 0) + 1
                    disabled = on_source_failure(source, e)
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()

                    status = "disabled" if disabled else "error"
                    metrics.inc_job_fetch(source.type, status)
                    logger.error(
                        "Job fetch failed",
                        extra={
                            "source": source.name,
                            "operation": "fetch_jobs",
                            "status": status,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "consecutive_errors": source.consecutive_errors,
                            "disabled": disabled,
                            "duration_ms": round(
                                (time.perf_counter() - started) * 1000, 1
                            ),
                        },
                    )
                    return {
                        "status": status,
                        "source": source.name,
                        "disabled": disabled,
                        "message": str(e),
                    }

                logger.error(
                    "Job fetch failed before source resolution",
                    extra={
                        "source_id": str(source_id),
                        "operation": "fetch_jobs",
                        "status": "error",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                return {
                    "status": "error",
                    "source": str(source_id),
                    "message": str(e),
                }
