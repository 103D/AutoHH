"""One-time OAuth state handling (ADR-001 security rules).

The state parameter binds the callback to the local user and cannot be
replayed:

- integrity/expiry: HMAC-SHA256 signature over ``{user_id, nonce, iat}``
  (signed with ``SECRET_KEY``) plus a short TTL checked on verification;
- one-time use: the nonce is stored server-side and atomically popped on the
  callback, so a captured URL cannot be used twice;
- user binding: the stored record carries the user_id that started the flow.

Nonce storage uses Redis when available (multi-worker safe); a process-local
fallback keeps single-worker deployments and tests hermetic.
"""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.logging import get_logger

from .exceptions import HHStateError

logger = get_logger(__name__)

_SIGNING_KEY_INFO = b"hh-oauth-state-v1"


def _signing_key() -> bytes:
    """Derive an HMAC key from SECRET_KEY (domain-separated)."""
    return hashlib.sha256(settings.secret_key.encode() + _SIGNING_KEY_INFO).digest()


class OAuthStateSigner:
    """HMAC-signed, expiring OAuth state tokens bound to a local user."""

    def __init__(self, ttl_seconds: int | None = None):
        self.ttl_seconds = ttl_seconds or settings.hh_oauth_state_ttl_seconds

    def issue(self, user_id: UUID) -> str:
        """Create ``base64(payload).base64(signature)`` state for the user."""
        payload = {
            "user_id": str(user_id),
            "nonce": uuid4().hex,
            "iat": int(time.time()),
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(_signing_key(), raw, hashlib.sha256).hexdigest()
        import base64

        return f"{base64.urlsafe_b64encode(raw).decode()}.{signature}"

    def verify(self, state: str) -> dict[str, Any]:
        """Validate signature and TTL; return the payload or raise HHStateError."""
        import base64

        try:
            raw_b64, signature = state.split(".", 1)
            raw = base64.urlsafe_b64decode(raw_b64.encode())
        except (ValueError, TypeError) as exc:
            raise HHStateError("Malformed OAuth state") from exc

        expected = hmac.new(_signing_key(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HHStateError("OAuth state signature mismatch")

        payload = json.loads(raw)
        issued_at = payload.get("iat")
        if not isinstance(issued_at, int) or time.time() - issued_at > self.ttl_seconds:
            raise HHStateError("OAuth state expired")
        return payload


class StateStore(Protocol):
    """Server-side one-time nonce storage."""

    async def put(self, nonce: str, value: str, ttl_seconds: int) -> None: ...

    async def pop(self, nonce: str) -> str | None:
        """Atomically read-and-delete; second read must return None."""
        ...


class InMemoryStateStore:
    """Process-local store for tests and single-worker deployments."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, float]] = {}

    async def put(self, nonce: str, value: str, ttl_seconds: int) -> None:
        self._entries[nonce] = (value, time.monotonic() + ttl_seconds)

    async def pop(self, nonce: str) -> str | None:
        entry = self._entries.pop(nonce, None)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            return None
        return value


class RedisStateStore:
    """Redis-backed store: safe across workers (SET EX / GETDEL)."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def put(self, nonce: str, value: str, ttl_seconds: int) -> None:
        await self._get_client().set(f"hh:oauth:state:{nonce}", value, ex=ttl_seconds)

    async def pop(self, nonce: str) -> str | None:
        return await self._get_client().getdel(f"hh:oauth:state:{nonce}")


def get_state_store() -> StateStore:
    """Redis when configured, in-memory fallback otherwise (warned)."""
    if settings.redis_url:
        return RedisStateStore(str(settings.redis_url))
    logger.warning(
        "REDIS_URL is not configured: OAuth state falls back to an in-memory "
        "store, which is only safe for single-worker deployments."
    )
    return InMemoryStateStore()


def state_expiry() -> datetime:
    """Absolute expiry for display/tests (UTC)."""
    return datetime.now(UTC) + timedelta(seconds=settings.hh_oauth_state_ttl_seconds)
