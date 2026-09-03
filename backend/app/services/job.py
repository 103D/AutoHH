from datetime import UTC, datetime
from uuid import UUID

from app.core.exceptions import DuplicateError, NotFoundError
from app.models.job import Job, JobSource
from app.repositories.job import JobRepository, JobSourceRepository
from app.schemas.job import JobCreate, JobFilter, JobSourceCreate, ManualJobCreate, RawJob
from app.services.deduplication import DeduplicationService
from app.utils.hash import compute_content_hash, normalize_url

# Well-known name/type of the manual import source (task spec #4)
MANUAL_SOURCE_NAME = "manual"


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

    async def get_or_create_manual_source(self) -> JobSource:
        """Get or create the dedicated manual import source (task spec #4).

        A single well-known source ("manual", type "manual") so manually added
        vacancies live in the same jobs table and pass the exact same pipeline
        as provider-fetched ones. Fetching it is harmless: ManualProvider
        serves vacancies from its configuration only.
        """
        source = await self.repository.get_by_name(MANUAL_SOURCE_NAME)
        if source:
            return source
        return await self.repository.create(
            {
                "name": MANUAL_SOURCE_NAME,
                "type": "manual",
                "enabled": True,
                "configuration": {},
            }
        )


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
        # Always go trough get_filtered (it joins job_sources и exposes the source type)。
        return await self.repository.get_filtered(filters or JobFilter(), skip, limit)

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
        self,
        source_id: UUID,
        raw_job: RawJob,
        dedup_service: DeduplicationService,
        source_type: str | None = None,
    ) -> tuple[Job | None, str]:
        """
        Ingest raw job with deduplication.
        Returns (job, status)
        Status: 'created', 'duplicate'
        """

        job_create, status = await dedup_service.process_raw_job(
            source_id, raw_job, source_type=source_type
        )

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

    async def ingest_manual_job(
        self,
        source_id: UUID,
        payload: ManualJobCreate,
        dedup_service: DeduplicationService,
        source_type: str = "manual",
    ) -> tuple[Job | None, str, str]:
        """Import a manually provided vacancy through the standard pipeline.

        normalize -> deduplicate -> persist — the exact same path as every
        provider (task spec #4). The external_id is deterministic (derived
        from the content hash) unless explicitly supplied, so re-importing
        the same vacancy is idempotent.

        Returns (job, status, external_id); status: 'created' | 'duplicate'.
        """
        content_hash = compute_content_hash(
            payload.title, payload.company, payload.description, payload.location
        )
        external_id = payload.external_id or f"manual-{content_hash[:16]}"
        raw_job = RawJob(
            external_id=external_id,
            title=payload.title,
            company=payload.company,
            description=payload.description,
            url=payload.url or f"manual://{external_id}",
            location=payload.location,
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            currency=payload.currency,
            employment_type=payload.employment_type,
            work_format=payload.work_format,
            experience_required=payload.experience_required,
            published_at=payload.published_at,
            raw_data={"import": "manual"},
        )
        job, status = await self.ingest_raw_job(
            source_id, raw_job, dedup_service, source_type=source_type
        )
        return job, status, external_id
