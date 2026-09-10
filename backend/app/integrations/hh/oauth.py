"""HH OAuth 2.0 client (ADR-001): PKCE, code exchange, refresh, revoke.

Talks only to ``hh.ru`` OAuth endpoints. Tokens are never logged; error
messages carry the remote error code only. Transient failures (timeout, 429,
5xx) are retried with bounded backoff and then surface as
:class:`HHTransientError`; a refused grant surfaces as
:class:`HHOAuthError` (with ``requires_reauth`` for dead grants).

PKCE (S256) is opt-in via ``HH_OAUTH_USE_PKCE`` because it works only for HH
applications registered with PKCE support (ADR-001: "where supported").
"""

import asyncio
import base64
import hashlib
import secrets
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import get_logger

from .exceptions import HHOAuthError, HHTransientError

logger = get_logger(__name__)

# Grants that are gone for good: only a fresh user-approved connect helps.
_REAUTH_GRANT_ERRORS = {"invalid_grant", "unauthorized_client", "access_denied"}


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` per RFC 7636 S256."""
    code_verifier = secrets.token_urlsafe(48)[:64]
    challenge_digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_digest).decode().rstrip("=")
    return code_verifier, code_challenge


class HHOAuthClient:
    """Async client for the hh.ru OAuth endpoints."""

    AUTHORIZE_URL = "https://hh.ru/oauth/authorize"
    TOKEN_URL = "https://hh.ru/oauth/token"
    REVOKE_URL = "https://hh.ru/oauth/revoke"

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ):
        self._client_id = settings.hh_oauth_client_id
        self._client_secret = settings.hh_oauth_client_secret
        self._redirect_uri = settings.hh_oauth_redirect_uri
        self._user_agent = user_agent or settings.hh_user_agent
        self._timeout = timeout
        self._transport = transport
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    def build_authorization_url(
        self,
        *,
        state: str,
        code_challenge: str | None = None,
    ) -> str:
        """Build the user-facing authorize URL (fails fast on missing config)."""
        if not self._client_id or not self._redirect_uri:
            raise HHOAuthError(
                "HH OAuth is not configured: set HH_OAUTH_CLIENT_ID and "
                "HH_OAUTH_REDIRECT_URI (register an application at dev.hh.ru)"
            )
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
        }
        if settings.hh_oauth_use_pkce:
            if not code_challenge:
                raise HHOAuthError("PKCE is enabled but no code_challenge was provided")
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return str(httpx.Request("GET", self.AUTHORIZE_URL, params=params).url)

    async def exchange_code(
        self, code: str, *, code_verifier: str | None = None
    ) -> OAuthTokens:
        """Exchange the authorization code for the first token pair."""
        if not self._client_id or not self._client_secret:
            raise HHOAuthError("HH OAuth is not configured (client id/secret missing)")
        form = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
        }
        if self._redirect_uri:
            form["redirect_uri"] = self._redirect_uri
        if settings.hh_oauth_use_pkce:
            if not code_verifier:
                raise HHOAuthError("PKCE is enabled but no code_verifier was provided")
            form["code_verifier"] = code_verifier
        return await self._token_request(form)

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """Rotate tokens with the refresh grant (single-flight per account)."""
        if not self._client_id or not self._client_secret:
            raise HHOAuthError("HH OAuth is not configured (client id/secret missing)")
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        )

    async def revoke_token(self, token: str) -> None:
        """Best-effort revoke; HH may not implement RFC 7009 — that is fine."""
        if not self._client_id or not self._client_secret:
            return
        try:
            await self._request_with_retries(
                "POST",
                self.REVOKE_URL,
                data={
                    "token": token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
        except (HHTransientError, HHOAuthError) as exc:
            logger.warning("HH token revoke was not confirmed: %s", type(exc).__name__)

    # -- internals ---------------------------------------------------------

    async def _token_request(self, form: dict[str, str]) -> OAuthTokens:
        response = await self._request_with_retries("POST", self.TOKEN_URL, data=form)
        try:
            body = response.json()
            if "access_token" not in body or "refresh_token" not in body:
                raise ValueError("token response is missing fields")
            return OAuthTokens(
                access_token=str(body["access_token"]),
                refresh_token=str(body["refresh_token"]),
                expires_in=int(body.get("expires_in", 0)),
                token_type=str(body.get("token_type", "bearer")),
            )
        except (ValueError, TypeError) as exc:
            raise HHOAuthError(f"Malformed token response: {exc}") from exc

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                await asyncio.sleep(self._backoff_base * (2 ** (attempt - 1)))
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    headers={
                        "User-Agent": self._user_agent,
                        "HH-User-Agent": self._user_agent,
                        "Accept": "application/json",
                    },
                    transport=self._transport,
                ) as client:
                    response = await client.request(method, url, data=data)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "HH OAuth transient error (attempt %s): %s",
                    attempt + 1,
                    type(exc).__name__,
                )
                continue

            if response.status_code == 429 or response.status_code >= 500:
                last_error = HHOAuthError(
                    f"HH OAuth transient status {response.status_code}"
                )
                logger.warning(
                    "HH OAuth transient status %s (attempt %s)",
                    response.status_code,
                    attempt + 1,
                )
                continue

            if response.status_code >= 400:
                error_code = self._remote_error_code(response)
                raise HHOAuthError(
                    f"HH OAuth error {response.status_code}: {error_code}",
                    requires_reauth=error_code in _REAUTH_GRANT_ERRORS,
                )
            return response

        raise HHTransientError(
            f"HH OAuth unavailable after retries: {type(last_error).__name__}"
        )

    @staticmethod
    def _remote_error_code(response: httpx.Response) -> str:
        try:
            body = response.json()
            code = body.get("error") if isinstance(body, dict) else None
            return str(code or "unknown_error")
        except ValueError:
            return "unparseable_error"
