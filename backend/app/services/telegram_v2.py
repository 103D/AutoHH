"""Telegram v2 adapter: daily top-5 digest with action buttons.

Extends the base adapter with:
- category emoji and Russian labels (matching v2)
- a daily digest message (top-5 vacancies)
- inline buttons: [Изучить] [Пакет] [⭐] [Пропустить]
"""

from datetime import UTC, datetime

import httpx

from app.core.logging import get_logger
from app.models.job import Job
from app.models.matching import MatchCategory, MatchResult
from app.services.telegram import TelegramBotAdapter

logger = get_logger(__name__)

CATEGORY_EMOJI = {
    MatchCategory.DREAM_JOB: "🔥",
    MatchCategory.STRETCH: "🚀",
    MatchCategory.SOLID_MATCH: "✅",
    MatchCategory.MARKET_RESEARCH: "📊",
    MatchCategory.LEARNING_OPPORTUNITY: "🎓",
    MatchCategory.IGNORE: "💤",
}

CATEGORY_LABELS_RU = {
    MatchCategory.DREAM_JOB: "Работа мечты",
    MatchCategory.STRETCH: "Растущая роль",
    MatchCategory.SOLID_MATCH: "Уверенное совпадение",
    MatchCategory.MARKET_RESEARCH: "Для изучения рынка",
    MatchCategory.LEARNING_OPPORTUNITY: "Чему учиться",
    MatchCategory.IGNORE: "Пропустить",
}

# Daily digest priority: dream jobs first, then stretch, then solid matches
CATEGORY_RANK = {
    MatchCategory.DREAM_JOB: 0,
    MatchCategory.STRETCH: 1,
    MatchCategory.SOLID_MATCH: 2,
    MatchCategory.MARKET_RESEARCH: 3,
    MatchCategory.LEARNING_OPPORTUNITY: 4,
    MatchCategory.IGNORE: 5,
}

# v2 callback actions
V2_ACTIONS = ("study", "package", "star", "skip")


def effective_category(match: MatchResult) -> str:
    """User override wins over the computed category."""
    return match.user_override_recommendation or match.recommendation


def select_daily_top(
    pairs: list[tuple[MatchResult, Job]], limit: int = 5
) -> list[tuple[MatchResult, Job]]:
    """Pick the daily top list: category priority first, then score."""
    def sort_key(pair: tuple[MatchResult, Job]):
        match, _job = pair
        return (CATEGORY_RANK.get(effective_category(match), 99), -match.score)

    return sorted(pairs, key=sort_key)[:limit]


class TelegramDigestAdapter(TelegramBotAdapter):
    """Telegram adapter for the daily digest flow."""

    def _salary_line(self, job: Job) -> str | None:
        if job.salary_min or job.salary_max:
            salary = f"{job.salary_min or '?'}–{job.salary_max or '?'}"
            if job.currency:
                salary += f" {job.currency}"
            return salary
        return None

    def format_vacancy_block(self, position: int, match: MatchResult, job: Job) -> str:
        """Format a single vacancy entry of the digest."""
        category = effective_category(match)
        emoji = CATEGORY_EMOJI.get(category, "📋")
        label = CATEGORY_LABELS_RU.get(category, category)

        lines = [f"{emoji} {position}. {job.title} — {job.company or '—'}"]

        details = [f"{match.score}/100 · {label}"]
        salary = self._salary_line(job)
        if salary:
            details.append(salary)
        if job.location:
            details.append(str(job.location))
        if job.work_format:
            details.append(str(job.work_format))
        lines.append("   " + " · ".join(str(d) for d in details))

        if category == MatchCategory.STRETCH:
            if match.missing_skills:
                learned = ", ".join(str(s) for s in match.missing_skills[:3])
                lines.append(f"   Чему подтянуться: {learned}")
        elif match.strong_matches:
            strong = ", ".join(str(s) for s in match.strong_matches[:3])
            lines.append(f"   Сильные стороны: {strong}")

        return "\n".join(lines)

    def format_digest_message(
        self, pairs: list[tuple[MatchResult, Job]]
    ) -> str:
        """Format the full daily digest message."""
        today = datetime.now(UTC).strftime("%d.%m.%Y")
        lines = [f"🌅 Подборка дня — топ-{len(pairs)} · {today}", ""]
        for position, (match, job) in enumerate(pairs, 1):
            lines.append(self.format_vacancy_block(position, match, job))
            lines.append("")
        lines.append("Кнопки под номерами: [Изучить] [Пакет] [⭐] [Пропустить]")
        return "\n".join(lines)

    def get_digest_keyboard(
        self, pairs: list[tuple[MatchResult, Job]]
    ) -> dict:
        """Build one action-button row per vacancy."""
        keyboard = []
        for match, _job in pairs:
            mid = str(match.id)
            keyboard.append([
                {"text": "🔍 Изучить", "callback_data": f"study:{mid}"},
                {"text": "📦 Пакет", "callback_data": f"package:{mid}"},
                {"text": "⭐", "callback_data": f"star:{mid}"},
                {"text": "➡️ Пропустить", "callback_data": f"skip:{mid}"},
            ])
        return {"inline_keyboard": keyboard}

    async def send_daily_digest(
        self, pairs: list[tuple[MatchResult, Job]]
    ) -> str | None:
        """
        Send the daily digest message with per-vacancy action buttons.

        Returns:
            Telegram message ID if successful, None otherwise.
        """
        if not self._is_configured():
            logger.warning("Telegram not configured, skipping daily digest")
            return None

        text = self.format_digest_message(pairs)
        keyboard = self.get_digest_keyboard(pairs)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard,
                    },
                )
                response.raise_for_status()
                data = response.json()

                if data.get("ok"):
                    message_id = str(data["result"]["message_id"])
                    logger.info(
                        f"Daily digest sent: {len(pairs)} vacancies, "
                        f"message_id={message_id}"
                    )
                    return message_id

                logger.error(f"Telegram API error: {data}")
                return None

        except httpx.HTTPError as e:
            logger.error(f"Failed to send daily digest: {e}")
            return None

    @staticmethod
    def parse_callback(callback_data: str) -> tuple[str, str] | None:
        """Parse a v2 callback into (action, match_id), or None if invalid."""
        action, sep, entity_id = callback_data.partition(":")
        if not sep or action not in V2_ACTIONS or not entity_id:
            return None
        return action, entity_id
