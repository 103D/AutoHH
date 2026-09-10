"""Integration tests for read-only HH syncs (ADR-001 milestone 3):
idempotent upserts, content-hash change detection, quarantine of malformed
items, pagination, last_sync_at, and the ownership scoping."""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.integrations.hh.accounts import HHAccountService
from app.integrations.hh.exceptions import HHAuthRequiredError
from app.integrations.hh.state import InMemoryStateStore
from app.models.hh import HHAccountStatus
from app.repositories.hh import HHNegotiationRepository, HHResumeRepository

RESUME_A = {
    "id": "res-1",
    "title": "Data Analyst",
    "status": {"id": "published", "name": "Published"},
    "updated_at": "2026-09-01T12:00:00+0300",
}
RESUME_A_CHANGED = {**RESUME_A, "title": "Senior Data Analyst"}
RESUME_B = {"id": "res-2", "title": "Analyst", "status": {"id": "draft"}}


def _negotiation(item_id, state_name="Active", **extra):
    item = {
        "id": item_id,
        "state": {"id": "active", "name": state_name},
        "vacancy": {"id": "vac-9", "name": "Backend Dev"},
        "resume": {"id": "res-1"},
        "created_at": "2026-08-01T09:00:00+0300",
        "updated_at": "2026-09-02T09:00:00+0300",
    }
    item.update(extra)
    return item


class ScriptedHHApi:
    """Scripted api.hh.ru applicant endpoints served via MockTransport."""

    def __init__(self, *, resumes_payload=None, negotiation_pages=None):
        self.resumes_payload = resumes_payload
        self.negotiation_pages = negotiation_pages or []
        self.negotiation_page = 0
        self.bearers: list[str] = []

    def transport(self) -> httpx.MockTransport:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.bearers.append(request.headers.get("Authorization"))
            if request.url.path == "/me":
                assert request.headers["Authorization"] == "Bearer access-first"
                return httpx.Response(200, json={"id": "424242", "email": "me@example.com"})
            if request.url.path == "/resumes/mine":
                return httpx.Response(200, json=self.resumes_payload)
            if request.url.path == "/negotiations":
                page = self.negotiation_page
                self.negotiation_page += 1
                if page >= len(self.negotiation_pages):
                    return httpx.Response(
                        200, json={"items": [], "pages": 1, "page": 0}
                    )
                return httpx.Response(200, json=self.negotiation_pages[page])
            return httpx.Response(404, json={"error": "not_found"})

        return httpx.MockTransport(handler)


def _stub_accounts_client(monkeypatch, api: ScriptedHHApi):
    import app.integrations.hh.accounts as accounts_module

    monkeypatch.setattr(
        accounts_module,
        "HHApplicantClient",
        lambda provider, **kwargs: _build_client(provider, api),
    )


def _build_client(provider, api: ScriptedHHApi):
    from app.integrations.hh.client import HHApplicantClient

    return HHApplicantClient(provider, transport=api.transport())


@pytest.fixture
def hh_env(monkeypatch):
    monkeypatch.setattr(
        settings, "hh_credentials_key", Fernet.generate_key().decode(), raising=False
    )
    monkeypatch.setattr(settings, "hh_oauth_client_id", "test-app", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_client_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "hh_oauth_redirect_uri", "http://cb", raising=False)


class FakeOAuthClient:
    """Scripted OAuth endpoints for the connect step of these tests."""

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


async def _connect(db_session, monkeypatch, user_id):
    """Run the real connect flow against scripted OAuth + /me, then commit."""
    api = ScriptedHHApi(resumes_payload={"items": []})
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(
        db_session, oauth_client=FakeOAuthClient(), state_store=InMemoryStateStore()
    )
    url = await service.build_authorization_url(user_id)
    state = parse_qs(urlparse(url).query)["state"][0]
    await service.handle_callback("auth-code", state)
    await db_session.commit()
    return service


async def test_resumes_sync_idempotent_and_updates(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    api = ScriptedHHApi(resumes_payload={"items": [RESUME_A, RESUME_B]})
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())

    first = await service.sync_resumes(user_id)
    await db_session.commit()
    assert first.fetched == 2 and first.upserted == 2 and first.skipped == 0

    account = await service.repo.get_by_user(user_id)
    assert account.last_sync_at is not None

    # Idempotent: same payload -> nothing rewritten
    second = await service.sync_resumes(user_id)
    assert second.upserted == 0 and second.fetched == 2

    # Changed title + new item -> exactly two upserts
    new_item = {**RESUME_B, "id": "res-3"}
    api2 = ScriptedHHApi(resumes_payload={"items": [RESUME_A_CHANGED, RESUME_B, new_item]})
    _stub_accounts_client(monkeypatch, api2)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    third = await service.sync_resumes(user_id)
    await db_session.commit()
    assert third.upserted == 2

    repo = HHResumeRepository(db_session)
    rows = {r.remote_resume_id: r for r in await repo.list_for_account(account.id)}
    assert set(rows) == {"res-1", "res-2", "res-3"}
    assert rows["res-1"].title == "Senior Data Analyst"


