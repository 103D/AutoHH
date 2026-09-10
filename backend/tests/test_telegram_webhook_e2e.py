"""E2E tests for the Telegram webhook inbound flow.

Runs over the real HTTP layer (ASGITransport) against the real test
database (same pattern as test_e2e_manual_pipeline.py). Hermeticity:
- the vacancy page download is stubbed with a JSON-LD fixture;
- the matching AI provider is mocked (deterministic, no network);
- the Telegram sendMessage adapter is stubbed to capture bot replies.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import telegram_inbound as ti_module
from app.services.telegram_inbound import HELP_TEXT
from app.services.telegram_v2 import TelegramDigestAdapter

pytestmark = pytest.mark.usefixtures("migrate_test_database")

JSONLD_HTML = """<html><head>
<script type="application/ld+json">
{"@type": "JobPosting",
 "title": "Senior Data Analyst",
 "hiringOrganization": {"@type": "Organization", "name": "Kaspi.kz"},
 "description": "<p>SQL dashboards and Python automation.</p>",
 "baseSalary": {"@type": "MonetaryAmount", "currency": "KZT",
                "value": {"minValue": 500000, "maxValue": 800000, "unitText": "KZT"}},
 "jobLocation": {"@type": "Place", "address": {"addressLocality": "Almaty"}},
 "identifier": {"@type": "PropertyValue", "name": "hh", "value": "e2e-777"}}
</script></head><body></body></html>"""

PROFILE_PAYLOAD = {
    "user_id": "00000000-0000-0000-0000-100000000001",
    "desired_positions": ["Data Analyst"],
    "skills": ["SQL", "Python", "Tableau"],
    "experience_years": 3,
    "experience_level": "middle",
    "languages": {"Russian": "native"},
    "location": "Almaty",
    "desired_salary_min": 400000,
    "desired_salary_max": 600000,
    "salary_currency": "KZT",
    "work_formats": ["remote", "hybrid"],
    "relocation_possible": False,
    "business_trips_acceptable": True,
}

VACANCY_URL = "https://hh.kz/vacancy/e2e-777"


@pytest.fixture
def mock_ai(monkeypatch):
    """Deterministic AI provider for matching: no network in E2E."""
    from unittest.mock import AsyncMock, MagicMock

    from app.providers.ai.base import MatchResult as AIMatchResult
    from app.providers.ai.base import SkillMatch

    ai_result = AIMatchResult(
        score=78,
        recommendation="APPLY",
        matched_skills=[SkillMatch(skill="SQL", match_type="exact", confidence=1.0)],
        missing_skills=["Cohort Analysis"],
        strong_matches=["SQL", "Python"],
        concerns=[],
        reasoning_summary="Strong SQL/Python match for an analyst role.",
        tokens_used=150,
        cost_usd=0.002,
    )
    provider = MagicMock()
    provider.name = "mock-ai"
    provider.analyze_job = AsyncMock(return_value=ai_result)
    monkeypatch.setattr(
        "app.services.matching.create_ai_provider", lambda *a, **k: provider
    )
    return provider


@pytest.fixture
def stub_page(monkeypatch):
    """Stub the vacancy page download for link imports."""
    from unittest.mock import AsyncMock

    mock = AsyncMock(return_value=JSONLD_HTML)
    monkeypatch.setattr(ti_module.TelegramInboundService, "_fetch_html", mock)
    return mock


@pytest.fixture
def sent_replies(monkeypatch):
    """Capture Telegram sendMessage calls instead of hitting the network."""
    calls: list[tuple[str, str]] = []

    async def _fake_send(self, chat_id, text, reply_markup=None, parse_mode=None):
        calls.append((str(chat_id), text))
        return "msg-1"

    monkeypatch.setattr(TelegramDigestAdapter, "send_message", _fake_send)
    return calls


def _message_update(text: str, chat_id: int = 111) -> dict:
    return {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text},
    }


async def _post_update(text: str, chat_id: int = 111, secret: str | None = None):
    headers = {}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            "/api/v1/telegram/webhook",
            json=_message_update(text, chat_id),
            headers=headers,
        )


@pytest.fixture
def no_secret(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.telegram_webhook_secret", None)
    monkeypatch.setattr("app.core.config.settings.telegram_chat_id", None)
    monkeypatch.setattr("app.core.config.settings.telegram_extra_chat_ids", None)


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret(monkeypatch, no_secret):
    monkeypatch.setattr(
        "app.core.config.settings.telegram_webhook_secret", "s3cret"
    )

    r = await _post_update("/help", secret="wrong")
    assert r.status_code == 403

    r = await _post_update("/help", secret="s3cret")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_webhook_ignores_unauthorized_chat(monkeypatch, no_secret, sent_replies):
    monkeypatch.setattr("app.core.config.settings.telegram_chat_id", "999")

    r = await _post_update("/help", chat_id=111)

    assert r.status_code == 200
    assert sent_replies == []  # message from a foreign chat is silently dropped


@pytest.mark.asyncio
async def test_webhook_help_message_replies_with_help(no_secret, sent_replies):
    r = await _post_update("/help")

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert sent_replies == [("111", HELP_TEXT)]


@pytest.mark.asyncio
async def test_webhook_link_import_and_score(
    cleanup_db, mock_ai, stub_page, no_secret, sent_replies
):
    """URL message -> JSON-LD import -> deterministic score -> bot reply."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/api/v1/profile/", json=PROFILE_PAYLOAD)
        assert r.status_code == 201, r.text

    r = await _post_update(VACANCY_URL)
    assert r.status_code == 200
    stub_page.assert_awaited_once_with(VACANCY_URL)

    assert len(sent_replies) == 1
    chat_id, reply = sent_replies[0]
    assert chat_id == "111"
    assert "📥 Вакансия импортирована" in reply
    assert "/100" in reply  # score line present
    assert VACANCY_URL in reply

    # The vacancy is persisted through the standard manual pipeline.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/jobs/", params={"source": "manual"})
        assert r.status_code == 200
        jobs = r.json()
        assert len(jobs) == 1
        assert jobs[0]["external_id"] == "e2e-777"
        assert jobs[0]["title"] == "Senior Data Analyst"

    # Resending the same link -> duplicate, still exactly one job.
    r = await _post_update(VACANCY_URL)
    assert r.status_code == 200
    assert len(sent_replies) == 2
    assert "♻️ Вакансия уже была в базе" in sent_replies[1][1]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/v1/jobs/", params={"source": "manual"})
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_webhook_link_without_profile_hints_resume(
    cleanup_db, mock_ai, stub_page, no_secret, sent_replies
):
    """No candidate profile -> the bot tells the user to send a resume first."""
    r = await _post_update(VACANCY_URL)

    assert r.status_code == 200
    assert len(sent_replies) == 1
    assert "сначала отправьте резюме" in sent_replies[0][1]
