"""Unit tests for the ingestion pipeline seam and retry taxonomy (no DB).

Covers:
- the ``_session_factory`` attribute/method name-collision regression
  (``SourceFetchPipeline()`` without an override used to crash with
  ``TypeError: 'NoneType' object is not callable``);
- ``classify_fetch_error`` transient/permanent mapping;
- Celery task retry configuration and exception propagation;
- per-item robustness of providers (one malformed vacancy never fails the
  batch) via ``httpx.MockTransport``.
"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core import metrics
from app.core.exceptions import JobSourceError, NotFoundError
from app.providers.jobs.exceptions import (
    PermanentFetchError,
    RateLimitError,
    TransientFetchError,
    classify_fetch_error,
)
from app.services.ingestion import SourceFetchPipeline
from app.workers.tasks.fetch_jobs import fetch_jobs_from_source

# ---------------------------------------------------------------------------
# Fix #1 regression: instance attribute must not shadow the resolver method.
# ---------------------------------------------------------------------------


def test_session_factory_resolves_without_override():
    """SourceFetchPipeline() (no custom factory) must resolve a real factory."""
    pipeline = SourceFetchPipeline()
    factory = pipeline._resolve_session_factory()
    assert isinstance(factory, async_sessionmaker)


def test_session_factory_override_wins():
    override = async_sessionmaker()
    pipeline = SourceFetchPipeline(session_factory=override)
    assert pipeline._resolve_session_factory() is override


def test_session_factory_attribute_does_not_shadow_method():
    """Regression: the attribute and the resolver must have distinct names."""
    pipeline = SourceFetchPipeline()
    assert pipeline._session_factory_override is None
    assert callable(type(pipeline)._resolve_session_factory)


# ---------------------------------------------------------------------------
# classify_fetch_error: transient vs permanent.
# ---------------------------------------------------------------------------


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/vacancies")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_classify_5xx_is_transient(status):
    assert isinstance(classify_fetch_error(_status_error(status)), TransientFetchError)


def test_classify_429_is_rate_limit_and_transient():
    classified = classify_fetch_error(_status_error(429))
    assert isinstance(classified, RateLimitError)
    assert isinstance(classified, TransientFetchError)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_classify_4xx_is_permanent(status):
    classified = classify_fetch_error(_status_error(status))
    assert isinstance(classified, PermanentFetchError)
    assert not isinstance(classified, TransientFetchError)


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectTimeout("timeout"),
        httpx.ReadTimeout("timeout"),
        httpx.ConnectError("connection refused"),
        httpx.RemoteProtocolError("peer closed"),
    ],
)
def test_classify_network_errors_are_transient(error):
    assert isinstance(classify_fetch_error(error), TransientFetchError)


def test_classify_malformed_json_is_transient():
    error = json.JSONDecodeError("Expecting value", "<html>oops</html>", 0)
    assert isinstance(classify_fetch_error(error), TransientFetchError)


def test_classify_db_operational_error_is_transient():
    error = OperationalError("COMMIT", {}, Exception("db down"))
    assert isinstance(classify_fetch_error(error), TransientFetchError)


def test_classify_config_error_is_permanent():
    error = JobSourceError("SuperJob API key is not configured")
    assert isinstance(classify_fetch_error(error), PermanentFetchError)


def test_classify_not_found_is_permanent():
    assert isinstance(classify_fetch_error(NotFoundError("gone")), PermanentFetchError)


def test_classify_unknown_error_is_permanent():
    classified = classify_fetch_error(RuntimeError("bug"))
    assert isinstance(classified, PermanentFetchError)
    assert not isinstance(classified, TransientFetchError)


def test_classify_passes_through_fetch_errors():
    error = RateLimitError("already classified")
    assert classify_fetch_error(error) is error


# ---------------------------------------------------------------------------
# Celery task retry semantics (no broker needed).
# ---------------------------------------------------------------------------


def test_celery_task_retries_only_transient_errors():
    assert TransientFetchError in fetch_jobs_from_source.autoretry_for
    # Rate limits are retried via the TransientFetchError subclass.
    assert issubclass(RateLimitError, TransientFetchError)
    # Permanent failures must never trigger autoretry.
    assert PermanentFetchError not in fetch_jobs_from_source.autoretry_for
    assert not issubclass(PermanentFetchError, tuple(fetch_jobs_from_source.autoretry_for))
    assert fetch_jobs_from_source.max_retries == 3
    assert fetch_jobs_from_source.retry_backoff is True


def test_celery_task_propagates_transient_error(monkeypatch):
    """A transient pipeline failure must escape the task body -> autoretry."""

    async def fake_fetch(self, source_id):
        raise TransientFetchError("provider 503")

    monkeypatch.setattr(SourceFetchPipeline, "fetch_from_source", fake_fetch)
    with pytest.raises(TransientFetchError):
        fetch_jobs_from_source.run(str(uuid4()))


def test_celery_task_returns_status_for_permanent_error(monkeypatch):
    """A permanent failure comes back as a status dict -> no retry."""

    async def fake_fetch(self, source_id):
        return {"status": "error", "source": "x", "message": "HTTP 403"}

    monkeypatch.setattr(SourceFetchPipeline, "fetch_from_source", fake_fetch)
    result = fetch_jobs_from_source.run(str(uuid4()))
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Provider per-item robustness via httpx.MockTransport (no network).
# ---------------------------------------------------------------------------


def _mock_httpx_client(monkeypatch, handler):
    """Route every httpx.AsyncClient through a MockTransport handler."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


