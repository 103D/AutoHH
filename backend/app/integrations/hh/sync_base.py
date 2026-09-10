"""Shared primitives for read-only HH syncs (ADR-001 milestone 3).

Idempotency: every remote item is stored verbatim in ``raw_data`` with a
``content_hash`` (canonical JSON, SHA-256). The repositories skip unchanged
items, so re-running a sync is always safe.

Quarantine: a malformed remote item (missing id, wrong shape) is skipped and
counted — the batch continues, per ADR-001 error semantics. Nothing about a
malformed item is persisted.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.integrations.hh.exceptions import HHParseError


@dataclass
class SyncResult:
    """Counts of one sync run (reported to the API layer / workers)."""

    fetched: int = 0
    upserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "upserted": self.upserted,
            "skipped": self.skipped,
        }


def content_hash(item: Any) -> str:
    """Stable SHA-256 over the canonical JSON of a remote item."""
    canonical = json.dumps(
        item, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_remote_datetime(value: Any) -> datetime | None:
    """Parse an HH ISO-8601 timestamp; malformed values become None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def extract_items(payload: Any, *, what: str) -> list[Any]:
    """Validate the sync batch envelope: dict with an ``items`` list."""
    if isinstance(payload, dict):
        items = payload.get("items")
    else:
        items = payload
    if not isinstance(items, list):
        raise HHParseError(f"HH {what} sync: unexpected payload envelope")
    return items


def require_dict(item: Any, *, what: str) -> dict | None:
    """Quarantine guard: non-dict items are skipped."""
    return item if isinstance(item, dict) else None
