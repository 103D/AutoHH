import asyncio
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import metrics
from app.core.database import get_engine
from app.core.logging import get_logger
from app.providers.jobs.factory import create_job_provider
from app.repositories.job import JobRepository, JobSourceRepository
from app.services.deduplication import DeduplicationService
from app.services.job import JobService, JobSourceService
from app.services.source_health import on_source_failure, on_source_success
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="fetch_jobs_from_source",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def fetch_jobs_from_source(source_id: str) -> dict:
    """
    Fetch jobs from a specific source.
    This is a synchronous wrapper for async operations.
    """
    return asyncio.run(_fetch_jobs_from_source_async(UUID(source_id)))


async def _fetch_jobs_from_source_async(source_id: UUID) -> dict:
    """
    Async implementation of job fetching.
    """
    started = time.perf_counter()
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        source = None
        try:
            # Get source
            source_repo = JobSourceRepository(session)
            source_service = JobSourceService(source_repo)
            source = await source_service.get_source(source_id)

            if not source.enabled:
                logger.info(
                    "Source disabled, skipping fetch",
                    extra={"source": source.name, "operation": "fetch_jobs", "status": "skipped", "reason": "disabled"},
                )
                metrics.inc_job_fetch(source.type, "skipped")
                return {"status": "skipped", "source": source.name, "reason": "disabled"}

            logger.info(
                "Fetching jobs from source",
                extra={"source": source.name, "type": source.type, "operation": "fetch_jobs"},
            )

            # Initialize provider using factory
            provider = create_job_provider(source.type, source.configuration)

            # Fetch jobs
            raw_jobs = await provider.fetch_jobs(
                filters=source.configuration.get("filters", {}),
                limit=source.configuration.get("limit", 100),
            )

            logger.info(
                "Raw jobs fetched",
                extra={"source": source.name, "jobs_received": len(raw_jobs), "operation": "fetch_jobs"},
            )

            # Process each job
            job_repo = JobRepository(session)
            job_service = JobService(job_repo)
            dedup_service = DeduplicationService(job_repo)

            created_count = 0
            duplicate_count = 0
            error_count = 0

            for raw_job in raw_jobs:
                try:
                    job, status = await job_service.ingest_raw_job(
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
                        extra={"source": source.name, "external_id": raw_job.external_id, "error": str(e), "operation": "fetch_jobs", "status": "job_error"},
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
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
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
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
                return {"status": status, "source": source.name, "disabled": disabled, "message": str(e)}

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
            return {"status": "error", "source": str(source_id), "message": str(e)}


@celery_app.task(name="fetch_jobs_from_all_sources")
def fetch_jobs_from_all_sources() -> dict:
    """
    Fetch jobs from all enabled sources.
    """
    return asyncio.run(_fetch_jobs_from_all_sources_async())


async def _fetch_jobs_from_all_sources_async() -> dict:
    """
    Async implementation of fetching from all sources.
    """
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            source_repo = JobSourceRepository(session)
            source_service = JobSourceService(source_repo)

            sources = await source_service.get_enabled_sources()
            logger.info(f"Found {len(sources)} enabled sources")

            results = []
            for source in sources:
                logger.info(f"Triggering fetch for source: {source.name}")
                # Trigger individual task for each source
                task = fetch_jobs_from_source.delay(str(source.id))
                results.append(
                    {
                        "source_id": str(source.id),
                        "source_name": source.name,
                        "task_id": task.id,
                    }
                )

            return {
                "status": "success",
                "sources_triggered": len(results),
                "tasks": results,
            }

        except Exception as e:
            logger.error(f"Error in fetch_jobs_from_all_sources: {e}")
            return {
                "status": "error",
                "message": str(e),
            }
