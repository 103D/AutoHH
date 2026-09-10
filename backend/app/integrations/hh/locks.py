"""HH distributed locks (ADR-001 M6).

Used around token refresh so multiple worker processes do not refresh the same
account concurrently. Redis is the production backend; in-memory is a safe
single-process fallback for tests/local development.
"""

import time
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class HHLockBackend(Protocol):
    async def acquire(self, key: str, owner: str, ttl_seconds: int) -> bool: ...
    async def release(self, key: str, owner: str) -> None: ...


class InMemoryHHLockBackend:
    """Process-local lock backend; safe only for single-worker deployments."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[str, float]] = {}

    async def acquire(self, key: str, owner: str, ttl_seconds: int) -> bool:
        now = time.monotonic()
        current = self._locks.get(key)
        if current is not None:
            current_owner, expires_at = current
            if current_owner != owner and expires_at > now:
                return False
        self._locks[key] = (owner, now + ttl_seconds)
        return True

    async def release(self, key: str, owner: str) -> None:
        current = self._locks.get(key)
        if current is not None and current[0] == owner:
            self._locks.pop(key, None)


class RedisHHLockBackend:
    """Redis SET NX EX lock with owner-token checked release."""

    def __init__(self, redis_url: str, *, client: Any | None = None) -> None:
        self._redis_url = redis_url
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _redis_key(key: str) -> str:
        return f"hh:lock:{key}"

    async def acquire(self, key: str, owner: str, ttl_seconds: int) -> bool:
        return bool(
            await self._get_client().set(
                self._redis_key(key), owner, nx=True, ex=ttl_seconds
            )
        )

    async def release(self, key: str, owner: str) -> None:
        redis = self._get_client()
        redis_key = self._redis_key(key)
        if await redis.get(redis_key) == owner:
            await redis.delete(redis_key)


def get_hh_lock_backend() -> HHLockBackend:
    """Redis when configured, otherwise process-local fallback."""
    if settings.redis_url:
        return RedisHHLockBackend(str(settings.redis_url))
    logger.warning(
        "REDIS_URL is not configured: HH refresh locks use an in-memory "
        "backend, which is only safe for single-worker deployments."
    )
    return InMemoryHHLockBackend()
