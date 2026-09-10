"""Unit tests for the HH integration primitives (ADR-001): PKCE, state and
the encrypted-credential primitive. Fully hermetic."""

import base64
import hashlib
import uuid as uuidlib

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.integrations.hh.crypto import CredentialCipher
from app.integrations.hh.exceptions import (
    HHCryptoError,
    HHOAuthError,
    HHStateError,
    HHTransientError,
)
from app.integrations.hh.oauth import HHOAuthClient, generate_pkce_pair
from app.integrations.hh.state import InMemoryStateStore, OAuthStateSigner

# -- PKCE ------------------------------------------------------------------


def test_pkce_pair_follows_rfc7636_s256():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) == 64
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    assert challenge == expected
    verifier2, _ = generate_pkce_pair()
    assert verifier2 != verifier  # unique per flow


# -- state ------------------------------------------------------------------


def test_state_roundtrip_binds_user():
    signer = OAuthStateSigner()
    user_id = uuidlib.uuid4()
    state = signer.issue(user_id)
    payload = signer.verify(state)
    assert payload["user_id"] == str(user_id)
    assert "nonce" in payload


def test_state_rejects_tampering():
    signer = OAuthStateSigner()
    state = signer.issue(uuidlib.uuid4())
    raw, sig = state.split(".", 1)
    with pytest.raises(HHStateError):
        signer.verify(f"{raw[:-2]}xy.{sig}")
    with pytest.raises(HHStateError):
        signer.verify(f"{raw}.{'0' * len(sig)}")


def test_state_rejects_expired(monkeypatch):
    signer = OAuthStateSigner(ttl_seconds=10)
    state = signer.issue(uuidlib.uuid4())

    import time as time_mod

    real_time = time_mod.time
    monkeypatch.setattr(time_mod, "time", lambda: real_time() + 60)
    with pytest.raises(HHStateError):
        signer.verify(state)


def test_in_memory_state_store_is_one_time():
    import asyncio

    store = InMemoryStateStore()

    async def scenario():
        await store.put("nonce", "value", 60)
        assert await store.pop("nonce") == "value"
        assert await store.pop("nonce") is None  # replay blocked

    asyncio.run(scenario())


# -- credential cipher --------------------------------------------------------


def _fernet_key() -> str:
    return Fernet.generate_key().decode()


def test_cipher_roundtrip():
    cipher = CredentialCipher(_fernet_key())
    token = "hh-access-token-123"
    ciphertext = cipher.encrypt(token)
    assert ciphertext != token
    assert token not in ciphertext
    assert cipher.decrypt(ciphertext) == token


def test_cipher_rejects_wrong_key():
    ciphertext = CredentialCipher(_fernet_key()).encrypt("secret")
    other = CredentialCipher(_fernet_key())
    with pytest.raises(HHCryptoError):
        other.decrypt(ciphertext)


def test_cipher_fails_closed_without_key():
    with pytest.raises(HHCryptoError, match="HH_CREDENTIALS_KEY"):
        CredentialCipher(None)
    with pytest.raises(HHCryptoError):
        CredentialCipher("not-a-fernet-key")
    cipher = CredentialCipher(_fernet_key())
    with pytest.raises(HHCryptoError):
        cipher.encrypt("")


# -- OAuth client ---------------------------------------------------------------


def _oauth_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.fixture
def oauth_env(monkeypatch):
    monkeypatch.setattr(settings, "hh_oauth_client_id", "app-id", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_client_secret", "app-secret", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_redirect_uri", "http://cb", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_use_pkce", False, raising=False)


def test_oauth_builds_authorize_url(oauth_env):
    client = HHOAuthClient()
    url = client.build_authorization_url(state="s1")
    assert "hh.ru/oauth/authorize" in url
    assert "client_id=app-id" in url
    assert "state=s1" in url


def test_oauth_url_requires_configuration():
    client = HHOAuthClient()
    with pytest.raises(HHOAuthError):
        client.build_authorization_url(state="s1")


async def test_oauth_exchange_success(oauth_env):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/oauth/token"
        form = request.read().decode()
        assert "grant_type=authorization_code" in form
        return httpx.Response(
            200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        )

    client = HHOAuthClient(transport=_oauth_transport(handler))
    tokens = await client._token_request({"grant_type": "authorization_code"})
    assert tokens.access_token == "at"
    assert tokens.expires_in == 3600


async def test_oauth_invalid_grant_requires_reauth(oauth_env):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = HHOAuthClient(transport=_oauth_transport(handler))
    with pytest.raises(HHOAuthError, match="invalid_grant") as exc_info:
        await client._token_request({"grant_type": "refresh_token"})
    assert exc_info.value.requires_reauth is True


async def test_oauth_transient_429_then_success(oauth_env):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "temporarily_unavailable"})
        return httpx.Response(
            200, json={"access_token": "at", "refresh_token": "rt", "expires_in": 10}
        )

    client = HHOAuthClient(transport=_oauth_transport(handler), backoff_base=0.001)
    tokens = await client._token_request({"grant_type": "refresh_token"})
    assert tokens.access_token == "at"
    assert calls["n"] == 2


async def test_oauth_transient_5xx_exhaustion(oauth_env):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"error": "bad_gateway"})

    client = HHOAuthClient(transport=_oauth_transport(handler), backoff_base=0.001)
    with pytest.raises(HHTransientError):
        await client._token_request({"grant_type": "refresh_token"})
