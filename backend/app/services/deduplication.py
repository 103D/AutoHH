from datetime import datetime
from uuid import UUID

from app.core.logging import get_logger
from app.repositories.job import JobRepository
from app.schemas.job import JobCreate, RawJob
from app.utils.hash import compute_content_hash, normalize_url

logger = get_logger(__name__)

class DeduplicationService:
    """Service for job deduplication logic."""
    
    def __init__(self, repository: JobRepository):
        self.repository = repository
    
    async def find_duplicate(
        self,
        source_id: UUID,
        raw_job: RawJob
    ) -> tuple[bool, str | None]:
        """
        Check if job is duplicate.
        Returns (is_duplicate, reason)
        """
        
        # Check by source + external_id
        existing = await self.repository.get_by_external_id(source_id, raw_job.external_id)
        if existing:
            return True, f"duplicate_external_id:{existing.id}"
        
        # Check by content hash
        content_hash = compute_content_hash(
            raw_job.title,
            raw_job.company,
            raw_job.description,
            raw_job.location
        )
        existing = await self.repository.get_by_content_hash(content_hash)
        if existing:
            return True, f"duplicate_content:{existing.id}"
        
        # Check by normalized URL
        url_normalized = normalize_url(raw_job.url)
        existing = await self.repository.get_by_url_normalized(url_normalized)
        if existing:
            return True, f"duplicate_url:{existing.id}"
        
        return False, None
    
    async def process_raw_job(
        self,
        source_id: UUID,
        raw_job: RawJob
    ) -> tuple[JobCreate | None, str]:
        """
        Process raw job and prepare for creation.
        Returns (job_create, status)
        Status: 'new', 'duplicate', 'updated'
        """
        
        is_duplicate, reason = await self.find_duplicate(source_id, raw_job)
        
        if is_duplicate:
            logger.debug(f"Duplicate job found: {reason}")
            
            # Update last_seen_at for existing job
            if reason:
                existing_id = reason.split(':')[1]
                # This should be handled by service layer
                
            return None, 'duplicate'
        
        # Prepare new job
        content_hash = compute_content_hash(
            raw_job.title,
            raw_job.company,
            raw_job.description,
            raw_job.location
        )
        url_normalized = normalize_url(raw_job.url)
        
        job_create = JobCreate(
            source_id=source_id,
            external_id=raw_job.external_id,
            title=raw_job.title,
            company=raw_job.company,
            description=raw_job.description,
            location=raw_job.location,
            salary_min=raw_job.salary_min,
            salary_max=raw_job.salary_max,
            currency=raw_job.currency,
            employment_type=raw_job.employment_type,
            work_format=raw_job.work_format,
            url=raw_job.url,
            published_at=raw_job.published_at,
            raw_data=raw_job.raw_data
        )
        
        return job_create, 'new'