HH_VALID_ITEM = {
    "id": "123",
    "name": "Data Analyst",
    "employer": {"name": "Corp"},
    "description": "SQL required",
    "alternate_url": "https://hh.kz/vacancy/123",
    "area": {"name": "Almaty"},
}


async def test_hh_skips_malformed_item_and_keeps_valid(monkeypatch):
    from app.providers.jobs.hh_kz import HeadHunterKZProvider

    def handler(request):
        # One valid item + one item missing the mandatory "id".
        return httpx.Response(200, json={"items": [HH_VALID_ITEM, {"name": "Broken"}]})

    _mock_httpx_client(monkeypatch, handler)
    provider = HeadHunterKZProvider()
    jobs = await provider.fetch_jobs()
    assert [j.external_id for j in jobs] == ["123"]


async def test_hh_500_raises_http_status_error(monkeypatch):
    from app.providers.jobs.hh_kz import HeadHunterKZProvider

    _mock_httpx_client(monkeypatch, lambda request: httpx.Response(500))
    provider = HeadHunterKZProvider()
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.fetch_jobs()
    # ...and the pipeline taxonomy maps it to a transient (retryable) error.
    assert isinstance(classify_fetch_error(exc_info.value), TransientFetchError)


async def test_hh_429_raises_rate_limitable_error(monkeypatch):
    from app.providers.jobs.hh_kz import HeadHunterKZProvider

    _mock_httpx_client(monkeypatch, lambda request: httpx.Response(429))
    provider = HeadHunterKZProvider()
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await provider.fetch_jobs()
    assert isinstance(classify_fetch_error(exc_info.value), RateLimitError)


async def test_hh_malformed_json_is_classified_transient(monkeypatch):
    from app.providers.jobs.hh_kz import HeadHunterKZProvider

    _mock_httpx_client(
        monkeypatch, lambda request: httpx.Response(200, content=b"<html>down</html>")
    )
    provider = HeadHunterKZProvider()
    with pytest.raises(json.JSONDecodeError) as exc_info:
        await provider.fetch_jobs()
    assert isinstance(classify_fetch_error(exc_info.value), TransientFetchError)


async def test_remote_ok_skips_malformed_items(monkeypatch):
    from app.providers.jobs.remote_ok import RemoteOkProvider

    def handler(request):
        return httpx.Response(
            200,
            json=[
                {"legal": "metadata entry"},  # feed metadata: skipped
                {
                    "id": "1",
                    "position": "Data Analyst",
                    "company": "A",
                    "description": "sql",
                    "url": "https://x/1",
                },
                {"id": "2", "position": None},  # malformed: skipped by guard
            ],
        )

    _mock_httpx_client(monkeypatch, handler)
    provider = RemoteOkProvider()
    jobs = await provider.fetch_jobs()
    assert [j.external_id for j in jobs] == ["1"]


async def test_manual_provider_skips_invalid_entries():
    from app.providers.jobs.manual import ManualProvider

    provider = ManualProvider(
        {
            "jobs": [
                {
                    "external_id": "ok-1",
                    "title": "Analyst",
                    "company": "A",
                    "description": "d",
                    "url": "https://x/1",
                },
                {"external_id": "bad-1", "title": "", "company": "B"},
                "not-a-dict",
            ]
        }
    )
    jobs = await provider.fetch_jobs()
    assert [j.external_id for j in jobs] == ["ok-1"]


async def test_habr_career_skips_malformed_postings(monkeypatch):
    from app.providers.jobs.habr_career import HabrCareerProvider

    good = {
        "@type": "JobPosting",
        "title": "Data Analyst",
        "hiringOrganization": {"name": "Corp"},
        "description": "<p>SQL</p>",
        "url": "/vacancies/1",
    }
    # hiringOrganization must be an Organization object; a plain string makes
    # the parser crash (AttributeError on .get) -> the item is skipped.
    bad = {
        "@type": "JobPosting",
        "title": "Broken",
        "hiringOrganization": "not-a-dict",
        "description": "x",
        "url": "/vacancies/2",
    }
    first_page = (
        '<html><script type="application/ld+json">'
        + json.dumps([good, bad])
        + "</script></html>"
    )

    def handler(request):
        # Stop pagination after page 1 (otherwise pages repeat forever).
        page = int(request.url.params.get("page", "1"))
        if page > 1:
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text=first_page)

    _mock_httpx_client(monkeypatch, handler)
    provider = HabrCareerProvider()
    jobs = await provider.fetch_jobs()
    assert len(jobs) == 1
    assert jobs[0].title == "Data Analyst"

# ---------------------------------------------------------------------------
# Metrics contract: observability must never break the pipeline (pin).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metric_fn,args",
    [
        (metrics.inc_job_fetch, ("hh_kz", "success")),
        (metrics.inc_job_ingested, ("hh_kz", "created")),
    ],
)
def test_metrics_helpers_never_raise(metric_fn, args):
    """Pin the metrics.py contract: inc_* helpers swallow every exception.

    ``SourceFetchPipeline`` calls these from inside its success/commit path;
    if a metric helper ever started raising, an already-committed fetch would
    be reported as an error (and retried), corrupting source health.
    """
    metric_fn(*args)  # must not raise


def test_metrics_helpers_do_not_raise_when_disabled(monkeypatch):
    """The disabled flag path must also be exception-free."""
    monkeypatch.setattr(metrics, "metrics_enabled", lambda: False)
    metrics.inc_job_fetch("hh_kz", "success")  # no-op, no raise
    metrics.inc_job_ingested("hh_kz", "duplicate")  # no-op, no raise



