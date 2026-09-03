"""Source health tracking for the ingestion pipeline.

A source that fails too many times in a row is auto-disabled so that:

- a misbehaving provider is not polled forever by the beat schedule;
- the rest of the pipeline keeps running (graceful degradation).

The logic lives in pure helpers (no imports of the ORM at runtime) so it is
easy to unit test.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.job import JobSource


def on_source_success(source: "JobSource") -> None:
    """Reset the error state after a successful fetch."""
    source.consecutive_errors = 0
    source.last_error = None
    source.last_success_at = datetime.now(UTC)


def on_source_failure(
    source: "JobSource",
    error: Exception | str,
    max_consecutive: int | None = None,
) -> bool:
    """Record a fetch failure; auto-disable the source after N consecutive errors.

    Returns ``True`` when the source was disabled by this failure.
    """
    max_consecutive = max_consecutive or settings.max_consecutive_source_errors
    message = str(error)
    source.consecutive_errors = (source.consecutive_errors or 0) + 1

    if source.consecutive_errors >= max_consecutive:
        source.enabled = False
        source.last_error = (
            f"Disabled after {source.consecutive_errors} consecutive failures: {message}"
        )
        return True

    source.last_error = message
    return False
