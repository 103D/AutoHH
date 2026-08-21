"""Repository for application operations."""

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatusHistory
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    """Repository for application operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Application, session)

    async def get_by_job_and_candidate(
        self, job_id: UUID, candidate_profile_id: UUID
    ) -> Application | None:
        """Get application by job and candidate."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.job_id == job_id,
                self.model.candidate_profile_id == candidate_profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_status(
        self, status: str, limit: int = 50
    ) -> list[Application]:
        """Get applications by status."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.status == status)
            .order_by(desc(self.model.updated_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_candidate(
        self, candidate_profile_id: UUID, limit: int = 50
    ) -> list[Application]:
        """Get all applications for a candidate."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.candidate_profile_id == candidate_profile_id)
            .order_by(desc(self.model.updated_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class ApplicationStatusHistoryRepository(BaseRepository[ApplicationStatusHistory]):
    """Repository for application status history."""

    def __init__(self, session: AsyncSession):
        super().__init__(ApplicationStatusHistory, session)

    async def get_for_application(
        self, application_id: UUID
    ) -> list[ApplicationStatusHistory]:
        """Get status history for an application (ordered by time)."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.application_id == application_id)
            .order_by(self.model.changed_at.asc())
        )
        return list(result.scalars().all())
