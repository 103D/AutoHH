"""Telegram bot adapter for sending job match notifications."""

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.job import Job
from app.models.matching import MatchResult

logger = get_logger(__name__)


class TelegramBotAdapter:
    """Adapter for Telegram Bot API."""

    BASE_URL = "https://api.telegram.org"

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self.bot_token = bot_token or settings.telegram_bot_token
        self.chat_id = chat_id or settings.telegram_chat_id
        self.timeout = 30.0

    def _is_configured(self) -> bool:
        """Check if Telegram is configured."""
        return bool(self.bot_token and self.chat_id)

    def _format_match_message(self, match: MatchResult, job: Job) -> str:
        """Format match result as Telegram message."""
        score_emoji = "🔥" if match.score >= 90 else "✅" if match.score >= 75 else "📋"

        lines = [f"{score_emoji} New match vacancy", "", f"{job.title}"]

        if job.company:
            lines.append(f"Company: {job.company}")

        lines.append(f"Match: {match.score}%")

        if job.salary_min or job.salary_max:
            salary = f"Salary: {job.salary_min or '?'}–{job.salary_max or '?'}"
            if job.currency:
                salary += f" {job.currency}"
            lines.append(salary)

        if job.work_format:
            lines.append(f"Format: {job.work_format.capitalize()}")

        if job.location:
            lines.append(f"Location: {job.location}")

        if match.strong_matches:
            lines.append("")
            lines.append("Strong matches:")
            for skill in match.strong_matches[:5]:
                lines.append(f"• {skill}")

        if match.missing_skills:
            lines.append("")
            lines.append("Missing:")
            for skill in match.missing_skills[:3]:
                lines.append(f"• {skill}")

        lines.append("")
        lines.append(f"Recommendation: {match.recommendation}")

        if job.url:
            lines.append("")
            lines.append(f"[View vacancy]({job.url})")

        return "\n".join(lines)

    def _get_inline_keyboard(self, job_id: str, match_id: str) -> dict:
        """Build inline keyboard for match notification."""
        return {
            "inline_keyboard": [
                [
                    {"text": "📋 View", "callback_data": f"view:{job_id}"},
                    {"text": "✏️ Prepare", "callback_data": f"prepare:{match_id}"},
                ],
                [
                    {"text": "🚫 Ignore", "callback_data": f"ignore:{match_id}"},
                ],
            ]
        }

    async def send_match_notification(
        self, match: MatchResult, job: Job
    ) -> str | None:
        """
        Send notification about a job match.

        Returns:
            Telegram message ID if successful, None otherwise.
        """
        if not self._is_configured():
            logger.warning("Telegram not configured, skipping notification")
            return None

        text = self._format_match_message(match, job)
        keyboard = self._get_inline_keyboard(str(job.id), str(match.id))

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
                    logger.info(f"Telegram notification sent: message_id={message_id}")
                    return message_id

                logger.error(f"Telegram API error: {data}")
                return None

        except httpx.HTTPError as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None

    async def handle_callback(self, callback_data: str) -> str:
        """
        Handle callback from inline keyboard.

        Args:
            callback_data: Callback data from button press

        Returns:
            Response text to show to user.
        """
        parts = callback_data.split(":", 1)
        if len(parts) != 2:
            return "Invalid callback"

        action, entity_id = parts

        if action == "view":
            return f"Opening vacancy {entity_id}..."
        elif action == "prepare":
            return f"Preparing application for match {entity_id}..."
        elif action == "ignore":
            return f"Match {entity_id} ignored."
        else:
            return f"Unknown action: {action}"

    async def answer_callback(
        self, callback_query_id: str, text: str
    ) -> bool:
        """Answer a callback query."""
        if not self.bot_token:
            return False

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/bot{self.bot_token}/answerCallbackQuery",
                    json={
                        "callback_query_id": callback_query_id,
                        "text": text,
                    },
                )
                response.raise_for_status()
                return response.json().get("ok", False)
        except httpx.HTTPError as e:
            logger.error(f"Failed to answer callback: {e}")
            return False
