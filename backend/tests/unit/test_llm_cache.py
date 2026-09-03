"""Tests for the Redis-backed LLM result cache (task specs #28, #29)."""

import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.llm_cache import CachedAIProvider


class FakeRedis:
    """Minimal async redis stub."""

    def __init__(self, store=None):
        self.store = store if store is not None else {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


def _provider_result(score=83):
    return SimpleNamespace(
        score=score,
        matched_skills=["SQL"],
        missing_skills=["DAX"],
        strong_matches=["SQL"],
        concerns=[],
        reasoning_summary="ok",
        tokens_used=100,
        cost_usd=0.01,
    )


def _make_provider(calls):
    async def analyze_job(**kwargs):
        calls.append(kwargs)
        return _provider_result()

    return SimpleNamespace(analyze_job=analyze_job, name="fake")


def _kwargs():
    return {
        "job_title": "Data Analyst",
        "job_company": "Corp",
        "job_description": "SQL and dashboards",
        "job_requirements": {"skills": ["SQL"]},
        "candidate_profile": {
            "skills": ["SQL"],
            "technologies": {},
            "experience_level": "middle",
        },
    }


@pytest.fixture
def enable_cache(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_enabled", True)


async def test_cache_hit_avoids_second_provider_call(enable_cache):
    calls = []
    store = {}
    first = CachedAIProvider(_make_provider(calls), redis_client=FakeRedis(store))
    r1 = await first.analyze_job(**_kwargs())
    assert len(calls) == 1

    second = CachedAIProvider(_make_provider(calls), redis_client=FakeRedis(store))
    r2 = await second.analyze_job(**_kwargs())

    assert len(calls) == 1  # provider was NOT called the second time
    assert r2.score == r1.score
    assert r2.tokens_used == r1.tokens_used
    assert r2.reasoning_summary == r1.reasoning_summary


async def test_cache_disabled_calls_provider_directly(monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_enabled", False)
    calls = []
    store = {}
    cached = CachedAIProvider(_make_provider(calls), redis_client=FakeRedis(store))

    await cached.analyze_job(**_kwargs())

    assert len(calls) == 1
    assert store == {}  # nothing written to redis


async def test_cache_read_failure_falls_back_to_provider(enable_cache):
    class BrokenRedis:
        async def get(self, key):
            raise ConnectionError("redis down")

        async def set(self, key, value, ex=None):
            pass

    calls = []
    cached = CachedAIProvider(_make_provider(calls), redis_client=BrokenRedis())

    result = await cached.analyze_job(**_kwargs())

    assert len(calls) == 1
    assert result.score == _provider_result().score


async def test_cache_write_failure_does_not_break_result(enable_cache):
    class WriteBrokenRedis:
        async def get(self, key):
            return None

        async def set(self, key, value, ex=None):
            raise ConnectionError("redis down on write")

    calls = []
    cached = CachedAIProvider(_make_provider(calls), redis_client=WriteBrokenRedis())

    result = await cached.analyze_job(**_kwargs())

    assert len(calls) == 1
    assert result.score == _provider_result().score


async def test_provider_error_propagates_and_nothing_cached(enable_cache):
    async def fail(**kwargs):
        raise RuntimeError("boom")

    provider = SimpleNamespace(analyze_job=fail, name="fake")
    redis = FakeRedis()
    cached = CachedAIProvider(provider, redis_client=redis)

    with pytest.raises(RuntimeError):
        await cached.analyze_job(**_kwargs())

    assert redis.store == {}


async def test_cache_key_depends_on_profile_skills(enable_cache):
    cached = CachedAIProvider(_make_provider([]), redis_client=FakeRedis())
    kw = _kwargs()
    base = cached._cache_key(kw)

    kw2 = _kwargs()
    kw2["candidate_profile"] = dict(kw["candidate_profile"], skills=["Power BI"])

    assert cached._cache_key(kw2) != base


async def test_cache_key_changes_with_prompt_version(enable_cache, monkeypatch):
    cached = CachedAIProvider(_make_provider([]), redis_client=FakeRedis())
    kw = _kwargs()
    base = cached._cache_key(kw)

    monkeypatch.setattr(settings, "prompt_version", "v2")

    assert cached._cache_key(kw) != base
    assert cached._cache_key(kw).startswith("autohh:llm:v2:")


async def test_cached_payload_roundtrip_keeps_result_fields(enable_cache):
    """Every RESULT_FIELD survives the JSON roundtrip (SimpleNamespace out)."""
    from app.services.llm_cache import RESULT_FIELDS

    calls = []
    store = {}
    first = CachedAIProvider(_make_provider(calls), redis_client=FakeRedis(store))
    await first.analyze_job(**_kwargs())

    raw = json.loads(next(iter(store.values())))
    assert set(raw) == set(RESULT_FIELDS)
    assert raw["score"] == _provider_result().score
