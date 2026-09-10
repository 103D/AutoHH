"""Unit tests for HH Redis/distributed refresh lock abstraction (ADR-001 M6)."""


from app.integrations.hh.locks import InMemoryHHLockBackend, RedisHHLockBackend


async def test_in_memory_lock_allows_single_owner_only():
    backend = InMemoryHHLockBackend()

    assert await backend.acquire("acct", "owner-1", ttl_seconds=30) is True
    assert await backend.acquire("acct", "owner-2", ttl_seconds=30) is False
    await backend.release("acct", "owner-2")
    assert await backend.acquire("acct", "owner-3", ttl_seconds=30) is False
    await backend.release("acct", "owner-1")
    assert await backend.acquire("acct", "owner-3", ttl_seconds=30) is True


async def test_in_memory_lock_ttl_expires(monkeypatch):
    now = {"value": 100.0}
    monkeypatch.setattr("app.integrations.hh.locks.time.monotonic", lambda: now["value"])
    backend = InMemoryHHLockBackend()

    assert await backend.acquire("acct", "owner-1", ttl_seconds=5) is True
    now["value"] = 106.0
    assert await backend.acquire("acct", "owner-2", ttl_seconds=5) is True


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)


async def test_redis_lock_releases_only_owner_token():
    redis = FakeRedis()
    backend = RedisHHLockBackend("redis://unused", client=redis)

    assert await backend.acquire("acct", "owner-1", ttl_seconds=30) is True
    assert await backend.acquire("acct", "owner-2", ttl_seconds=30) is False

    await backend.release("acct", "owner-2")
    assert redis.values
    await backend.release("acct", "owner-1")
    assert redis.values == {}


def test_get_lock_backend_uses_memory_without_redis(monkeypatch):
    from app.core.config import settings
    from app.integrations.hh.locks import get_hh_lock_backend

    monkeypatch.setattr(settings, "redis_url", None, raising=False)
    assert isinstance(get_hh_lock_backend(), InMemoryHHLockBackend)
