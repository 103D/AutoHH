from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateProfile
from app.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[CandidateProfile]):
    """Repository for candidate profile operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(CandidateProfile, session)

    async def get_by_user_id(self, user_id: UUID) -> CandidateProfile | None:
        """Get candidate profile by user ID."""
        result = await self.session.execute(select(self.model).where(self.model.user_id == user_id))
        return result.scalar_one_or_none()
