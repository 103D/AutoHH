"""Integration tests for the HH account lifecycle (ADR-001 milestones 1-2):
connect/callback with /me verification, encryption at rest, one-time state,
refresh under lock, REAUTH_REQUIRED on dead grants, disconnect."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.integrations.hh.accounts import HHAccountService
from app.integrations.hh.crypto import CredentialCipher
from app.integrations.hh.exceptions import (
    HHAuthRequiredError,
    HHIntegrationError,
    HHOAuthError,
    HHStateError,
)
from app.integrations.hh.oauth import OAuthTokens
from app.integrations.hh.state import InMemoryStateStore
from app.models.hh import HHAccountStatus


class FakeOAuthClient:
    """Scripted hh.ru OAuth endpoints for the lifecycle tests."""

    def __init__(self, *, refresh_error: Exception | None = None):
        self.exchange_calls = 0
        self.refresh_calls = 0
        self.revoked: list[str] = []
        self.refresh_error = refresh_error

    def build_authorization_url(self, *, state, code_challenge=None) -> str:
        return f"https://hh.ru/oauth/authorize?state={state}"

    async def exchange_code(self, code, *, code_verifier=None) -> OAuthTokens:
        self.exchange_calls += 1
        return OAuthTokens("access-first", "refresh-first", 3600)

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        self.refresh_calls += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        return OAuthTokens("access-second", "refresh-second", 3600)

    async def revoke_token(self, token: str) -> None:
        self.revoked.append(token)


def _me_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer access-first"
    return httpx.Response(200, json={"id": "424242", "email": "me@example.com"})


def _stub_client(provider, handler):
    from app.integrations.hh.client import HHApplicantClient

    return HHApplicantClient(provider, transport=httpx.MockTransport(handler))


@pytest.fixture
def hh_env(monkeypatch):
    monkeypatch.setattr(
        settings, "hh_credentials_key", Fernet.generate_key().decode(), raising=False
    )
    monkeypatch.setattr(settings, "hh_oauth_client_id", "test-app", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_client_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_redirect_uri", "http://cb", raising=False)

    import app.integrations.hh.accounts as accounts_module

    monkeypatch.setattr(
        accounts_module,
        "HHApplicantClient",
        lambda provider, **kwargs: _stub_client(provider, _me_handler),
    )


def _service(session, oauth: FakeOAuthClient) -> HHAccountService:
    return HHAccountService(session, oauth_client=oauth, state_store=InMemoryStateStore())


async def _start_and_callback(session, oauth, user_id):
    service = _service(session, oauth)
    url = await service.build_authorization_url(user_id)
    state = parse_qs(urlparse(url).query)["state"][0]
    return await service.handle_callback("auth-code", state)


def _state_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


# -- connect flow -------------------------------------------------------------


async def test_connect_stores_encrypted_tokens(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    user_id = uuid4()
    account = await _start_and_callback(db_session, oauth, user_id)
    await db_session.commit()

    assert account.hh_user_id == "424242"
    assert account.status == HHAccountStatus.CONNECTED
    # Ciphertexts at rest, plaintext never stored
    assert account.access_token_encrypted != "access-first"
    assert "access-first" not in account.access_token_encrypted
    cipher = CredentialCipher(settings.hh_credentials_key)
    assert cipher.decrypt(account.access_token_encrypted) == "access-first"
    assert cipher.decrypt(account.refresh_token_encrypted) == "refresh-first"
    assert account.access_token_expires_at > datetime.now(UTC)
    assert account.last_verified_at is not None


async def test_reconnect_updates_same_account(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    user_id = uuid4()
    first = await _start_and_callback(db_session, oauth, user_id)
    second = await _start_and_callback(db_session, oauth, user_id)
    await db_session.commit()
    assert first.id == second.id
    assert oauth.exchange_calls == 2


async def test_state_is_one_time(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    service = _service(db_session, oauth)
    url = await service.build_authorization_url(uuid4())
    state = _state_of(url)

    await service.handle_callback("auth-code", state)
    with pytest.raises(HHStateError):
        await service.handle_callback("auth-code", state)  # replay


async def test_tampered_state_rejected(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    service = _service(db_session, oauth)
    url = await service.build_authorization_url(uuid4())
    with pytest.raises(HHStateError):
        await service.handle_callback("auth-code", _state_of(url) + "x")


async def test_me_failure_blocks_storage(db_session, hh_env, monkeypatch, cleanup_db):
    user_id = uuid4()

    async def forbidden(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    import app.integrations.hh.accounts as accounts_module

    monkeypatch.setattr(
        accounts_module,
        "HHApplicantClient",
        lambda provider, **kwargs: _stub_client(provider, forbidden),
    )
    oauth = FakeOAuthClient()
    service = _service(db_session, oauth)
    url = await service.build_authorization_url(user_id)
    # 403 from /me maps to a permanent error; either way the token pair
    # must NOT be persisted without a verified identity.
    with pytest.raises(HHIntegrationError):
        await service.handle_callback("auth-code", _state_of(url))
    await db_session.commit()
    assert await service.repo.get_by_user(user_id) is None
    assert await service.repo.get_by_hh_user("424242") is None


# -- status / disconnect -------------------------------------------------------


async def test_status_and_disconnect(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    user_id = uuid4()
    service = _service(db_session, oauth)

    assert await service.get_status(user_id) is None  # never connected

    await _start_and_callback(db_session, oauth, user_id)
    await db_session.commit()

    account_status = await service.get_status(user_id)
    assert account_status is not None
    assert account_status["connected"] is True
    assert account_status["hh_user_id"] == "424242"
    assert "access_token" not in json.dumps(account_status, default=str)

    await service.disconnect(user_id)
    await db_session.commit()
    assert await service.get_status(user_id) is None
    assert oauth.revoked == ["access-first"]
    assert await HHAccountService(db_session).get_status(user_id) is None


# -- token management ----------------------------------------------------------


async def test_token_requires_connection(db_session, hh_env, cleanup_db):
    service = _service(db_session, FakeOAuthClient())
    with pytest.raises(HHAuthRequiredError):
        await service.get_valid_access_token(uuid4())


async def test_fresh_token_skips_refresh(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    user_id = uuid4()
    await _start_and_callback(db_session, oauth, user_id)
    await db_session.commit()

    service = _service(db_session, oauth)
    token = await service.get_valid_access_token(user_id)
    assert token == "access-first"
    assert oauth.refresh_calls == 0  # still fresh: no remote call


async def test_expired_token_refreshes_once(db_session, hh_env, cleanup_db):
    oauth = FakeOAuthClient()
    user_id = uuid4()
    account = await _start_and_callback(db_session, oauth, user_id)
    account.access_token_expires_at = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()

    service = _service(db_session, oauth)
    token = await service.get_valid_access_token(user_id)
    await db_session.commit()

    assert token == "access-second"
    assert oauth.refresh_calls == 1
    cipher = CredentialCipher(settings.hh_credentials_key)
    assert cipher.decrypt(account.access_token_encrypted) == "access-second"
    # Second call is served from the fresh token: no further refresh
    assert await service.get_valid_access_token(user_id) == "access-second"
    assert oauth.refresh_calls == 1


async def test_expired_token_refresh_uses_distributed_lock(
    db_session, hh_env, cleanup_db
):
    class RecordingLock:
        def __init__(self):
            self.acquired = []
            self.released = []

        async def acquire(self, key, owner, ttl_seconds):
            self.acquired.append((key, owner, ttl_seconds))
            return True

        async def release(self, key, owner):
            self.released.append((key, owner))

    oauth = FakeOAuthClient()
    user_id = uuid4()
    account = await _start_and_callback(db_session, oauth, user_id)
    account.access_token_expires_at = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()

    lock = RecordingLock()
    service = HHAccountService(
        db_session,
        oauth_client=oauth,
        lock_backend=lock,
        state_store=InMemoryStateStore(),
    )

    assert await service.get_valid_access_token(user_id) == "access-second"
    assert oauth.refresh_calls == 1
    assert len(lock.acquired) == 1
    assert lock.acquired[0][0] == f"hh-account-refresh:{account.id}"
    assert lock.released == [(lock.acquired[0][0], lock.acquired[0][1])]


async def test_expired_token_refresh_lock_contention_blocks_remote_call(
    db_session, hh_env, cleanup_db
):
    class DenyingLock:
        async def acquire(self, key, owner, ttl_seconds):
            return False

        async def release(self, key, owner):
            raise AssertionError("release must not be called when acquire failed")

    oauth = FakeOAuthClient()
    user_id = uuid4()
    account = await _start_and_callback(db_session, oauth, user_id)
    account.access_token_expires_at = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()

    service = HHAccountService(
        db_session,
        oauth_client=oauth,
        lock_backend=DenyingLock(),
        state_store=InMemoryStateStore(),
    )

    with pytest.raises(HHAuthRequiredError, match="refresh is already in progress"):
        await service.get_valid_access_token(user_id)
    assert oauth.refresh_calls == 0


async def test_dead_grant_marks_reauth_required(db_session, hh_env, cleanup_db):

    dead = HHOAuthError("HH OAuth error 400: invalid_grant", requires_reauth=True)
    oauth = FakeOAuthClient(refresh_error=dead)
    user_id = uuid4()
    account = await _start_and_callback(db_session, oauth, user_id)
    account.access_token_expires_at = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()

    service = _service(db_session, oauth)
    with pytest.raises(HHAuthRequiredError):
        await service.get_valid_access_token(user_id)
    await db_session.commit()

    refreshed = await service.get_status(user_id)
    assert refreshed is not None
    assert refreshed["status"] == HHAccountStatus.REAUTH_REQUIRED
    assert refreshed["connected"] is False
    # Status guard: no token for an account that needs re-auth
    with pytest.raises(HHAuthRequiredError):
        await service.get_valid_access_token(user_id)
