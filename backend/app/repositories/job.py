from uuid import UUID
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobSource
from app.repositories.base import BaseRepository

class JobSourceRepository(BaseRepository[JobSource]):
    def __init__(self, session: AsyncSession):
        super().__init__(JobSource, session)
    
    async def get_by_name(self, name: str) -> JobSource | None:
        result = await self.session.execute(
            select(self.model).where(self.model.name == name)
        )
        return result.scalar_one_or_none()
    
    async def get_enabled(self) -> list[JobSource]:
        result = await self.session.execute(
            select(self.model).where(self.model.enabled == True)
        )
        return list(result.scalars().all())

class JobRepository(BaseRepository[Job]):
    def __init__(self, session: AsyncSession):
        super().__init__(Job, session)
    
    async def get_by_external_id(self, source_id: UUID, external_id: str) -> Job | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.source_id == source_id,
                self.model.external_id == external_id
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