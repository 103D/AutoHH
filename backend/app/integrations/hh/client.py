"""Typed HTTP client for authenticated HH applicant endpoints (ADR-001).

All requests carry the registered User-Agent (HH rejects common UAs with
403) and a Bearer token supplied by an injectable ``token_provider`` — the
client never stores or logs tokens itself.

Error semantics (ADR-001):
- 401 with ``auth_retries`` left -> re-resolve the token with
  ``force_refresh=True`` (refresh once) and retry the request once;
- exhausted 401s -> :class:`HHAuthRequiredError`;
- 403, unless the body carries the ``already_applied`` duplicate marker ->
  :class:`HHPermissionError` (permanent, visible to the user);
- ``already_applied`` duplicate -> :class:`HHAlreadyAppliedError`;
- 400 -> :class:`HHApiError`;
- 429/5xx/transport errors -> bounded backoff, then :class:`HHTransientError`;
- non-JSON response -> :class:`HHParseError` (sync layer skips the item).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

from .exceptions import (
    HHAlreadyAppliedError,
    HHApiError,
    HHAuthRequiredError,
    HHParseError,
    HHPermissionError,
    HHTransientError,
)

logger = get_logger(__name__)

TokenProvider = Callable[[bool], Awaitable[str]]


class HHApplicantClient:
    """Authenticated applicant-scope client for api.hh.ru."""

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        base_url: str = "https://api.hh.ru",
        user_agent: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ):
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent or settings.hh_user_agent
        self._timeout = timeout
        self._transport = transport
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    # -- public endpoint surface (read-only in milestone 3 scope) ----------

    async def get_current_user(self) -> dict[str, Any]:
        """``GET /me`` — identity and token health check."""
        return await self._request("GET", "/me")

    async def list_resumes(self) -> dict[str, Any]:
        """``GET /resumes/mine`` — applicant resume list."""
        return await self._request("GET", "/resumes/mine")

    async def get_resume(self, resume_id: str) -> dict[str, Any]:
        """``GET /resumes/{id}`` — one resume, full view."""
        return await self._request("GET", f"/resumes/{resume_id}")

    async def list_negotiations(
        self, *, status: str = "active", page: int = 0, per_page: int = 50
    ) -> dict[str, Any]:
        """``GET /negotiations`` — applicant responses, remote-state driven."""
        return await self._request(
            "GET",
            "/negotiations",
            params={"status": status, "page": page, "per_page": per_page},
        )

    async def apply_to_vacancy(
        self, *, resume_id: str, vacancy_id: str, message: str | None = None
    ) -> dict[str, Any]:
        """``POST /negotiations`` — explicit applicant response to a vacancy.

        The form carries ``resume_id``/``vacancy_id`` plus an optional cover
        ``message``. The 403 ``already_applied`` duplicate is detected in the
        request core and surfaces as :class:`HHAlreadyAppliedError`: per
        ADR-001 m5 the caller resolves the existing negotiation instead of
        reporting it as a failure.
        """
        form: dict[str, Any] = {"resume_id": resume_id, "vacancy_id": vacancy_id}
        if message:
            form["message"] = message
        return await self._request("POST", "/negotiations", data=form)

    async def get_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        """``GET /negotiations/{id}`` — one negotiation with messages/state."""
        return await self._request("GET", f"/negotiations/{negotiation_id}")

    # -- request core ------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        transient_attempt = 0
        auth_retries_left = 1  # ADR-001: refresh once, then retry once
        force_refresh = False

        while True:
            token = await self._token_provider(force_refresh)
            force_refresh = False
            headers = {
                "User-Agent": self._user_agent,
                "HH-User-Agent": self._user_agent,
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout, transport=self._transport
                ) as client:
                    response = await client.request(
                        method,
                        f"{self._base_url}{path}",
                        params=params,
                        data=data,
                        headers=headers,
                    )
            except httpx.HTTPError as exc:
                if transient_attempt >= self._max_retries:
                    raise HHTransientError(
                        f"HH API transport error after retries: {type(exc).__name__}"
                    ) from exc
                transient_attempt += 1
                await asyncio.sleep(self._backoff_base * (2 ** (transient_attempt - 1)))
                continue

            if response.status_code == 401:
                if auth_retries_left == 0:
                    raise HHAuthRequiredError(
                        "HH API rejected the token (401) after refresh retry"
                    )
                auth_retries_left = 0
                force_refresh = True
                logger.info("HH API 401: refreshing token once and retrying")
                continue

            if response.status_code == 403:
                text = _remote_error_text(response)
                if "already_applied" in text:
                    raise HHAlreadyAppliedError(
                        "HH reports an existing response for this pair"
                    )
                raise HHPermissionError(f"HH API refused the operation (403): {text}")

            if response.status_code == 429 or response.status_code >= 500:
                if transient_attempt >= self._max_retries:
                    raise HHTransientError(
                        f"HH API unavailable (status {response.status_code})"
                    )
                transient_attempt += 1
                await asyncio.sleep(self._backoff_base * (2 ** (transient_attempt - 1)))
                continue

            if response.status_code >= 400:
                raise HHApiError(
                    f"HH API client error {response.status_code} for {path}: "
                    f"{_remote_error_text(response)}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise HHParseError(f"HH API returned non-JSON payload for {path}") from exc


def _remote_error_text(response: httpx.Response) -> str:
    """Compact remote error fingerprint (codes only, never credentials)."""
    try:
        body = response.json()
    except ValueError:
        text = (response.text or "")[:200]
        return text or "unparseable_error"
    if isinstance(body, dict):
        code = body.get("error") or body.get("error_code") or body.get("description")
        errors = body.get("errors")
        details: list[str] = []
        if isinstance(errors, list):
            for entry in errors:
                if not isinstance(entry, dict):
                    continue
                value = entry.get("value")
                message = entry.get("message") or entry.get("type")
                piece = (
                    f"{value}:{message}" if value and message else str(message or value)
                )
                if piece and piece != "None":
                    details.append(piece)
        parts = [str(code)] if code else []
        parts.extend(details)
        joined = ";".join(parts)[:300]
        return joined or "unknown_error"
    return "unexpected_error_shape"
