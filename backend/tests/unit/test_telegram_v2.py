"""Unit tests for the Telegram v2 digest adapter."""

from types import SimpleNamespace
from uuid import uuid4

from app.models.matching import MatchCategory
from app.services.telegram_v2 import (
    CATEGORY_EMOJI,
    TelegramDigestAdapter,
    effective_category,
    select_daily_top,
)


def _match(
    score: int,
    recommendation: str,
    override: str | None = None,
    strong: list | None = None,
    missing: list | None = None,
) -> SimpleNamespace:
    """Lightweight match stub (only fields the adapter uses)."""
    return SimpleNamespace(
        id=uuid4(),
        score=score,
        recommendation=recommendation,
        user_override_recommendation=override,
        strong_matches=strong or [],
        missing_skills=missing or [],
    )


def _job(**overrides) -> SimpleNamespace:
    data = {
        "id": uuid4(),
        "title": "Senior Data Analyst",
        "company": "Kaspi.kz",
        "salary_min": 500000,
        "salary_max": 700000,
        "currency": "KZT",
        "location": "Almaty",
        "work_format": "hybrid",
        "description": "desc",
        "url": "https://hh.kz/vacancy/1",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class TestEffectiveCategory:
    def test_computed_category(self):
        assert effective_category(_match(90, MatchCategory.STRETCH)) == MatchCategory.STRETCH

    def test_override_wins(self):
        match = _match(60, MatchCategory.SOLID_MATCH, override=MatchCategory.DREAM_JOB)
        assert effective_category(match) == MatchCategory.DREAM_JOB


class TestSelectDailyTop:
    def test_categories_prioritized_over_score(self):
        pairs = [
            (_match(69, MatchCategory.SOLID_MATCH), _job()),
            (_match(72, MatchCategory.STRETCH), _job()),
            (_match(90, MatchCategory.DREAM_JOB), _job()),
        ]
        top = select_daily_top(pairs, limit=3)

        assert [m.score for m, _ in top] == [90, 72, 69]

    def test_override_affects_priority(self):
        pairs = [
            (_match(95, MatchCategory.SOLID_MATCH), _job()),
            (_match(60, MatchCategory.SOLID_MATCH, override=MatchCategory.DREAM_JOB), _job()),
        ]
        top = select_daily_top(pairs, limit=2)

        assert top[0][0].score == 60  # override promoted it to DREAM_JOB

    def test_limit(self):
        pairs = [(_match(90, MatchCategory.DREAM_JOB), _job()) for _ in range(8)]
        assert len(select_daily_top(pairs, limit=5)) == 5


class TestDigestFormatting:
    def setup_method(self):
        self.adapter = TelegramDigestAdapter()

    def test_format_digest_contains_all_vacancies(self):
        pairs = [
            (_match(92, MatchCategory.DREAM_JOB, strong=["SQL", "Python"]), _job()),
            (_match(75, MatchCategory.STRETCH, missing=["Tableau"]), _job()),
        ]
        text = self.adapter.format_digest_message(pairs)

        assert "Подборка дня" in text
        assert "🔥 1. Senior Data Analyst — Kaspi.kz" in text
        assert "92/100 · Работа мечты" in text
        assert "Сильные стороны: SQL, Python" in text
        assert "🚀 2." in text
        assert "75/100 · Растущая роль" in text
        assert "Чему подтянуться: Tableau" in text
        assert "[Изучить] [Пакет] [⭐] [Пропустить]" in text

    def test_vacancy_block_details(self):
        block = self.adapter.format_vacancy_block(1, _match(80, MatchCategory.STRETCH), _job())

        assert "500000–700000 KZT" in block
        assert "Almaty" in block
        assert "hybrid" in block

    def test_keyboard_one_row_per_vacancy(self):
        pairs = [(_match(90, MatchCategory.DREAM_JOB), _job()), (_match(70, MatchCategory.STRETCH), _job())]
        keyboard = self.adapter.get_digest_keyboard(pairs)

        assert len(keyboard["inline_keyboard"]) == 2
        row = keyboard["inline_keyboard"][0]
        assert [b["text"] for b in row] == ["🔍 Изучить", "📦 Пакет", "⭐", "➡️ Пропустить"]
        assert all(len(b["callback_data"]) <= 64 for b in row)

    def test_emoji_mapping(self):
        assert CATEGORY_EMOJI[MatchCategory.DREAM_JOB] == "🔥"
        assert CATEGORY_EMOJI[MatchCategory.STRETCH] == "🚀"
        assert CATEGORY_EMOJI[MatchCategory.SOLID_MATCH] == "✅"


class TestParseCallback:
    def setup_method(self):
        self.adapter = TelegramDigestAdapter()

    def test_valid_actions(self):
        for action in ("study", "package", "star", "skip"):
            parsed = self.adapter.parse_callback(f"{action}:abc-def")
            assert parsed == (action, "abc-def")

    def test_invalid_action(self):
        assert self.adapter.parse_callback("unknown:123") is None

    def test_missing_separator(self):
        assert self.adapter.parse_callback("study") is None

    def test_missing_id(self):
        assert self.adapter.parse_callback("study:") is None
