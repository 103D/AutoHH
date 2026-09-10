"""Read-only negotiation (applicant response) synchronization, ADR-001 m3.

``GET /negotiations?status=active`` -> idempotent upserts into
``hh_negotiations`` with pagination. The applicant-visible remote state is
stored as data (state_id/state_name) — it is never mapped onto the local
Application workflow. Malformed items are quarantined; the batch continues.
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
from app.repositories.hh import HHNegotiationRepository

logger = get_logger(__name__)

MAX_PAGES = 20  # hard bound so a remote paging bug cannot loop forever
PER_PAGE = 50


def parse_negotiation_item(item: Any) -> dict | None:
    """Map a remote negotiation to storage fields; None => quarantined.

    ``state`` is essential for an applicant response — an item without it is
    treated as malformed (ADR-001: applicant states are remote data).
    """
    if not isinstance(item, dict):
        return None
    remote_id = item.get("id")
    state = item.get("state") if isinstance(item.get("state"), dict) else {}
    if remote_id is None or not (state.get("id") or state.get("name")):
        return None

    vacancy = item.get("vacancy") if isinstance(item.get("vacancy"), dict) else {}
    resume = item.get("resume") if isinstance(item.get("resume"), dict) else {}
    messages = item.get("messages") if isinstance(item.get("messages"), list) else []

    return {
        "remote_negotiation_id": str(remote_id),
        "remote_resume_id": _optional_remote_id(resume.get("id") or item.get("resume_id")),
        "remote_vacancy_id": _optional_remote_id(vacancy.get("id") or item.get("vacancy_id")),
        "state_id": state.get("id"),
        "state_name": state.get("name"),
        "remote_created_at": parse_remote_datetime(item.get("created_at")),
        "remote_updated_at": parse_remote_datetime(item.get("updated_at")),
        "messages_metadata": {
            "count": len(messages),
            "last_message_at": (
                parse_remote_datetime(messages[-1].get("created_at")).isoformat()
                if messages and isinstance(messages[-1], dict)
                and parse_remote_datetime(messages[-1].get("created_at"))
                else None
            ),
        }
        if messages
        else {},
        "raw_data": item,
        "content_hash": content_hash(item),
    }


def _optional_remote_id(value: Any) -> str | None:
    return str(value) if value is not None else None


class HHNegotiationSync:
    """Idempotent negotiation sync for one connected account."""

    def __init__(
        self, session: AsyncSession, account: HHAccount, client: HHApplicantClient
    ):
        self.repo = HHNegotiationRepository(session)
        self.account = account
        self.client = client

    async def run(self, *, status: str = "active") -> SyncResult:
        result = SyncResult()
        for page in range(MAX_PAGES):
            payload = await self.client.list_negotiations(
                status=status, page=page, per_page=PER_PAGE
            )
            items = extract_items(payload, what="negotiation")
            for item in items:
                result.fetched += 1
                parsed = parse_negotiation_item(item)
                if parsed is None:
                    result.skipped += 1
                    logger.warning(
                        "HH negotiation item quarantined (malformed): %r",
                        item,
                        extra={"hh_account_id": str(self.account.id)},
                    )
                    continue
                _, changed = await self.repo.upsert_from_remote(
                    self.account.id, parsed
                )
                if changed:
                    result.upserted += 1

            if not self._has_next_page(payload, page):
                break

        logger.info(
            "HH negotiation sync done: account=%s fetched=%s upserted=%s skipped=%s",
            self.account.id, result.fetched, result.upserted, result.skipped,
        )
        return result

    @staticmethod
    def _has_next_page(payload: Any, current_page: int) -> bool:
        if not isinstance(payload, dict):
            return False
        pages = payload.get("pages")
        try:
            return int(pages) > current_page + 1
        except (TypeError, ValueError):
            return False
