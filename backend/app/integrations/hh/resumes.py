"""Read-only applicant resume synchronization (ADR-001 milestone 3).

``GET /resumes/mine`` -> idempotent upserts into ``hh_resumes``. Malformed
items are quarantined (skipped + counted) and the batch continues. The sync
never mutates anything remote and never writes into local resume profiles —
linking happens in milestone 4.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.integrations.hh.client import HHApplicantClient
from app.integrations.hh.sync_base import (
    SyncResult,
    content_hash,
    extract_items,
    parse_remote_datetime,
)
from app.models.hh import HHAccount
from app.repositories.hh import HHResumeRepository

logger = get_logger(__name__)


def parse_resume_item(item: Any) -> dict | None:
    """Map a remote resume brief to storage fields; None => quarantined."""
    if not isinstance(item, dict):
        return None
    remote_id = item.get("id")
    if remote_id is None:
        return None
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    return {
        "remote_resume_id": str(remote_id),
        "title": item.get("title"),
        "status": status.get("id") or status.get("name"),
        "remote_updated_at": parse_remote_datetime(item.get("updated_at")),
        "raw_data": item,
        "content_hash": content_hash(item),
    }


class HHResumeSync:
    """Idempotent resume sync for one connected account."""

    def __init__(
        self, session: AsyncSession, account: HHAccount, client: HHApplicantClient
    ):
        self.repo = HHResumeRepository(session)
        self.account = account
        self.client = client

    async def run(self) -> SyncResult:
        result = SyncResult()
        payload = await self.client.list_resumes()
        items = extract_items(payload, what="resume")

        for item in items:
            result.fetched += 1
            parsed = parse_resume_item(item)
            if parsed is None:
                result.skipped += 1
                logger.warning(
                    "HH resume item quarantined (malformed): %r", item, extra={
                        "hh_account_id": str(self.account.id)
                    }
                )
                continue
            _, changed = await self.repo.upsert_from_remote(self.account.id, parsed)
            if changed:
                result.upserted += 1

        logger.info(
            "HH resume sync done: account=%s fetched=%s upserted=%s skipped=%s",
            self.account.id, result.fetched, result.upserted, result.skipped,
        )
        return result
