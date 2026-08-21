"""Repository for notification log operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationLog
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[NotificationLog]):
    """Repository for notification log operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(NotificationLog, session)

    async def get_by_match_result(self, match_result_id: UUID) -> NotificationLog | None:
        """Get notification log by match result ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.match_result_id == match_result_id)
        )
        return result.scalar_one_or_none()

    async def get_pending(self, limit: int = 20) -> list[NotificationLog]:
        """Get pending notifications."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.status == "pending")
            .order_by(self.model.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
