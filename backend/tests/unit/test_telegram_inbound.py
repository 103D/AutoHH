"""Unit tests for the Telegram inbound flow (links, resumes, commands)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.services import telegram_inbound as ti
from app.services.telegram_inbound import (
    HELP_TEXT,
    RESUME_MIN_LENGTH,
    UNKNOWN_COMMAND_TEXT,
    TelegramInboundService,
    extract_job_payload,
    extract_url,
)

JSONLD_HTML = """<html><head>
<script type="application/ld+json">
{"@type": "JobPosting",
 "title": "Senior Data Analyst",
 "hiringOrganization": {"@type": "Organization", "name": "Kaspi.kz"},
 "description": "<p>SQL and Python.</p>",
 "datePosted": "2026-08-01",
 "baseSalary": {"@type": "MonetaryAmount", "currency": "KZT",
                "value": {"minValue": 500000, "maxValue": 800000, "unitText": "KZT"}},
 "jobLocation": {"@type": "Place", "address": {"addressLocality": "Almaty"}},
 "identifier": {"@type": "PropertyValue", "name": "hh", "value": "12345"}}
</script></head><body></body></html>"""

OG_HTML = """<html><head>
<meta property="og:title" content="Аналитик данных">
<meta property="og:description" content="Нужен SQL-аналитик">
<meta property="og:site_name" content="hh.kz">
<title>Вакансия — hh.kz</title>
</head><body>body</body></html>"""

EMPTY_HTML = "<html><head><title></title></head><body></body></html>"


def _service() -> TelegramInboundService:
    return TelegramInboundService(session=None)


class TestExtractUrl:
    def test_finds_url_and_strips_trailing_punctuation(self):
        assert (
            extract_url("глянь https://hh.kz/vacancy/1, интересно")
            == "https://hh.kz/vacancy/1"
        )

    def test_returns_first_url(self):
        assert (
            extract_url("a https://x.kz/1 b https://y.kz/2") == "https://x.kz/1"
        )

    def test_no_url(self):
        assert extract_url("просто текст") is None
        assert extract_url(None) is None


class TestExtractJobPayload:
    def test_jsonld_posting(self):
        raw = extract_job_payload(JSONLD_HTML, "https://hh.kz/vacancy/1")

        assert raw is not None
        assert raw.title == "Senior Data Analyst"
        assert raw.company == "Kaspi.kz"
        assert raw.description == "SQL and Python."
        assert raw.external_id == "12345"
        assert raw.url == "https://hh.kz/vacancy/1"
        assert raw.salary_min == 500000
        assert raw.salary_max == 800000
        assert raw.currency == "KZT"
        assert raw.location == "Almaty"
        assert raw.raw_data["import"] == "telegram_link"

    def test_opengraph_fallback(self):
        raw = extract_job_payload(OG_HTML, "https://hh.kz/vacancy/2")

        assert raw is not None
        assert raw.title == "Аналитик данных"
        assert raw.company == "hh.kz"
        assert raw.description == "Нужен SQL-аналитик"
        assert raw.external_id.startswith("url-")

    def test_unusable_page_returns_none(self):
        assert extract_job_payload(EMPTY_HTML, "https://example.com/x") is None
        assert extract_job_payload(None, "https://example.com/x") is None


class TestHandleMessageDispatch:
    @pytest.mark.asyncio
    async def test_help_and_start(self):
        service = _service()
        assert await service.handle_message("/help") == HELP_TEXT
        assert await service.handle_message("/start") == HELP_TEXT

    @pytest.mark.asyncio
    async def test_empty_message_returns_none(self):
        assert await _service().handle_message("   ") is None
        assert await _service().handle_message(None) is None

    @pytest.mark.asyncio
    async def test_score_command_with_argument(self):
        service = _service()
        service.handle_score_argument = AsyncMock(return_value="scored")
        assert await service.handle_message("/score https://hh.kz/v/1") == "scored"
        service.handle_score_argument.assert_awaited_once_with("https://hh.kz/v/1")

    @pytest.mark.asyncio
    async def test_score_command_strips_bot_suffix(self):
        service = _service()
        service.handle_score_argument = AsyncMock(return_value="scored")
        await service.handle_message("/score@myjobbot https://hh.kz/v/1")
        service.handle_score_argument.assert_awaited_once_with("https://hh.kz/v/1")

    @pytest.mark.asyncio
    async def test_train_command(self):
        service = _service()
        service.training_digest = AsyncMock(return_value="digest")
        assert await service.handle_message("/train") == "digest"

    @pytest.mark.asyncio
    async def test_resume_without_argument_prompts(self):
        service = _service()
        reply = await service.handle_message("/resume")
        assert "резюме" in reply

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        assert await _service().handle_message("/foo") == UNKNOWN_COMMAND_TEXT

    @pytest.mark.asyncio
    async def test_plain_url_goes_to_score(self):
        service = _service()
        service.handle_score_argument = AsyncMock(return_value="ok")
        await service.handle_message("https://hh.kz/vacancy/9")
        service.handle_score_argument.assert_awaited_once_with("https://hh.kz/vacancy/9")

    @pytest.mark.asyncio
    async def test_long_plain_text_goes_to_resume(self):
        service = _service()
        service.ingest_resume = AsyncMock(return_value="parsed")
        long_text = "Моё резюме. " * 30  # > RESUME_MIN_LENGTH
        assert len(long_text) >= RESUME_MIN_LENGTH
        assert await service.handle_message(long_text) == "parsed"

    @pytest.mark.asyncio
    async def test_short_plain_text_returns_help(self):
        assert await _service().handle_message("привет") == HELP_TEXT


class TestScoreFlow:
    @pytest.mark.asyncio
    async def test_url_import_created(self):
        service = _service()
        job = SimpleNamespace(id=uuid4())
        service.import_job_from_url = AsyncMock(return_value=(job, "created"))
        service._score_with_hints = AsyncMock(return_value="87/100")

        reply = await service.handle_score_argument("https://hh.kz/vacancy/1")

        assert reply.startswith("📥 Вакансия импортирована")
        assert "87/100" in reply
        service.import_job_from_url.assert_awaited_once_with("https://hh.kz/vacancy/1")

    @pytest.mark.asyncio
    async def test_url_import_duplicate(self):
        service = _service()
        job = SimpleNamespace(id=uuid4())
        service.import_job_from_url = AsyncMock(return_value=(job, "duplicate"))
        service._score_with_hints = AsyncMock(return_value="score")

        reply = await service.handle_score_argument("https://hh.kz/vacancy/1")
        assert reply.startswith("♻️ Вакансия уже была в базе")

    @pytest.mark.asyncio
    async def test_import_validation_error(self):
        service = _service()
        service.import_job_from_url = AsyncMock(
            side_effect=ValidationError("нет разметки")
        )
        reply = await service.handle_score_argument("https://example.com/job")
        assert "нет разметки" in reply

    @pytest.mark.asyncio
    async def test_import_http_error(self):
        service = _service()
        service.import_job_from_url = AsyncMock(side_effect=httpx.ConnectError("boom"))
        reply = await service.handle_score_argument("https://example.com/job")
        assert "Не удалось загрузить" in reply

    @pytest.mark.asyncio
    async def test_empty_argument(self):
        assert "Укажите ссылку" in await _service().handle_score_argument("")

    @pytest.mark.asyncio
    async def test_garbage_argument(self):
        assert "Не похоже" in await _service().handle_score_argument("опечатка")

    @pytest.mark.asyncio
    async def test_uuid_argument_scores_directly(self):
        service = _service()
        job_id = uuid4()
        service.score_job = AsyncMock(return_value="score text")

        reply = await service.handle_score_argument(str(job_id))

        assert reply == "score text"


class TestFormatScore:
    def _result(self, **overrides):
        data = {
            "score": 87,
            "recommendation": "DREAM_JOB",
            "strong_matches": ["SQL", "Python"],
            "missing_skills": ["Kafka"],
            "hard_failures": [],
            "reasoning_summary": "Отличное совпадение по стеку.",
        }
        data.update(overrides)
        return SimpleNamespace(**data)

    def _job(self, **overrides):
        data = {"title": "Senior Data Analyst", "url": "https://hh.kz/vacancy/1"}
        data.update(overrides)
        return SimpleNamespace(**data)

    def test_dream_job_formatting(self):
        text = TelegramInboundService.format_score(self._result(), self._job())

        assert "🔥 Senior Data Analyst — 87/100 · Работа мечты" in text
        assert "Сильные стороны: SQL, Python" in text
        assert "Чему подтянуться: Kafka" in text
        assert "Отличное совпадение по стеку." in text
        assert "https://hh.kz/vacancy/1" in text

    def test_not_eligible_shows_failures(self):
        result = self._result(
            recommendation="NOT_ELIGIBLE", hard_failures=["experience 10 > 4.5"]
        )
        text = TelegramInboundService.format_score(result, self._job())

        assert "⛔" in text
        assert "Не пройдено: experience 10 > 4.5" in text

    def test_unknown_category_falls_back(self):
        text = TelegramInboundService.format_score(
            self._result(recommendation="WEIRD"), self._job()
        )
        assert "WEIRD" in text


class TestIngestResume:
    @pytest.fixture
    def fake_parser(self, monkeypatch):
        """Replace ResumeParserService with a canned stub."""
        parsed = SimpleNamespace(full_name="Дияр М.", summary="Analyst")
        profile_data = {
            "desired_positions": ["Data Analyst"],
            "skills": ["SQL", "Python", "Power BI"],
            "experience_years": 3,
            "experience_level": "middle",
            "desired_salary_min": 400000,
            "desired_salary_max": 600000,
            "salary_currency": "KZT",
        }

        class _FakeParser:
            def __init__(self, ai_provider=None):
                pass

            async def parse(self, text):
                return parsed

            def to_profile_data(self, parsed_obj):
                return dict(profile_data)

        monkeypatch.setattr(ti, "ResumeParserService", _FakeParser)
        return parsed, profile_data

    @pytest.mark.asyncio
    async def test_short_text_hint(self):
        assert "слишком короткий" in await _service().ingest_resume("коротко")

    @pytest.mark.asyncio
    async def test_successful_ingest(self, fake_parser):
        service = _service()
        profile_id = uuid4()
        upsert = AsyncMock(return_value=(profile_id, True))
        service._upsert_profile = upsert

        resume_text = "Резюме " * 40
        reply = await service.ingest_resume(resume_text)

        assert "Профиль создан из резюме" in reply
        assert "Позиции: Data Analyst" in reply
        assert "Опыт: 3 лет (middle)" in reply
        assert "400000–600000 KZT" in reply
        assert f"ID профиля: {profile_id}" in reply
        args = upsert.await_args.args
        assert args[1] == resume_text
        assert args[2].startswith("telegram_")

    @pytest.mark.asyncio
    async def test_parser_validation_error(self, monkeypatch):
        class _BadParser:
            def __init__(self, ai_provider=None):
                pass

            async def parse(self, text):
                raise ValidationError("no skills")

            def to_profile_data(self, parsed):
                return {}

        monkeypatch.setattr(ti, "ResumeParserService", _BadParser)
        reply = await _service().ingest_resume("Резюме " * 40)
        assert "Не удалось разобрать резюме" in reply


class TestUpsertProfile:
    @pytest.mark.asyncio
    async def test_creates_profile_when_none_exists(self, monkeypatch):
        service = _service()

        class _FakeCandidateService:
            def __init__(self, repo):
                pass

            async def get_profile_by_user(self, user_id):
                raise NotFoundError("no profile")

            async def create_profile(self, data):
                assert data.user_id == ti.DEFAULT_USER_ID
                assert data.resume_versions["original"] == "resume text"
                assert data.additional_preferences["parsed_from"] == "telegram"
                return SimpleNamespace(id=uuid4())

        monkeypatch.setattr(ti, "CandidateService", _FakeCandidateService)

        parsed = SimpleNamespace(full_name="Дияр", summary=None)
        profile_id, created = await service._upsert_profile(
            {"desired_positions": ["Data Analyst"], "skills": ["SQL"]},
            "resume text",
            "telegram_1",
            parsed,
        )
        assert created is True
        assert profile_id is not None

    @pytest.mark.asyncio
    async def test_updates_existing_profile(self, monkeypatch):
        service = _service()
        existing = SimpleNamespace(
            id=uuid4(), resume_versions={"original": "old"}, additional_preferences={}
        )
        update_calls = []

        class _FakeCandidateService:
            def __init__(self, repo):
                pass

            async def get_profile_by_user(self, user_id):
                return existing

            async def update_profile(self, profile_id, data):
                update_calls.append((profile_id, data))
                return existing

        monkeypatch.setattr(ti, "CandidateService", _FakeCandidateService)

        parsed = SimpleNamespace(full_name=None, summary=None)
        profile_id, created = await service._upsert_profile(
            {"desired_positions": ["Data Analyst"], "skills": ["SQL"]},
            "new resume",
            "telegram_2",
            parsed,
        )
        assert created is False
        assert profile_id == existing.id
        assert update_calls[0][1].resume_versions["original"] == "old"
        assert update_calls[0][1].resume_versions["telegram_2"] == "new resume"


class TestTrainingDigest:
    def test_full_report_formatting(self):
        report = {
            "total_applications": 12,
            "responded": 5,
            "response_rate": 41.7,
            "interviews": 2,
            "interview_rate": 16.7,
            "missing_skills_on_rejection": [
                {"name": "Kafka", "count": 3},
                {"name": "Airflow", "count": 1},
            ],
        }
        suggestion = SimpleNamespace(
            best_bucket="70-84",
            suggested_skip_below=55,
            insights=["Best bucket: 70-84 (interview rate 50% on 4 applications)"],
        )

        text = TelegramInboundService.format_training_digest(report, suggestion)

        assert "Заявок: 12 · Ответов: 5 (41.7%) · Интервью: 2 (16.7%)" in text
        assert "Лучший диапазон оценок: 70-84" in text
        assert "Ниже score 55" in text
        assert "💡 Best bucket: 70-84" in text
        assert "Kafka (3), Airflow (1)" in text

    def test_empty_report_is_safe(self):
        suggestion = SimpleNamespace(
            best_bucket=None, suggested_skip_below=None, insights=[]
        )
        text = TelegramInboundService.format_training_digest({}, suggestion)

        assert "Заявок: 0" in text
        assert "💡" not in text

    @pytest.mark.asyncio
    async def test_training_digest_wires_services(self, monkeypatch):
        service = _service()
        report = {"total_applications": 0}
        suggestion = SimpleNamespace(
            best_bucket=None, suggested_skip_below=None, insights=[]
        )

        class _FakeFeedback:
            def __init__(self, repo):
                pass

            async def feedback_report(self, candidate_profile_id=None):
                return report

        class _FakeAdvisor:
            def __init__(self, min_bucket):
                pass

            def suggest_from_response(self, stats):
                return suggestion

        monkeypatch.setattr(ti, "FeedbackAnalyticsService", _FakeFeedback)
        monkeypatch.setattr(ti, "ThresholdAdvisor", _FakeAdvisor)

        assert await service.training_digest() == (
            TelegramInboundService.format_training_digest(report, suggestion)
        )
