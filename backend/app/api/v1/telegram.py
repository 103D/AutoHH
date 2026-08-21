"""API endpoints for Telegram bot webhook."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.logging import get_logger
from app.services.telegram import TelegramBotAdapter

logger = get_logger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Handle Telegram webhook updates.

    Processes callback queries from inline keyboard buttons.
    """
    try:
        update = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse Telegram update: {e}")
        return {"ok": False}

    # Handle callback query (button press)
    if "callback_query" in update:
        callback = update["callback_query"]
        callback_id = callback.get("id", "")
        callback_data = callback.get("data", "")

        telegram = TelegramBotAdapter()
        response_text = await telegram.handle_callback(callback_data)

        await telegram.answer_callback(callback_id, response_text)

        # Update notification log if applicable
        parts = callback_data.split(":", 1)
        if len(parts) == 2:
            action, entity_id = parts
            if action in ("prepare", "ignore"):
                from datetime import UTC, datetime
                from uuid import UUID

                from app.repositories.notification import NotificationRepository

                notification_repo = NotificationRepository(session)

                # Find notification by match_result_id
                try:
                    match_id = UUID(entity_id)
                    notification = await notification_repo.get_by_match_result(match_id)
                    if notification:
                        notification.callback_action = action
                        notification.callback_at = datetime.now(UTC)
                        notification.status = "callback"
                        await session.commit()
                except ValueError:
                    logger.warning(f"Invalid entity ID in callback: {entity_id}")

    return {"ok": True}
