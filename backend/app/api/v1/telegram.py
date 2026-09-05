"""API endpoints for Telegram bot webhook."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.models.matching import MatchCategory
from app.repositories.application import (
    ApplicationRepository,
    ApplicationStatusHistoryRepository,
)
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository
from app.repositories.matching import MatchResultRepository
from app.repositories.notification import NotificationRepository
from app.services.application import ApplicationService
from app.services.candidate import CandidateService
from app.services.matching import MatchingService
from app.services.telegram_inbound import TelegramInboundService
from app.services.telegram_v2 import TelegramDigestAdapter

logger = get_logger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _application_service(session: AsyncSession) -> ApplicationService:
    """Build the application service from a raw session."""
    return ApplicationService(
        ApplicationRepository(session),
        ApplicationStatusHistoryRepository(session),
        JobRepository(session),
        CandidateService(CandidateRepository(session)),
    )


async def _record_callback(
    session: AsyncSession, match_id: UUID, action: str
) -> None:
    """Store the callback action on the notification log (best effort)."""
    try:
        notification_repo = NotificationRepository(session)
        notification = await notification_repo.get_by_match_result(match_id)
        if notification:
            notification.callback_action = action
            notification.callback_at = datetime.now(UTC)
            notification.status = "callback"
    except Exception as e:
        logger.warning(f"Failed to record callback on notification log: {e}")


async def _handle_v2_action(
    session: AsyncSession, action: str, match_id_str: str
) -> str:
    """Handle a v2 digest callback: study / package / star / skip."""
    try:
        match_id = UUID(match_id_str)
    except ValueError:
        return "Некорректный идентификатор вакансии"

    match_repo = MatchResultRepository(session)
    match = await match_repo.get(match_id)
    if not match:
        return "Вакансия больше не доступна в подборке"

    job = await JobRepository(session).get(match.job_id)
    job_title = job.title if job else "вакансия"

    if action == "study":
        await _record_callback(session, match_id, action)
        text = "🔗 " + ((job.url if job else None) or "ссылка недоступна")
        if job and job.description:
            text += "\n\n" + job.description[:300]
        return text

    if action == "star":
        matching_service = MatchingService(
            JobRepository(session),
            CandidateService(CandidateRepository(session)),
            match_repo,
        )
        await matching_service.set_recommendation_override(
            match.job_id, match.candidate_profile_id, MatchCategory.DREAM_JOB
        )
        await _record_callback(session, match_id, action)
        return f"⭐ Помечено как работа мечты: {job_title}"

    application_service = _application_service(session)
    if action == "package":
        application = await application_service.save_job_from_telegram(
            match.job_id,
            status="SAVED",
            comment="Saved from Telegram digest",
        )
        await _record_callback(session, match_id, action)
        return (
            f"📦 {job_title} сохранена в трекер (статус {application.status}). "
            "Пакет документов: кнопка Prepare на дашборде."
        )

    if action == "skip":
        await application_service.save_job_from_telegram(
            match.job_id,
            status="SKIPPED",
            comment="Skipped from Telegram digest",
        )
        await _record_callback(session, match_id, action)
        return f"➡️ Пропущено: {job_title}. В подборке больше не появится."

    return "Неизвестное действие"


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Telegram webhook updates.

    Processes callback queries from inline keyboard buttons (both legacy
    adapter actions and v2 digest actions: study/package/star/skip) and
    inbound text messages (job links, resumes, /score /train /resume
    commands) via TelegramInboundService.
    """
    expected_secret = settings.telegram_webhook_secret
    if expected_secret and request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != expected_secret:
        logger.warning("Telegram webhook rejected: secret token mismatch")
        return JSONResponse({"ok": False}, status_code=403)

    try:
        update = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Telegram update: {e}")
        return {"ok": False}

    if "callback_query" in update:
        callback = update["callback_query"]
        callback_id = callback.get("id", "")
        callback_data = callback.get("data", "")

        telegram = TelegramDigestAdapter()
        parsed = telegram.parse_callback(callback_data)

        if parsed:
            action, entity_id = parsed
            response_text = await _handle_v2_action(session, action, entity_id)
        else:
            response_text = await telegram.handle_callback(callback_data)
            await _record_legacy_callback(session, callback_data)

        await telegram.answer_callback(callback_id, response_text)

    message = update.get("message") or update.get("edited_message")
    if isinstance(message, dict) and isinstance(message.get("text"), str):
        reply = await _handle_message_update(session, message)
        if reply:
            chat_id = str((message.get("chat") or {}).get("id", ""))
            await TelegramDigestAdapter().send_message(chat_id, reply)

    return {"ok": True}


async def _handle_message_update(session: AsyncSession, message: dict) -> str | None:
    """Run the inbound flow for one message; never raises to the webhook."""
    chat_id = str((message.get("chat") or {}).get("id", ""))
    allowed = settings.telegram_allowed_chat_ids
    if allowed and chat_id and chat_id not in allowed:
        logger.warning(f"Ignoring Telegram message from unauthorized chat {chat_id}")
        return None

    inbound = TelegramInboundService(session)
    try:
        return await inbound.handle_message(message["text"])
    except Exception as e:
        logger.error(f"Telegram inbound handling failed: {e}")
        return "⚠️ Внутренняя ошибка при обработке сообщения. Попробуйте позже."


async def _record_legacy_callback(
    session: AsyncSession, callback_data: str
) -> None:
    """Record callback for legacy view/prepare/ignore buttons."""
    parts = callback_data.split(":", 1)
    if len(parts) != 2:
        return
    action, entity_id = parts
    if action not in ("prepare", "ignore"):
        return
    try:
        await _record_callback(session, UUID(entity_id), action)
        await session.commit()
    except ValueError:
        logger.warning(f"Invalid entity ID in callback: {entity_id}")
