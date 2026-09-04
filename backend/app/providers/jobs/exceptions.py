"""Fetch-failure taxonomy shared by job providers and the ingestion pipeline.

The Celery task ``fetch_jobs_from_source`` retries only *transient* failures.
For that to work, every fetch-level failure must be classified before it
leaves the ingestion pipeline:

- ``TransientFetchError`` — network/timeout/5xx: safe to retry (Celery
  ``autoretry_for`` with exponential backoff);
- ``RateLimitError`` — HTTP 429: transient, retried with backoff;
- ``PermanentFetchError`` — 4xx (except 429), authentication and
  configuration errors: retrying would never succeed, so the pipeline records
  the source-health failure and returns an error status instead of raising.

Individual malformed vacancies never raise through this layer: providers skip
them per-item, and the pipeline isolates each job write in a SAVEPOINT.
"""

import json

import httpx
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError

from app.core.exceptions import JobHunterException, JobSourceError, NotFoundError


class FetchError(JobHunterException):
    """Base class for fetch-level (whole-batch) failures."""


class TransientFetchError(FetchError):
    """Transient provider/network/DB failure — Celery should retry."""


class RateLimitError(TransientFetchError):
    """HTTP 429 — retry with backoff (subclass of transient)."""


class PermanentFetchError(FetchError):
    """Permanent failure (4xx, auth, configuration) — never retried."""


def classify_fetch_error(error: BaseException) -> FetchError:
    """Translate any fetch-level failure into the retry taxonomy.

    Unknown errors classify as *permanent*: retrying a code bug only delays
    the failure and multiplies error noise; the source-health record still
    captures it.
    """
    if isinstance(error, FetchError):
        return error

    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code if error.response is not None else 0
        if status == 429:
            return RateLimitError(f"rate limited (HTTP 429): {error}")
        if 400 <= status < 500:
            return PermanentFetchError(f"client error (HTTP {status}): {error}")
        # 5xx and anything unexpected: server-side, worth retrying.
        return TransientFetchError(f"server error (HTTP {status}): {error}")

    if isinstance(error, httpx.TimeoutException):
        return TransientFetchError(f"provider timeout: {error}")
    if isinstance(error, httpx.TransportError):
        # ConnectError / NetworkError / RemoteProtocolError / ...
        return TransientFetchError(f"network error: {error}")
    if isinstance(error, httpx.HTTPError):
        return TransientFetchError(f"HTTP error: {error}")

    if isinstance(error, json.JSONDecodeError):
        # The provider answered with a body that is not valid JSON — almost
        # always a server-side/deploy artifact, so a retry may succeed.
        return TransientFetchError(f"malformed JSON response: {error}")

    if isinstance(error, OperationalError | SATimeoutError):
        return TransientFetchError(f"database unavailable: {error}")
    if isinstance(error, DBAPIError):
        # Covers connection-invalidated and driver-level disconnects.
        return TransientFetchError(f"database driver error: {error}")

    if isinstance(error, JobSourceError):
        # Misconfiguration (e.g. missing SuperJob API key): never transient.
        return PermanentFetchError(f"source configuration error: {error}")
    if isinstance(error, NotFoundError):
        return PermanentFetchError(f"not found: {error}")

    return PermanentFetchError(f"{type(error).__name__}: {error}")
