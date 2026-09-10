"""Redis-backed cache for AI job analyses (task specs #28, #29).

Cache key = hash(job title/company/description/requirements
                 + candidate skills fingerprint + prompt_version).

``same vacancy + same candidate profile + same prompt version`` => reuse the
previous analysis instead of paying for a new LLM call. Cache read/write
failures degrade gracefully to a direct provider call — the pipeline never
depends on Redis being available.

The wrapped object exposes the same ``analyze_job`` interface as the
underlying AIProvider, so it is a drop-in decorator (no second abstraction).
"""

import hashlib
import json
import logging
from types import SimpleNamespace

from app.core import metrics
from app.core.config import settings
from app.services.match_provenance import candidate_snapshot

logger = logging.getLogger(__name__)

# AIAnalysisResult fields persisted into the cache entry.
RESULT_FIELDS = (
    "score",
    "matched_skills",
    "missing_skills",
    "strong_matches",
    "concerns",
    "reasoning_summary",
    "requirements",
    "skill_equivalences",
    "seniority_signal",
    "domain_signal",
    "tokens_used",
    "cost_usd",
)


class CachedAIProvider:
    """Decorator around an AIProvider adding a Redis result cache."""

    def __init__(self, provider, redis_client=None):
        self.provider = provider
        self._redis = redis_client
        self.name = getattr(provider, "name", provider.__class__.__name__)

    # --- redis -----------------------------------------------------------

    def _get_redis(self):
        """Lazily create the async Redis client; None => cache disabled."""
        if self._redis is not None:
            return self._redis
        url = getattr(settings, "redis_url", None) or getattr(
            settings, "celery_broker_url", None
        )
        if not url:
            return None
        try:
            import redis.asyncio as redis_asyncio

            self._redis = redis_asyncio.from_url(
                url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=1.0,
            )
        except Exception as e:  # pragma: no cover - construction is trivial
            logger.warning(f"LLM cache disabled, redis client unavailable: {e}")
            self._redis = None
        return self._redis

    # --- key --------------------------------------------------------------

    @staticmethod
    def _profile_fingerprint(profile_dict: dict) -> str:
        """Stable fingerprint of the candidate profile part that affects matching."""
        payload = json.dumps(
            candidate_snapshot(profile_dict),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _json_safe(value):
        """Convert Pydantic/domain values to a JSON-serializable structure."""
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {
                str(key): CachedAIProvider._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list | tuple):
            return [CachedAIProvider._json_safe(item) for item in value]
        return value

    def _cache_key(self, kwargs: dict) -> str:
        payload = json.dumps(
            {
                "title": kwargs.get("job_title"),
                "company": kwargs.get("job_company"),
                "description": kwargs.get("job_description"),
                "requirements": kwargs.get("job_requirements"),
                "profile": self._profile_fingerprint(kwargs.get("candidate_profile") or {}),
                "prompt_version": settings.prompt_version,
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"autohh:llm:{settings.prompt_version}:{digest}"

    # --- interface ---------------------------------------------------------

    async def analyze_job(self, **kwargs):
        """Cache-through analysis; falls back to the provider on any cache error."""
        if not settings.llm_cache_enabled:
            return await self.provider.analyze_job(**kwargs)

        redis = None
        key = None
        try:
            redis = self._get_redis()
            if redis is not None:
                key = self._cache_key(kwargs)
                raw = await redis.get(key)
                if raw:
                    data = json.loads(raw)
                    metrics.inc_llm(self.name, "cache_hit")
                    return SimpleNamespace(**data)
        except Exception as e:
            logger.warning(f"LLM cache read failed (proceeding to provider): {e}")
            redis = None

        try:
            result = await self.provider.analyze_job(**kwargs)
        except Exception:
            metrics.inc_llm(self.name, "error")
            raise

        metrics.inc_llm(self.name, "called")
        metrics.add_llm_cost(self.name, float(getattr(result, "cost_usd", 0) or 0))

        try:
            if redis is not None and key:
                payload = {
                    field: self._json_safe(getattr(result, field, None))
                    for field in RESULT_FIELDS
                }
                ttl_seconds = max(int(settings.llm_cache_ttl_hours), 1) * 3600
                await redis.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
        except Exception as e:
            logger.warning(f"LLM cache write failed (analysis still valid): {e}")

        return result
