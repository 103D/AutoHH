"""Habr Career provider (career.habr.com).

Habr Career has no official public API, so this provider fetches public
vacancy search pages and parses the schema.org JobPosting JSON-LD blocks
embedded in them. Best effort: when the page structure changes and no
structured data is found, an empty list is returned (with a warning) instead
of raising, so one broken source never breaks the whole pipeline.
"""

from typing import Any

import httpx

from app.core.logging import get_logger
from app.providers.jobs.jsonld import extract_jobposting_blocks, jobposting_to_rawjob
from app.schemas.job import RawJob

logger = get_logger(__name__)


class HabrCareerProvider:
    """Habr Career scraper based on JSON-LD structured data."""

    BASE_URL = "https://career.habr.com"
    MAX_PAGES = 3

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.base_url = self.config.get("base_url", self.BASE_URL)
        self.timeout = self.config.get("timeout", 30)

    def _build_params(self, filters: dict | None) -> dict[str, Any]:
        """Build search params from filters and source config."""
        filters = filters or {}
        params: dict[str, Any] = {
            "q": filters.get("text") or self.config.get("query", "data analyst"),
            "page": filters.get("page", 1),
        }
        remote = filters.get("remote", self.config.get("remote", True))
        if remote:
            params["remote"] = "true"
        city = filters.get("city") or self.config.get("city")
        if city:
            params["city"] = city
        return params

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list[RawJob]:
        """Fetch vacancies from Habr Career search pages."""
        params = self._build_params(filters)
        jobs: list[RawJob] = []
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                for page in range(params["page"], self.MAX_PAGES + 1):
                    if len(jobs) >= limit:
                        break
                    params["page"] = page
                    response = await client.get(f"{self.base_url}/vacancies", params=params)
                    response.raise_for_status()

                    postings = extract_jobposting_blocks(response.text)
                    if not postings:
                        break  # structure changed or empty page: stop gracefully
                    for posting in postings:
                        # One malformed vacancy must not fail the whole batch.
                        try:
                            jobs.append(self._parse_jobposting(posting))
                        except Exception as e:
                            logger.warning(
                                f"Skipping malformed Habr Career posting: {e}"
                            )

            logger.info(f"Fetched {len(jobs)} jobs from Habr Career")
            return jobs[:limit]

        except httpx.HTTPError as e:
            logger.error(f"Error fetching jobs from Habr Career: {e}")
            raise

    async def get_job_details(self, external_id: str) -> RawJob:
        """Fetch a single vacancy page and parse its JSON-LD block."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                response = await client.get(f"{self.base_url}/vacancies/{external_id}")
                response.raise_for_status()

            postings = extract_jobposting_blocks(response.text)
            if not postings:
                raise ValueError(f"No JobPosting structured data on page {external_id}")
            return self._parse_jobposting(postings[0])

        except httpx.HTTPError as e:
            logger.error(f"Error fetching Habr Career vacancy {external_id}: {e}")
            raise

    def _parse_jobposting(self, posting: dict[str, Any]) -> RawJob:
        """Convert a JSON-LD JobPosting block into RawJob."""
        return RawJob(**jobposting_to_rawjob(posting, self.base_url))