async def test_resumes_sync_quarantines_malformed(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    api = ScriptedHHApi(
        resumes_payload={"items": [RESUME_A, {"no": "id"}, "garbage"]}
    )
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    result = await service.sync_resumes(user_id)
    await db_session.commit()

    assert (result.fetched, result.upserted, result.skipped) == (3, 1, 2)
    account = await service.repo.get_by_user(user_id)
    repo = HHResumeRepository(db_session)
    assert len(await repo.list_for_account(account.id)) == 1


async def test_negotiations_sync_and_state_change(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    api = ScriptedHHApi(
        negotiation_pages=[
            {
                "items": [_negotiation("n-1"), _negotiation("n-2", state_name="Interview")],
                "pages": 1,
                "page": 0,
            }
        ]
    )
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    result = await service.sync_negotiations(user_id)
    await db_session.commit()
    assert (result.fetched, result.upserted) == (2, 2)

    account = await service.repo.get_by_user(user_id)
    repo = HHNegotiationRepository(db_session)
    rows = {r.remote_negotiation_id: r for r in await repo.list_for_account(account.id)}
    assert rows["n-1"].remote_vacancy_id == "vac-9"
    assert rows["n-1"].remote_resume_id == "res-1"
    assert rows["n-2"].state_name == "Interview"

    # State change on n-1 -> exactly one upsert, new state persisted
    api2 = ScriptedHHApi(
        negotiation_pages=[
            {"items": [_negotiation("n-1", state_name="Discarded")], "pages": 1, "page": 0}
        ]
    )
    _stub_accounts_client(monkeypatch, api2)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    again = await service.sync_negotiations(user_id)
    await db_session.commit()
    assert again.upserted == 1 and again.fetched == 1
    rows = {r.remote_negotiation_id: r for r in await repo.list_for_account(account.id)}
    assert rows["n-1"].state_name == "Discarded"


async def test_negotiations_sync_follows_pagination(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    api = ScriptedHHApi(
        negotiation_pages=[
            {"items": [_negotiation("n-1")], "pages": 2, "page": 0},
            {"items": [_negotiation("n-2")], "pages": 2, "page": 1},
        ]
    )
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    result = await service.sync_negotiations(user_id)
    await db_session.commit()

    assert result.fetched == 2
    account = await service.repo.get_by_user(user_id)
    repo = HHNegotiationRepository(db_session)
    ids = {r.remote_negotiation_id for r in await repo.list_for_account(account.id)}
    assert ids == {"n-1", "n-2"}


async def test_negotiations_sync_quarantines_missing_state(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    api = ScriptedHHApi(
        negotiation_pages=[
            {"items": [{"id": "n-x"}, _negotiation("n-ok")], "pages": 1}
        ]
    )
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    result = await service.sync_negotiations(user_id)
    await db_session.commit()
    assert (result.fetched, result.upserted, result.skipped) == (2, 1, 1)


async def test_sync_requires_connected_account(db_session, hh_env, cleanup_db):
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    with pytest.raises(HHAuthRequiredError):
        await service.sync_resumes(uuid4())
    with pytest.raises(HHAuthRequiredError):
        await service.sync_negotiations(uuid4())
    with pytest.raises(HHAuthRequiredError):
        await service.sync_all(uuid4())


async def test_sync_uses_auto_refreshed_bearer(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    api = ScriptedHHApi(resumes_payload={"items": []})
    _stub_accounts_client(monkeypatch, api)
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    await service.sync_resumes(user_id)

    assert api.bearers
    assert all(b == "Bearer access-first" for b in api.bearers)


async def test_reauth_required_account_blocks_sync(
    db_session, hh_env, monkeypatch, cleanup_db
):
    user_id = uuid4()
    await _connect(db_session, monkeypatch, user_id)

    # Force the account into REAUTH_REQUIRED
    service = HHAccountService(db_session, state_store=InMemoryStateStore())
    account = await service.repo.get_by_user(user_id)
    await service.repo.mark_status(account, HHAccountStatus.REAUTH_REQUIRED)
    await db_session.commit()

    with pytest.raises(HHAuthRequiredError):
        await service.sync_resumes(user_id)
