from typing import Protocol

from app.schemas.job import RawJob


class JobSourceProvider(Protocol):
    """Protocol for job source providers."""

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list[RawJob]:
        """
        Fetch jobs from source.
        Returns raw, unnormalized job data.
        """
        ...

    async def get_job_details(self, external_id: str) -> RawJob:
        """Fetch detailed job information by external ID."""
        ...
