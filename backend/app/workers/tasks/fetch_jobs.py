"""Celery task wrappers for the job ingestion pipeline.

Real logic lives in ``app.services.ingestion.SourceFetchPipeline`` (testable
without a broker). This module only:
- defines the Celery task names / retry policy;
- schedules per-source tasks from the list of enabled sources.

Retry semantics (task spec: transient vs permanent failures):
- the pipeline raises ``TransientFetchError`` (incl. ``RateLimitError``) for
  network/timeout/5xx/429/DB-outage failures -> retried here with exponential
  backoff (max 3 attempts);
- permanent failures (4xx, auth, configuration) are recorded in source health
  by the pipeline and returned as an error status — they never reach
  ``autoretry_for``, so they are never retried.
"""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_engine
from app.providers.jobs.exceptions import TransientFetchError
from app.repositories.job import JobSourceRepository
from app.services.ingestion import SourceFetchPipeline
from app.services.job import JobSourceService
from app.workers.celery_app import celery_app


@celery_app.task(
    name="fetch_jobs_from_source",
    autoretry_for=(TransientFetchError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def fetch_jobs_from_source(source_id: str) -> dict:
    """
    Fetch jobs from a specific source.
    This is a synchronous wrapper for the async ingestion pipeline.
    """
    return asyncio.run(SourceFetchPipeline().fetch_from_source(UUID(source_id)))


@celery_app.task(name="fetch_jobs_from_all_sources")
def fetch_jobs_from_all_sources() -> dict:
    """
    Fetch jobs from all enabled sources (dispatches one task per source).
    """
    return asyncio.run(_fetch_jobs_from_all_sources_async())


async def _fetch_jobs_from_all_sources_async() -> dict:
    """List enabled sources and schedule an individual fetch task for each."""
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            source_service = JobSourceService(JobSourceRepository(session))
            sources = await source_service.get_enabled_sources()

            results = []
            for source in sources:
                # Trigger the individual task for each source
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
            return {
                "status": "error",
                "message": str(e),
            }
