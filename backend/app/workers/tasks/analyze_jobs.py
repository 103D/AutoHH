"""Celery task for analyzing new jobs."""

from uuid import UUID

from app.core.database import async_session_maker
from app.core.logging import get_logger
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.services.candidate import CandidateService
from app.services.matching import MatchingService
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="analyze_job")
def analyze_job(job_id: str) -> dict:
    """
    Analyze a single job.
    This is a synchronous wrapper for async operations.
    """
    import asyncio

    return asyncio.run(_analyze_job_async(UUID(job_id)))


async def _analyze_job_async(job_id: UUID) -> dict:
    """
    Async implementation of job analysis.
    """
    async with async_session_maker() as session:
        try:
            job_repo = JobRepository(session)
            candidate_repo = CandidateRepository(session)
            match_repo = MatchResultRepository(session)
            candidate_service = CandidateService(candidate_repo)

            matching_service = MatchingService(job_repo, candidate_service, match_repo)

            logger.info(f"Analyzing job: {job_id}")

            result = await matching_service.analyze_job(job_id)

            await session.commit()

            return {
                "status": "success",
                "job_id": str(job_id),
                "score": result.score,
                "recommendation": result.recommendation,
            }

        except Exception as e:
            logger.error(f"Error analyzing job {job_id}: {e}")
            return {
                "status": "error",
                "job_id": str(job_id),
                "message": str(e),
            }


@celery_app.task(name="analyze_new_jobs")
def analyze_new_jobs(limit: int = 50) -> dict:
    """
    Analyze jobs that haven't been analyzed yet.
    This is a synchronous wrapper for async operations.
    """
    import asyncio

    return asyncio.run(_analyze_new_jobs_async(limit))


async def _analyze_new_jobs_async(limit: int) -> dict:
    """
    Async implementation of batch job analysis.
    """
    async with async_session_maker() as session:
        try:
            job_repo = JobRepository(session)
            candidate_repo = CandidateRepository(session)
            match_repo = MatchResultRepository(session)
            candidate_service = CandidateService(candidate_repo)

            matching_service = MatchingService(job_repo, candidate_service, match_repo)

            logger.info(f"Analyzing up to {limit} new jobs")

            results = await matching_service.analyze_pending_jobs(limit)

            await session.commit()

            # Summary statistics
            score_distribution = {"HIGH_PRIORITY": 0, "APPLY": 0, "REVIEW": 0, "IGNORE": 0}
            for result in results:
                score_distribution[result.recommendation] = (
                    score_distribution.get(result.recommendation, 0) + 1
                )

            return {
                "status": "success",
                "total_analyzed": len(results),
                "distribution": score_distribution,
            }

        except Exception as e:
            logger.error(f"Error in analyze_new_jobs: {e}")
            return {
                "status": "error",
                "message": str(e),
            }
