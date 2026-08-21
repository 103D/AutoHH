from datetime import datetime
from typing import Any

import httpx

from app.core.logging import get_logger
from app.schemas.job import RawJob

logger = get_logger(__name__)


class HeadHunterKZProvider:
    """HeadHunter Kazakhstan API provider."""

    BASE_URL = "https://api.hh.ru"
    AREA_KAZAKHSTAN = "40"  # Kazakhstan area code
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 30)

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list[RawJob]:
        """
        Fetch jobs from HeadHunter Kazakhstan.

        Filters:
        - text: search query
        - area: location (default: Kazakhstan)
        - experience: experience level
        - employment: employment type
        - schedule: work schedule
        """

        filters = filters or {}

        params = {
            "area": filters.get("area", self.AREA_KAZAKHSTAN),
            "per_page": min(limit, 100),  # API max is 100
            "page": filters.get("page", 0),
        }

        if "text" in filters:
            params["text"] = filters["text"]

        if "experience" in filters:
            params["experience"] = filters["experience"]

        if "employment" in filters:
            params["employment"] = filters["employment"]

        if "schedule" in filters:
            params["schedule"] = filters["schedule"]

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            ) as client:
                response = await client.get(f"{self.BASE_URL}/vacancies", params=params)

                # Handle rate limiting
                if response.status_code == 429:
                    logger.warning("Rate limited by HH API, waiting...")
                    raise httpx.HTTPStatusError(
                        "Rate limited", request=response.request, response=response
                    )

                response.raise_for_status()
                data = response.json()

                jobs = []
                for item in data.get("items", []):
                    jobs.append(self._parse_vacancy(item))

                logger.info(f"Fetched {len(jobs)} jobs from HeadHunter")
                return jobs

        except httpx.HTTPError as e:
            logger.error(f"Error fetching jobs from HeadHunter: {e}")
            raise

    async def get_job_details(self, external_id: str) -> RawJob:
        """Fetch detailed vacancy information."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.BASE_URL}/vacancies/{external_id}")

                if response.status_code == 429:
                    logger.warning("Rate limited by HH API")
                    raise httpx.HTTPStatusError(
                        "Rate limited", request=response.request, response=response
                    )

                response.raise_for_status()
                data = response.json()

                return self._parse_vacancy(data)

        except httpx.HTTPError as e:
            logger.error(f"Error fetching job details: {e}")
            raise

    def _parse_vacancy(self, data: dict[str, Any]) -> RawJob:
        """Parse HH API vacancy data to RawJob."""

        # Extract salary
        salary_data = data.get("salary")
        salary_min = None
        salary_max = None
        currency = None

        if salary_data:
            salary_min = salary_data.get("from")
            salary_max = salary_data.get("to")
            currency = salary_data.get("currency")

        # Extract location
        area = data.get("area", {})
        location = area.get("name")

        # Extract employment type
        employment = data.get("employment", {})
        employment_type = employment.get("id")

        # Extract work format (schedule)
        schedule = data.get("schedule", {})
        work_format = schedule.get("id")

        # Extract description
        description = data.get("description", "")
        if not description:
            # Fallback to snippet
            snippet = data.get("snippet", {})
            description = snippet.get("requirement", "") + " " + snippet.get("responsibility", "")

        # Parse published date
        published_at = None
        published_str = data.get("published_at")
        if published_str:
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        return RawJob(
            external_id=str(data["id"]),
            title=data["name"],
            company=data.get("employer", {}).get("name", "Unknown"),
            description=description,
            url=data.get("alternate_url", ""),
            location=location,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            employment_type=employment_type,
            work_format=work_format,
            published_at=published_at,
            raw_data=data,
        )
