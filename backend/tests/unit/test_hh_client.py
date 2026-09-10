"""Unit tests for HHApplicantClient error semantics (ADR-001):
401 -> refresh once and retry once; 403 permanent; 429/5xx transient with
bounded retries; malformed payload -> parse error; tokens never logged."""

import httpx
import pytest

from app.integrations.hh.client import HHApplicantClient
from app.integrations.hh.exceptions import (
    HHAlreadyAppliedError,
    HHApiError,
    HHAuthRequiredError,
    HHParseError,
    HHPermissionError,
    HHTransientError,
)


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _client(handler, *, token_calls: list[bool] | None = None, backoff: float = 0.001):
    async def provider(force_refresh: bool) -> str:
        if token_calls is not None:
            token_calls.append(force_refresh)
        return "token-abc"

    return HHApplicantClient(
        provider,
        transport=_transport(handler),
        backoff_base=backoff,
        user_agent="TestUA/1.0 (test@example.com)",
    )


async def test_me_success_with_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["ua"] = request.headers.get("User-Agent")
        return httpx.Response(200, json={"id": "424242", "email": "a@b.c"})

    me = await _client(handler).get_current_user()
    assert me["id"] == "424242"
    assert seen["auth"] == "Bearer token-abc"
    assert seen["ua"].startswith("TestUA/1.0")


async def test_401_refreshes_once_then_retries():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("Authorization"))
        if len(calls) == 1:
            return httpx.Response(401, json={"error": "token_expired"})
        return httpx.Response(200, json={"id": "1"})

    token_calls: list[bool] = []
    me = await _client(handler, token_calls=token_calls).get_current_user()
    assert me == {"id": "1"}
    assert calls[0] == "Bearer token-abc"
    assert calls[1] == "Bearer token-abc"  # refreshed value from provider
    assert token_calls == [False, True]  # second fetch forced the refresh


async def test_401_twice_raises_auth_required():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "token_expired"})

    with pytest.raises(HHAuthRequiredError):
        await _client(handler).get_current_user()


async def test_403_is_permanent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    with pytest.raises(HHPermissionError):
        await _client(handler).get_current_user()


async def test_400_is_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad_arguments"})

    with pytest.raises(HHApiError):
        await _client(handler).get_current_user()


async def test_429_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"errors": []})
        return httpx.Response(200, json={"items": []})

    result = await _client(handler).list_negotiations()
    assert result == {"items": []}
    assert calls["n"] == 2


async def test_5xx_exhaustion_is_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with pytest.raises(HHTransientError):
        await _client(handler).list_resumes()


async def test_non_json_payload_is_parse_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy error</html>")

    with pytest.raises(HHParseError):
        await _client(handler).get_current_user()


async def test_tokens_never_logged(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "token_expired"})

    import logging

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(HHAuthRequiredError):
            await _client(handler).get_current_user()

    assert "token-abc" not in caplog.text


async def test_apply_to_vacancy_posts_form_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return httpx.Response(201, json={"id": "neg-1"})

    result = await _client(handler).apply_to_vacancy(
        resume_id="res-1", vacancy_id="vac-9", message="Hello"
    )

    assert result == {"id": "neg-1"}
    assert seen["method"] == "POST"
    assert seen["path"] == "/negotiations"
    assert "resume_id=res-1" in seen["body"]
    assert "vacancy_id=vac-9" in seen["body"]
    assert "message=Hello" in seen["body"]


async def test_apply_to_vacancy_already_applied_is_specific_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"errors": [{"value": "vacancy_id", "message": "already_applied"}]},
        )

    with pytest.raises(HHAlreadyAppliedError):
        await _client(handler).apply_to_vacancy(
            resume_id="res-1", vacancy_id="vac-9"
        )
