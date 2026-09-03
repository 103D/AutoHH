"""Zarplata.ru provider.

Zarplata.ru has no documented public API, so this provider fetches public
vacancy search pages and parses schema.org JobPosting JSON-LD blocks embedded
in them (same best-effort approach as the Habr Career provider). The base URL
and search path are configurable in case the site structure changes.
"""

from typing import Any

import httpx

from app.core.logging import get_logger
from app.providers.jobs.jsonld import extract_jobposting_blocks, jobposting_to_rawjob
from app.schemas.job import RawJob

logger = get_logger(__name__)


class ZarplataProvider:
    """Zarplata.ru scraper based on JSON-LD structured data."""

    BASE_URL = "https://zarplata.ru"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", self.BASE_URL)
        self.search_path = self.config.get("search_path", "/vacancies")
        self.timeout = self.config.get("timeout", 30)

    def _build_params(self, filters: dict | None) -> dict[str, Any]:
        """Build search params from filters and source config."""
        filters = filters or {}
        params: dict[str, Any] = {
            "text": filters.get("text") or self.config.get("query", "аналитик данных"),
            "page": filters.get("page", 1),
        }
        remote = filters.get("remote", self.config.get("remote", False))
        if remote:
            params["remote"] = "true"
        return params

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list[RawJob]:
        """Fetch vacancies from Zarplata.ru search pages."""
        params = self._build_params(filters)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                response = await client.get(
                    f"{self.base_url}{self.search_path}", params=params
                )
                response.raise_for_status()

            postings = extract_jobposting_blocks(response.text)
            jobs = [self._parse_jobposting(p) for p in postings]
            logger.info(f"Fetched {len(jobs)} jobs from Zarplata.ru")
            return jobs[:limit]

        except httpx.HTTPError as e:
            logger.error(f"Error fetching jobs from Zarplata.ru: {e}")
            raise

    async def get_job_details(self, external_id: str) -> RawJob:
        """Fetch a single vacancy page and parse its JSON-LD block."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                response = await client.get(
                    f"{self.base_url}{self.search_path}/{external_id}"
                )
                response.raise_for_status()

            postings = extract_jobposting_blocks(response.text)
            if not postings:
                raise ValueError(f"No JobPosting structured data on page {external_id}")
            return self._parse_jobposting(postings[0])

        except httpx.HTTPError as e:
            logger.error(f"Error fetching Zarplata.ru vacancy {external_id}: {e}")
            raise

    def _parse_jobposting(self, posting: dict[str, Any]) -> RawJob:
        """Convert a JSON-LD JobPosting block into RawJob."""
        return RawJob(**jobposting_to_rawjob(posting, self.base_url))
