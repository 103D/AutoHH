from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobSource
from app.repositories.base import BaseRepository
from app.schemas.job import JobFilter


class JobSourceRepository(BaseRepository[JobSource]):
    def __init__(self, session: AsyncSession):
        super().__init__(JobSource, session)

    async def get_by_name(self, name: str) -> JobSource | None:
        result = await self.session.execute(select(self.model).where(self.model.name == name))
        return result.scalar_one_or_none()

    async def get_enabled(self) -> list[JobSource]:
        result = await self.session.execute(select(self.model).where(self.model.enabled.is_(True)))
        return list(result.scalars().all())


class JobRepository(BaseRepository[Job]):
    def __init__(self, session: AsyncSession):
        super().__init__(Job, session)

    async def get_by_external_id(self, source_id: UUID, external_id: str) -> Job | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.source_id == source_id, self.model.external_id == external_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_content_hash(self, content_hash: str) -> Job | None:
        result = await self.session.execute(
            select(self.model).where(self.model.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_url_normalized(self, url_normalized: str) -> Job | None:
        result = await self.session.execute(
            select(self.model).where(self.model.url_normalized == url_normalized)
        )
        return result.scalar_one_or_none()

    async def update_last_seen(self, job: Job) -> Job:
        """Update last_seen_at timestamp."""
        job.last_seen_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_filtered(
        self,
        filters: JobFilter,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Job]:
        """Get jobs with filters."""
        query = select(self.model)

        if filters.company:
            query = query.where(self.model.company.ilike(f"%{filters.company}%"))

        if filters.location:
            query = query.where(self.model.location.ilike(f"%{filters.location}%"))

        if filters.salary_min is not None:
            query = query.where(self.model.salary_min >= filters.salary_min)

        if filters.salary_max is not None:
            query = query.where(self.model.salary_max <= filters.salary_max)

        if filters.currency:
            query = query.where(self.model.currency == filters.currency)

        if filters.employment_type:
            query = query.where(self.model.employment_type == filters.employment_type)

        if filters.work_format:
            query = query.where(self.model.work_format == filters.work_format)

        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(self.model.title.ilike(search_term), self.model.description.ilike(search_term))
            )

        if filters.published_after:
            query = query.where(self.model.published_at >= filters.published_after)

        query = query.order_by(self.model.published_at.desc()).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())
