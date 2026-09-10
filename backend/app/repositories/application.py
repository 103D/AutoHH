"""Repository for application operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, select
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

    async def get_by_job_and_user(self, job_id: UUID, user_id: UUID) -> Application | None:
        """Find an application for a job owned by a specific local user."""
        from app.models.candidate import CandidateProfile

        result = await self.session.execute(
            select(self.model)
            .join(
                CandidateProfile,
                CandidateProfile.id == self.model.candidate_profile_id,
            )
            .where(self.model.job_id == job_id, CandidateProfile.user_id == user_id)
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

    async def list_feedback_dataset(
        self, candidate_profile_id: UUID | None = None, limit: int = 1000
    ) -> list[tuple[Application, Any, Any, Any]]:
        """Applications joined with their MatchResult, Job and ResumeProfile.

        Returns rows of (application, match | None, job | None,
        resume_profile | None) — the raw feedback dataset for outcome
        analytics (task spec #17). Outer joins keep applications without a
        match/job/profile in the dataset.
        """
        from app.models.candidate import ResumeProfile
        from app.models.job import Job
        from app.models.matching import MatchResult

        stmt = (
            select(Application, MatchResult, Job, ResumeProfile)
            .outerjoin(
                MatchResult,
                and_(
                    MatchResult.job_id == Application.job_id,
                    MatchResult.candidate_profile_id == Application.candidate_profile_id,
                ),
            )
            .outerjoin(Job, Job.id == Application.job_id)
            .outerjoin(ResumeProfile, ResumeProfile.id == Application.resume_profile_id)
            .order_by(desc(Application.updated_at))
            .limit(limit)
        )
        if candidate_profile_id is not None:
            stmt = stmt.where(Application.candidate_profile_id == candidate_profile_id)
        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]


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
