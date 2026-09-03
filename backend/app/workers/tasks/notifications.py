"""Celery task for sending Telegram notifications about job matches."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_engine
from app.core.logging import get_logger
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.repositories.notification import NotificationRepository
from app.services.telegram import TelegramBotAdapter
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="send_notifications")
def send_notifications(limit: int = 20) -> dict:
    """Send notifications about high-priority job matches."""
    import asyncio

    return asyncio.run(_send_notifications_async(limit))


async def _send_notifications_async(limit: int) -> dict:
    """Async implementation of notification sending."""
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            match_repo = MatchResultRepository(session)
            notification_repo = NotificationRepository(session)
            job_repo = JobRepository(session)
            telegram = TelegramBotAdapter()

            # Get high-priority matches not yet notified
            # For now, use get_pending_notification from match repo
            # and filter out those already in notification_logs

            # Get all candidate profiles (single user for now)
            from sqlalchemy import select

            from app.models.candidate import CandidateProfile

            result = await session.execute(select(CandidateProfile).limit(1))
            profile = result.scalar_one_or_none()

            if not profile:
                logger.info("No candidate profile found, skipping notifications")
                return {"status": "success", "sent": 0, "message": "No profile"}

            pending_matches = await match_repo.get_pending_notification(
                profile.id, limit=limit
            )

            sent_count = 0
            failed_count = 0

            for match in pending_matches:
                # Check if already notified
                existing = await notification_repo.get_by_match_result(match.id)
                if existing:
                    continue

                # Get job
                job = await job_repo.get(match.job_id)
                if not job:
                    continue

                # Create notification log
                notification = await notification_repo.create(
                    {
                        "match_result_id": match.id,
                        "status": "pending",
                    }
                )

                # Send via Telegram
                message_id = await telegram.send_match_notification(match, job)

                if message_id:
                    notification.telegram_message_id = message_id
                    notification.status = "sent"

                    notification.sent_at = datetime.now(UTC)
                    sent_count += 1
                else:
                    notification.status = "failed"
                    notification.error = "Failed to send Telegram message"
                    failed_count += 1

            await session.commit()

            logger.info(
                f"Notifications: sent={sent_count}, failed={failed_count}"
            )

            return {
                "status": "success",
                "sent": sent_count,
                "failed": failed_count,
            }

        except Exception as e:
            logger.error(f"Error in send_notifications: {e}")
            await session.rollback()
            return {"status": "error", "message": str(e)}


@celery_app.task(name="send_daily_digest")
def send_daily_digest(limit: int = 5) -> dict:
    """Send the daily top-5 digest to Telegram (career intelligence v2)."""
    import asyncio

    return asyncio.run(_send_daily_digest_async(limit))


async def _send_daily_digest_async(limit: int) -> dict:
    """Async implementation of the daily digest."""
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            from sqlalchemy import select

            from app.models.candidate import CandidateProfile
            from app.models.matching import MatchCategory
            from app.repositories.job import JobRepository
            from app.repositories.matching import MatchResultRepository
            from app.repositories.notification import NotificationRepository
            from app.services.telegram_v2 import (
                TelegramDigestAdapter,
                select_daily_top,
            )

            result = await session.execute(select(CandidateProfile).limit(1))
            profile = result.scalar_one_or_none()
            if not profile:
                logger.info("No candidate profile found, skipping daily digest")
                return {"status": "success", "sent": 0, "message": "No profile"}

            match_repo = MatchResultRepository(session)
            notification_repo = NotificationRepository(session)
            job_repo = JobRepository(session)

            actionable = await match_repo.get_effective_top(
                profile.id,
                categories=[
                    MatchCategory.DREAM_JOB,
                    MatchCategory.STRETCH,
                    MatchCategory.SOLID_MATCH,
                ],
                limit=50,
            )

            # Keep only matches never notified before
            fresh: list[tuple] = []
            for match in actionable:
                if await notification_repo.get_by_match_result(match.id):
                    continue
                job = await job_repo.get(match.job_id)
                if job:
                    fresh.append((match, job))

            top = select_daily_top(fresh, limit=limit)
            if not top:
                logger.info("No new actionable matches for the daily digest")
                return {"status": "success", "sent": 0, "message": "Nothing to send"}

            telegram = TelegramDigestAdapter()
            message_id = await telegram.send_daily_digest(top)

            digest_status = "sent" if message_id else "failed"
            for match, _job in top:
                notification = await notification_repo.create(
                    {
                        "match_result_id": match.id,
                        "status": digest_status,
                        "error": None if message_id else "Failed to send daily digest",
                    }
                )
                if message_id:
                    notification.telegram_message_id = message_id
                    notification.sent_at = datetime.now(UTC)

            await session.commit()
            logger.info(f"Daily digest: sent={len(top)} (status={digest_status})")
            return {"status": "success", "sent": len(top), "message_id": message_id}

        except Exception as e:
            logger.error(f"Error in send_daily_digest: {e}")
            await session.rollback()
            return {"status": "error", "message": str(e)}
