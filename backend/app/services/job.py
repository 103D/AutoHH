from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import DuplicateError, NotFoundError
from app.models.job import Job, JobSource
from app.repositories.job import JobRepository, JobSourceRepository
from app.schemas.job import JobCreate, JobFilter, JobSourceCreate, RawJob
from app.services.deduplication import DeduplicationService
from app.utils.hash import compute_content_hash, normalize_url


class JobSourceService:
    def __init__(self, repository: JobSourceRepository):
        self.repository = repository

    async def get_source(self, source_id: UUID) -> JobSource:
        source = await self.repository.get(source_id)
        if not source:
            raise NotFoundError(f"Source {source_id} not found")
        return source

    async def get_source_by_name(self, name: str) -> JobSource:
        source = await self.repository.get_by_name(name)
        if not source:
            raise NotFoundError(f"Source '{name}' not found")
        return source

    async def get_enabled_sources(self) -> list[JobSource]:
        return await self.repository.get_enabled()

    async def create_source(self, source_in: JobSourceCreate) -> JobSource:
        existing = await self.repository.get_by_name(source_in.name)
        if existing:
            raise DuplicateError(f"Source '{source_in.name}' already exists")

        source_data = source_in.model_dump()
        return await self.repository.create(source_data)


class JobService:
    def __init__(self, repository: JobRepository):
        self.repository = repository

    async def get_job(self, job_id: UUID) -> Job:
        job = await self.repository.get(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    async def get_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: JobFilter | None = None,
    ) -> list[Job]:
        if filters:
            return await self.repository.get_filtered(filters, skip, limit)
        return await self.repository.get_multi(skip, limit)

    async def create_job(self, job_in: JobCreate) -> Job:
        # Compute deduplication fields
        content_hash = compute_content_hash(
            job_in.title, job_in.company, job_in.description, job_in.location
        )
        url_normalized = normalize_url(job_in.url)

        now = datetime.now(UTC)

        job_data = job_in.model_dump()
        job_data["content_hash"] = content_hash
        job_data["url_normalized"] = url_normalized
        job_data["first_seen_at"] = now
        job_data["last_seen_at"] = now

        return await self.repository.create(job_data)

    async def ingest_raw_job(
        self, source_id: UUID, raw_job: RawJob, dedup_service: DeduplicationService
    ) -> tuple[Job | None, str]:
        """
        Ingest raw job with deduplication.
        Returns (job, status)
        Status: 'created', 'duplicate'
        """

        job_create, status = await dedup_service.process_raw_job(source_id, raw_job)

        if status == "duplicate":
            # Update last_seen_at for existing job
            existing = await self.repository.get_by_external_id(source_id, raw_job.external_id)
            if existing:
                await self.repository.update_last_seen(existing)
            return None, "duplicate"

        if job_create:
            job = await self.create_job(job_create)
            return job, "created"

        return None, "error"
