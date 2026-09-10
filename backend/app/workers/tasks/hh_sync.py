"""Celery tasks for HH account sync (ADR-001 milestone 6).

This module stays a thin wrapper around the already-testable HH account service:
it lists connected accounts, runs read-only sync, records metrics and returns a
compact summary. Transient HH failures from per-account task bodies are retried
by Celery; batch sync records and continues so one bad account does not block
others.
"""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import metrics
from app.core.config import settings
from app.core.database import get_engine
from app.core.logging import get_logger
from app.integrations.hh.accounts import HHAccountService
from app.integrations.hh.exceptions import HHAuthRequiredError, HHTransientError
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="sync_hh_account",
    autoretry_for=(HHTransientError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def sync_hh_account(user_id: str) -> dict:
    """Sync one connected HH applicant account."""
    return asyncio.run(_sync_hh_account_async(UUID(user_id)))


async def _sync_hh_account_async(user_id: UUID) -> dict:
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        service = HHAccountService(session)
        try:
            results = await service.sync_all(user_id)
            await session.commit()
        except HHAuthRequiredError as exc:
            await session.rollback()
            metrics.inc_hh_sync("sync_all", "reauth_required")
            logger.warning("HH sync requires reauth for user %s: %s", user_id, exc)
            return {"status": "reauth_required", "user_id": str(user_id)}
        except HHTransientError:
            await session.rollback()
            metrics.inc_hh_sync("sync_all", "transient_error")
            raise
        except Exception as exc:
            await session.rollback()
            metrics.inc_hh_sync("sync_all", "error")
            logger.exception("HH sync failed for user %s: %s", user_id, exc)
            return {"status": "error", "user_id": str(user_id), "message": str(exc)}

    _record_item_metrics(results)
    metrics.inc_hh_sync("sync_all", "success")
    return {
        "status": "success",
        "user_id": str(user_id),
        "resumes": results["resumes"].as_dict(),
        "negotiations": results["negotiations"].as_dict(),
    }


@celery_app.task(name="sync_all_hh_accounts")
def sync_all_hh_accounts(limit: int | None = None) -> dict:
    """Run read-only sync for all connected HH accounts in a bounded batch."""
    return asyncio.run(_sync_all_hh_accounts_async(limit=limit or settings.hh_sync_batch_size))


async def _sync_all_hh_accounts_async(limit: int | None = None) -> dict:
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    summary = {
        "status": "success",
        "accounts_scanned": 0,
        "success": 0,
        "transient_error": 0,
        "reauth_required": 0,
        "error": 0,
        "accounts": [],
    }
    async with session_factory() as session:
        service = HHAccountService(session)
        accounts = await service.repo.list_connected(limit=limit or settings.hh_sync_batch_size)
        for account in accounts:
            summary["accounts_scanned"] += 1
            try:
                results = await service.sync_all(account.user_id)
                await session.commit()
                _record_item_metrics(results)
                metrics.inc_hh_sync("sync_all", "success")
                summary["success"] += 1
                summary["accounts"].append(
                    {"user_id": str(account.user_id), "status": "success"}
                )
            except HHAuthRequiredError as exc:
                await session.rollback()
                metrics.inc_hh_sync("sync_all", "reauth_required")
                summary["reauth_required"] += 1
                summary["accounts"].append(
                    {"user_id": str(account.user_id), "status": "reauth_required"}
                )
                logger.warning("HH sync skipped (reauth): user=%s %s", account.user_id, exc)
            except HHTransientError as exc:
                await session.rollback()
                metrics.inc_hh_sync("sync_all", "transient_error")
                summary["transient_error"] += 1
                summary["accounts"].append(
                    {"user_id": str(account.user_id), "status": "transient_error"}
                )
                logger.warning("HH sync transient failure: user=%s %s", account.user_id, exc)
            except Exception as exc:
                await session.rollback()
                metrics.inc_hh_sync("sync_all", "error")
                summary["error"] += 1
                summary["accounts"].append(
                    {"user_id": str(account.user_id), "status": "error"}
                )
                logger.exception("HH sync failed: user=%s %s", account.user_id, exc)
    return summary


def _record_item_metrics(results: dict) -> None:
    for entity in ("resumes", "negotiations"):
        counts = results[entity].as_dict()
        for outcome in ("fetched", "upserted", "skipped"):
            metrics.inc_hh_sync_items(entity, outcome, int(counts.get(outcome, 0)))
