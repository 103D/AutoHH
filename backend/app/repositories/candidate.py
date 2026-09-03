from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateProfile, ResumeProfile
from app.repositories.base import BaseRepository


class CandidateRepository(BaseRepository[CandidateProfile]):
    """Repository for candidate profile operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(CandidateProfile, session)

    async def get_by_user_id(self, user_id: UUID) -> CandidateProfile | None:
        """Get candidate profile by user ID."""
        result = await self.session.execute(select(self.model).where(self.model.user_id == user_id))
        return result.scalar_one_or_none()


class ResumeProfileRepository(BaseRepository[ResumeProfile]):
    """Repository for resume profile operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(ResumeProfile, session)

    async def list_by_candidate(self, candidate_profile_id: UUID) -> list[ResumeProfile]:
        """List all resume profiles of a candidate."""
        result = await self.session.execute(
            select(self.model).where(self.model.candidate_profile_id == candidate_profile_id)
        )
        return list(result.scalars().all())

    async def get_by_specialization(
        self, candidate_profile_id: UUID, specialization: str
    ) -> ResumeProfile | None:
        """Get the resume profile of a candidate for one specialization."""
        result = await self.session.execute(
            select(self.model).where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.specialization == specialization,
            )
        )
        return result.scalar_one_or_none()
