from datetime import UTC, datetime
from uuid import UUID

from app.core.database import async_session_maker
from app.core.logging import get_logger
from app.providers.jobs.factory import create_job_provider
from app.repositories.job import JobRepository, JobSourceRepository
from app.services.deduplication import DeduplicationService
from app.services.job import JobService, JobSourceService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="fetch_jobs_from_source")
def fetch_jobs_from_source(source_id: str) -> dict:
    """
    Fetch jobs from a specific source.
    This is a synchronous wrapper for async operations.
    """
    import asyncio

    return asyncio.run(_fetch_jobs_from_source_async(UUID(source_id)))


async def _fetch_jobs_from_source_async(source_id: UUID) -> dict:
    """
    Async implementation of job fetching.
    """
    async with async_session_maker() as session:
        source = None
        try:
            # Get source
            source_repo = JobSourceRepository(session)
            source_service = JobSourceService(source_repo)
            source = await source_service.get_source(source_id)

            logger.info(f"Fetching jobs from source: {source.name}")

            # Initialize provider using factory
            provider = create_job_provider(source.type, source.configuration)

            # Fetch jobs
            raw_jobs = await provider.fetch_jobs(
                filters=source.configuration.get("filters", {}),
                limit=source.configuration.get("limit", 100),
            )

            logger.info(f"Fetched {len(raw_jobs)} raw jobs")

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

                except Exception as e:
                    logger.error(f"Error processing job {raw_job.external_id}: {e}")
                    error_count += 1

            # Update source stats
            source.last_fetch_at = datetime.now(UTC)
            source.last_success_at = datetime.now(UTC)
            source.fetch_count += 1
            source.last_error = None

            await session.commit()

            result = {
                "status": "success",
                "source": source.name,
                "total_fetched": len(raw_jobs),
                "created": created_count,
                "duplicates": duplicate_count,
                "errors": error_count,
            }

            logger.info(f"Job fetch completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Error in fetch_jobs_from_source: {e}")

            # Update source error stats
            if source:
                source.last_fetch_at = datetime.now(UTC)
                source.last_error = str(e)
                source.error_count += 1

            await session.commit()

            return {
                "status": "error",
                "source": str(source_id),
                "message": str(e),
            }


@celery_app.task(name="fetch_jobs_from_all_sources")
def fetch_jobs_from_all_sources() -> dict:
    """
    Fetch jobs from all enabled sources.
    """
    import asyncio

    return asyncio.run(_fetch_jobs_from_all_sources_async())


async def _fetch_jobs_from_all_sources_async() -> dict:
    """
    Async implementation of fetching from all sources.
    """
    async with async_session_maker() as session:
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
