"""Tests for HH background sync workers and observability (ADR-001 M6)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core import metrics
from app.integrations.hh.crypto import CredentialCipher
from app.integrations.hh.exceptions import HHAuthRequiredError, HHTransientError
from app.models.hh import HHAccount, HHAccountStatus
from app.repositories.hh import HHAccountRepository
from app.workers.tasks import hh_sync as hh_sync_tasks


async def _account(session, user_id, *, status=HHAccountStatus.CONNECTED):
    cipher = CredentialCipher("".join(["Z"] * 43) + "=")
    account = HHAccount(
        user_id=user_id,
        hh_user_id=f"hh-{uuid4().hex[:8]}",
        host="hh.ru",
        status=status,
        access_token_encrypted=cipher.encrypt("access"),
        refresh_token_encrypted=cipher.encrypt("refresh"),
        access_token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        scopes=[],
    )
    session.add(account)
    await session.flush()
    return account


async def _clean_hh_tables(session) -> None:
    await session.execute(
        text("TRUNCATE TABLE hh_apply_attempts, hh_negotiations, hh_resumes, hh_accounts CASCADE;")
    )
    await session.commit()


async def test_account_repo_lists_connected_only(db_session, cleanup_db):
    await _clean_hh_tables(db_session)
    connected = await _account(db_session, uuid4())
    disconnected = await _account(db_session, uuid4(), status=HHAccountStatus.REAUTH_REQUIRED)
    await db_session.commit()

    rows = await HHAccountRepository(db_session).list_connected(limit=10)
    ids = {r.id for r in rows}

    assert connected.id in ids
    assert disconnected.id not in ids


async def test_sync_all_connected_accounts_summarizes_and_records_metrics(
    db_session, monkeypatch, cleanup_db
):
    await _clean_hh_tables(db_session)
    users = [uuid4(), uuid4(), uuid4()]
    for user_id in users:
        await _account(db_session, user_id)
    await db_session.commit()

    seen = []

    class FakeAccountService:
        def __init__(self, session):
            self.repo = HHAccountRepository(session)

        async def sync_all(self, user_id):
            seen.append(user_id)
            if user_id == users[1]:
                raise HHTransientError("api 503")
            if user_id == users[2]:
                raise HHAuthRequiredError("reauth")
            return {
                "resumes": type("R", (), {"as_dict": lambda self: {"fetched": 1, "upserted": 1, "skipped": 0}})(),
                "negotiations": type("N", (), {"as_dict": lambda self: {"fetched": 2, "upserted": 1, "skipped": 1}})(),
            }

    monkeypatch.setattr(hh_sync_tasks, "HHAccountService", FakeAccountService)
    labels_success = {"operation": "sync_all", "status": "success"}
    labels_transient = {"operation": "sync_all", "status": "transient_error"}
    labels_reauth = {"operation": "sync_all", "status": "reauth_required"}
    before_success = metrics._sample_value("autohh_hh_sync_total", labels_success) or 0
    before_transient = metrics._sample_value("autohh_hh_sync_total", labels_transient) or 0
    before_reauth = metrics._sample_value("autohh_hh_sync_total", labels_reauth) or 0

    result = await hh_sync_tasks._sync_all_hh_accounts_async(limit=10)

    assert result["status"] == "success"
    assert result["accounts_scanned"] == 3
    assert result["success"] == 1
    assert result["transient_error"] == 1
    assert result["reauth_required"] == 1
    assert seen == users
    assert metrics._sample_value("autohh_hh_sync_total", labels_success) == before_success + 1
    assert metrics._sample_value("autohh_hh_sync_total", labels_transient) == before_transient + 1
    assert metrics._sample_value("autohh_hh_sync_total", labels_reauth) == before_reauth + 1


def test_hh_sync_celery_task_policy_and_schedule():
    assert HHTransientError in hh_sync_tasks.sync_hh_account.autoretry_for
    assert HHAuthRequiredError not in hh_sync_tasks.sync_hh_account.autoretry_for
    assert hh_sync_tasks.sync_hh_account.max_retries == 3

    from app.workers.schedulers import celery_app

    assert "hh-sync-periodic" in celery_app.conf.beat_schedule
    assert celery_app.conf.beat_schedule["hh-sync-periodic"]["task"] == "sync_all_hh_accounts"
