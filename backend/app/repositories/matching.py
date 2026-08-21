from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matching import MatchResult
from app.repositories.base import BaseRepository


class MatchResultRepository(BaseRepository[MatchResult]):
    def __init__(self, session: AsyncSession):
        super().__init__(MatchResult, session)

    async def get_by_job_and_candidate(
        self, job_id: UUID, candidate_profile_id: UUID
    ) -> MatchResult | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.job_id == job_id,
                self.model.candidate_profile_id == candidate_profile_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_job(self, job_id: UUID) -> list[MatchResult]:
        result = await self.session.execute(
            select(self.model).where(self.model.job_id == job_id)
        )
        return list(result.scalars().all())

    async def get_for_candidate(self, candidate_profile_id: UUID) -> list[MatchResult]:
        result = await self.session.execute(
            select(self.model).where(self.model.candidate_profile_id == candidate_profile_id)
        )
        return list(result.scalars().all())

    async def get_high_priority(
        self, candidate_profile_id: UUID, limit: int = 10
    ) -> list[MatchResult]:
        from sqlalchemy import desc
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.recommendation == "HIGH_PRIORITY",
            )
            .order_by(desc(self.model.analyzed_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_notification(
        self, candidate_profile_id: UUID, limit: int = 20
    ) -> list[MatchResult]:
        """Get matches that haven't been notified yet (for notification worker)."""
        # This would need a notification_logs table to track what was sent
        # For now, return recent high-priority matches
        from sqlalchemy import desc
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.candidate_profile_id == candidate_profile_id,
                self.model.recommendation.in_(["HIGH_PRIORITY", "APPLY"]),
            )
            .order_by(desc(self.model.analyzed_at))
            .limit(limit)
        )
        return list(result.scalars().all())
