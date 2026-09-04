"""Manual job source provider for vacancies added by hand.

Covers sources without public APIs (e.g. LinkedIn) or vacancies found via
referrals: jobs are stored directly in the job source configuration as a
list of RawJob-like dicts.
"""

from typing import Any
from uuid import uuid4

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.schemas.job import RawJob

logger = get_logger(__name__)


class ManualProvider:
    """Provider that serves vacancies from the source configuration.

    Expected configuration format::

        {
            "jobs": [
                {
                    "external_id": "li-12345",       # optional, generated if missing
                    "title": "Data Analyst",
                    "company": "Kaspi",
                    "description": "…",
                    "url": "https://linkedin.com/jobs/…",
                    "location": "Almaty",            # optional
                    "salary_min": 500000,            # optional
                    "salary_max": 800000,            # optional
                    "currency": "KZT",               # optional
                    "work_format": "remote",         # optional
                    "employment_type": "full_time",  # optional
                }
            ]
        }
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list[RawJob]:
        """Return manually configured vacancies (optionally filtered by text)."""
        entries = self.config.get("jobs", [])
        if not isinstance(entries, list):
            logger.error("Manual source configuration 'jobs' must be a list")
            return []

        query = (filters or {}).get("text")
        jobs: list[RawJob] = []
        for entry in entries:
            if not isinstance(entry, dict):
                logger.warning("Skipping invalid manual job entry (not a dict)")
                continue
            if query:
                haystack = " ".join(
                    str(entry.get(field) or "")
                    for field in ("title", "company", "description")
                ).lower()
                if query.lower() not in haystack:
                    continue
            # One malformed entry must not fail the whole batch.
            try:
                jobs.append(self._parse_entry(entry))
            except Exception as e:
                logger.warning(
                    f"Skipping invalid manual job entry "
                    f"{entry.get('external_id') or entry.get('title')!r}: {e}"
                )
                continue
            if len(jobs) >= limit:
                break

        logger.info(f"Fetched {len(jobs)} manual jobs")
        return jobs

    async def get_job_details(self, external_id: str) -> RawJob:
        """Find a manually configured job by external id."""
        for entry in self.config.get("jobs", []):
            if isinstance(entry, dict) and str(entry.get("external_id")) == str(external_id):
                return self._parse_entry(entry)
        raise NotFoundError(f"Manual job '{external_id}' not found in source configuration")

    def _parse_entry(self, entry: dict[str, Any]) -> RawJob:
        """Validate and normalize a manual job entry."""
        data = dict(entry)
        if not data.get("external_id"):
            data["external_id"] = f"manual-{uuid4().hex[:12]}"
        return RawJob(**data)
