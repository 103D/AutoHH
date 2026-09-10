"""Integration tests for explicit HH apply (ADR-001 milestone 5).

Covered contract:
- explicit user action, owner-scoped: the resume must be a synced snapshot of
  the caller's own connected account;
- idempotency guard on (account, remote_resume, remote_vacancy): a second call
  makes no additional remote POST and returns the stored outcome;
- audit: every attempt persists a durable row with outcome/remote id/error;
- remote ``already_applied`` is an idempotent success, not an error;
- transient remote failures mark the attempt FAILED and allow a later retry;
- an orphaned IN_PROGRESS guard (crashed worker) becomes retryable, a live
  one is a 409 conflict;
- local Application workflow is never created or mutated by apply.
"""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from app.api.v1 import hh as hh_api
from app.core.config import settings
from app.core.exceptions import DuplicateError, NotFoundError, ValidationError
from app.integrations.hh.accounts import HHAccountService
from app.integrations.hh.apply import ApplyResult, HHApplyService
from app.integrations.hh.exceptions import (
    HHAuthRequiredError,
    HHPermissionError,
    HHTransientError,
)
from app.integrations.hh.state import InMemoryStateStore
from app.models.hh import HHApplyAttempt, HHApplyAttemptStatus
from app.repositories.hh import HHApplyAttemptRepository, HHNegotiationRepository
from app.schemas.hh import HHApplyRequest


def _resume_item(resume_id="res-1", title="Data Analyst"):
    return {"id": resume_id, "title": title, "status": {"id": "published"}}


def _negotiation(item_id, resume_id="res-1", vacancy_id="vac-9"):
    return {
        "id": item_id,
        "state": {"id": "response", "name": "Response"},
        "vacancy": {"id": vacancy_id, "name": "Backend Dev"},
        "resume": {"id": resume_id},
        "created_at": "2026-08-01T09:00:00+0300",
        "updated_at": "2026-09-02T09:00:00+0300",
    }


class ScriptedApplyApi:
    """Scripted api.hh.ru surface for apply tests (MockTransport)."""

    def __init__(self, *, post_responses=None, negotiation_pages=None, resumes=(),
                 me_id="424242"):
        self.post_responses = list(post_responses or [])
        self.negotiation_pages = list(negotiation_pages or [])
        self.resumes_payload = {"items": list(resumes)}
        self.me_id = me_id
        self.page = 0
        self.posts = 0
        self.last_form: dict[str, list[str]] = {}
        self.bearers: list[str | None] = []

    def transport(self) -> httpx.MockTransport:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.bearers.append(request.headers.get("Authorization"))
            path = request.url.path
            if path == "/me":
                return httpx.Response(200, json={"id": self.me_id})
            if path == "/resumes/mine":
                return httpx.Response(200, json=self.resumes_payload)
            if path == "/negotiations" and request.method == "POST":
                self.posts += 1
                self.last_form = parse_qs(request.content.decode())
                if self.post_responses:
                    status, body = self.post_responses.pop(0)
                    return httpx.Response(status, json=body)
                return httpx.Response(201, json={"id": "neg-new"})
            if path == "/negotiations":
                if self.page >= len(self.negotiation_pages):
                    return httpx.Response(200, json={"items": [], "pages": 1, "page": 0})
                payload = self.negotiation_pages[self.page]
                self.page += 1
                return httpx.Response(200, json=payload)
            return httpx.Response(404, json={})

        return httpx.MockTransport(handler)


def _stub_accounts_client(monkeypatch, api: ScriptedApplyApi):
    import app.integrations.hh.accounts as accounts_module
    from app.integrations.hh.client import HHApplicantClient

    monkeypatch.setattr(
        accounts_module,
        "HHApplicantClient",
        lambda provider, **kwargs: HHApplicantClient(provider, transport=api.transport()),
    )


@pytest.fixture
def hh_env(monkeypatch):
    monkeypatch.setattr(
        settings, "hh_credentials_key", Fernet.generate_key().decode(), raising=False
    )
    monkeypatch.setattr(settings, "hh_oauth_client_id", "test-app", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_client_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_redirect_uri", "http://cb", raising=False)


class FakeOAuthClient:
    def build_authorization_url(self, *, state, code_challenge=None) -> str:
        return f"https://hh.ru/oauth/authorize?state={state}"

    async def exchange_code(self, code, *, code_verifier=None):
        from app.integrations.hh.oauth import OAuthTokens

        return OAuthTokens("access-first", "refresh-first", 3600)

    async def refresh_tokens(self, refresh_token):
        from app.integrations.hh.oauth import OAuthTokens

        return OAuthTokens("access-second", "refresh-second", 3600)

    async def revoke_token(self, token: str) -> None:
        return None


async def _connect_with_resumes(db_session, monkeypatch, user_id, resumes, me_id=None):
    api = ScriptedApplyApi(
        resumes=[_resume_item(r) for r in resumes], me_id=me_id or str(user_id.int % 10**9)
    )
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(
        db_session, oauth_client=FakeOAuthClient(), state_store=InMemoryStateStore()
    )
    url = await service.build_authorization_url(user_id)
    state = parse_qs(urlparse(url).query)["state"][0]
    await service.handle_callback("auth-code", state)
    await service.sync_resumes(user_id)
    await db_session.commit()


def _apply_service(db_session, monkeypatch, api: ScriptedApplyApi) -> HHApplyService:
    _stub_accounts_client(monkeypatch, api)
    accounts = HHAccountService(db_session, state_store=InMemoryStateStore())
    return HHApplyService(db_session, account_service=accounts)
async def test_apply_success_posts_once_and_audits(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    api = ScriptedApplyApi(
        negotiation_pages=[{"items": [_negotiation("neg-new")], "pages": 1, "page": 0}]
    )
    service = _apply_service(db_session, monkeypatch, api)

    result = await service.apply(user_id, "res-1", "vac-9", "Hello!")
    await db_session.commit()

    assert result.applied is True and result.duplicate is False
    assert result.remote_negotiation_id == "neg-new"
    assert api.posts == 1
    assert api.last_form == {
        "resume_id": ["res-1"],
        "vacancy_id": ["vac-9"],
        "message": ["Hello!"],
    }
    assert all(b == "Bearer access-first" for b in api.bearers)

    accounts = HHAccountService(db_session, state_store=InMemoryStateStore())
    account = await accounts.repo.get_by_user(user_id)
    attempt = await HHApplyAttemptRepository(db_session).get_by_tuple(
        account.id, "res-1", "vac-9"
    )
    assert attempt is not None
    assert attempt.status == HHApplyAttemptStatus.SUCCEEDED
    assert attempt.remote_negotiation_id == "neg-new"

    negotiations = await HHNegotiationRepository(db_session).list_for_account(account.id)
    assert {n.remote_negotiation_id for n in negotiations} == {"neg-new"}
    assert negotiations[0].job_id is None and negotiations[0].application_id is None


async def test_apply_is_idempotent_without_second_post(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    api = ScriptedApplyApi(
        negotiation_pages=[{"items": [_negotiation("neg-new")], "pages": 1, "page": 0}]
    )
    service = _apply_service(db_session, monkeypatch, api)
    first = await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()
    assert api.posts == 1

    second = await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()

    assert api.posts == 1
    assert second.applied is True and second.duplicate is True
    assert second.remote_negotiation_id == first.remote_negotiation_id == "neg-new"


async def test_apply_remote_duplicate_is_idempotent_success(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    api = ScriptedApplyApi(
        post_responses=[
            (403, {"errors": [{"value": "vacancy_id", "message": "already_applied"}]})
        ],
        negotiation_pages=[
            {"items": [_negotiation("neg-remote")], "pages": 1, "page": 0}
        ],
    )
    service = _apply_service(db_session, monkeypatch, api)

    result = await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()

    assert result.applied is True and result.duplicate is True
    assert result.remote_negotiation_id == "neg-remote"
    assert api.posts == 1

    again = await service.apply(user_id, "res-1", "vac-9")
    assert api.posts == 1
    assert again.duplicate is True


async def test_apply_transient_failure_marks_failed_and_retry_succeeds(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    api = ScriptedApplyApi(
        post_responses=[(503, {"error": "unavailable"})] * 4,
        negotiation_pages=[{"items": [_negotiation("neg-new")], "pages": 1, "page": 0}],
    )
    service = _apply_service(db_session, monkeypatch, api)

    with pytest.raises(HHTransientError):
        await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()
    assert api.posts >= 1

    accounts = HHAccountService(db_session, state_store=InMemoryStateStore())
    account = await accounts.repo.get_by_user(user_id)
    attempt = await HHApplyAttemptRepository(db_session).get_by_tuple(
        account.id, "res-1", "vac-9"
    )
    assert attempt.status == HHApplyAttemptStatus.FAILED
    assert attempt.error

    posts_before_retry = api.posts
    result = await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()
    assert api.posts == posts_before_retry + 1
    assert result.applied is True and result.duplicate is False
    await db_session.refresh(attempt)
    assert attempt.status == HHApplyAttemptStatus.SUCCEEDED

async def test_apply_in_progress_is_conflict(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    accounts = HHAccountService(db_session, state_store=InMemoryStateStore())
    account = await accounts.repo.get_by_user(user_id)
    db_session.add(
        HHApplyAttempt(
            hh_account_id=account.id,
            remote_resume_id="res-1",
            remote_vacancy_id="vac-9",
            status=HHApplyAttemptStatus.IN_PROGRESS,
        )
    )
    await db_session.commit()

    api = ScriptedApplyApi()
    service = _apply_service(db_session, monkeypatch, api)
    with pytest.raises(DuplicateError, match="already in progress"):
        await service.apply(user_id, "res-1", "vac-9")
    assert api.posts == 0


async def test_apply_stale_in_progress_guard_is_retryable(
    db_session, hh_env, monkeypatch, cleanup_db
):
    import app.integrations.hh.apply as apply_module

    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    accounts = HHAccountService(db_session, state_store=InMemoryStateStore())
    account = await accounts.repo.get_by_user(user_id)
    db_session.add(
        HHApplyAttempt(
            hh_account_id=account.id,
            remote_resume_id="res-1",
            remote_vacancy_id="vac-9",
            status=HHApplyAttemptStatus.IN_PROGRESS,
        )
    )
    await db_session.commit()

    monkeypatch.setattr(apply_module, "STALE_IN_PROGRESS_SECONDS", -1)
    api = ScriptedApplyApi(
        negotiation_pages=[{"items": [_negotiation("neg-new")], "pages": 1, "page": 0}]
    )
    service = _apply_service(db_session, monkeypatch, api)
    result = await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()

    assert result.applied is True and api.posts == 1


async def test_apply_unknown_or_foreign_resume_is_not_found(
    db_session, hh_env, monkeypatch, cleanup_db
):
    owner_id = uuid4()
    stranger_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, owner_id, ["res-1"])
    await _connect_with_resumes(db_session, monkeypatch, stranger_id, ["res-2"])

    api = ScriptedApplyApi()
    service = _apply_service(db_session, monkeypatch, api)

    with pytest.raises(NotFoundError, match="not found"):
        await service.apply(owner_id, "res-unknown", "vac-9")
    with pytest.raises(NotFoundError, match="not found"):
        await service.apply(stranger_id, "res-1", "vac-9")
    assert api.posts == 0


async def test_apply_blank_ids_are_rejected_without_remote_call(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    api = ScriptedApplyApi()
    service = _apply_service(db_session, monkeypatch, api)
    with pytest.raises(ValidationError):
        await service.apply(user_id, "  ", "vac-9")
    assert api.posts == 0


async def test_apply_without_connected_account(
    db_session, hh_env, monkeypatch, cleanup_db
):
    api = ScriptedApplyApi()
    service = _apply_service(db_session, monkeypatch, api)
    with pytest.raises(HHAuthRequiredError):
        await service.apply(uuid4(), "res-1", "vac-9")
    assert api.posts == 0


async def test_apply_permission_error_propagates_and_is_audited(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect_with_resumes(db_session, monkeypatch, user_id, ["res-1"])

    api = ScriptedApplyApi(post_responses=[(403, {"error": "forbidden"})])
    service = _apply_service(db_session, monkeypatch, api)
    with pytest.raises(HHPermissionError):
        await service.apply(user_id, "res-1", "vac-9")
    await db_session.commit()
    assert api.posts == 1

    accounts = HHAccountService(db_session, state_store=InMemoryStateStore())
    account = await accounts.repo.get_by_user(user_id)
    attempt = await HHApplyAttemptRepository(db_session).get_by_tuple(
        account.id, "res-1", "vac-9"
    )
    assert attempt.status == HHApplyAttemptStatus.FAILED


def _patch_apply_service(monkeypatch, *, result=None, exc=None):
    class FakeApplyService:
        def __init__(self, session):
            pass

        async def apply(self, *args, **kwargs):
            if exc is not None:
                raise exc
            return result

    monkeypatch.setattr(hh_api, "HHApplyService", FakeApplyService)


async def test_apply_endpoint_success_shape(monkeypatch):
    _patch_apply_service(
        monkeypatch,
        result=ApplyResult(
            applied=True, duplicate=False, remote_negotiation_id="neg-1"
        ),
    )
    response = await hh_api.apply_to_vacancy(
        HHApplyRequest(remote_resume_id="res-1", remote_vacancy_id="vac-9"),
        uuid4(),
        object(),
    )
    assert response.applied is True and response.duplicate is False
    assert response.remote_negotiation_id == "neg-1"


async def test_apply_endpoint_error_mapping(monkeypatch):
    from fastapi import HTTPException

    cases = [
        (HHAuthRequiredError("no account"), 409),
        (NotFoundError("missing"), 404),
        (DuplicateError("in progress"), 409),
        (ValidationError("blank"), 422),
        (HHPermissionError("denied"), 422),
        (HHTransientError("down"), 502),
    ]
    for exc, expected_status in cases:
        _patch_apply_service(monkeypatch, exc=exc)
        with pytest.raises(HTTPException) as error:
            await hh_api.apply_to_vacancy(
                HHApplyRequest(remote_resume_id="res-1", remote_vacancy_id="vac-9"),
                uuid4(),
                object(),
            )
        assert error.value.status_code == expected_status

