"""RemoteOK provider (https://remoteok.com/api).

Remote OK exposes a public JSON feed with remote-only vacancies worldwide.
The feed does not require authentication or an API key. The first array
element is a metadata dict (legal notice); vacancies follow it."""

import re
from datetime import datetime
from typing import Any

import httpx

from app.core.logging import get_logger
from app.schemas.job import RawJob
from app.utils.experience import extract_required_experience_years

logger = get_logger(__name__)


class RemoteOkProvider:
    """RemoteOK public API provider (remote-only vacancies worldwide)."""

    BASE_URL = "https://remoteok.com/api"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 30)
        self.tag = self.config.get("tag")

    async def fetch_jobs(
        self, filters: dict | None = None, limit: int = 100
    ) -> list[RawJob]:
        """Fetch remote jobs from the public RemoteOK feed.

        Filters:
        - text: optional tag (e.g. "python", "data", "devops")).
        """
        params: dict[str, str] = {}
        tag = (filters or {}).get("text") or self.tag
        if tag:
            params["tag"] = tag

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(self.BASE_URL, params=params)

                response.raise_for_status()
                data = response.json()

            jobs: list[RawJob] = []
            for item in data:
                if not isinstance(item, dict) or not item.get("id") or not item.get("position"):
                    continue  # skip the metadata entry and malformed records
                # One malformed vacancy must not fail the whole batch.
                try:
                    jobs.append(self._parse_vacancy(item))
                except Exception as e:
                    logger.warning(
                        f"Skipping malformed RemoteOK vacancy {item.get('id')!r}: {e}"
                    )
                    continue
                if len(jobs) >= limit:
                    break

            logger.info(f"Fetched {len(jobs)} jobs from RemoteOK")
            return jobs

        except httpx.HTTPError as e:
            logger.error(f"Error fetching jobs from RemoteOK: {e}")
            raise

    async def get_job_details(self, external_id: str) -> RawJob:
        """Fetch a single vacancy from the public feed by id."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(self.BASE_URL)

                response.raise_for_status()
                data = response.json()

            for item in data:
                if isinstance(item, dict) and str(item.get("id")) == str(external_id):
                    return self._parse_vacancy(item)
            logger.warning(f"RemoteOK vacancy {external_id} not found in feed")
            raise ValueError(f"RemoteOK vacancy {external_id} not found")

        except httpx.HTTPError as e:
            logger.error(f"Error fetching RemoteOK vacancy {external_id}: {e}")
            raise

    def _parse_vacancy(self, data: dict[str, Any]) -> RawJob:
        """Convert a RemoteOK feed item into RawJob."""
        raw_min = data.get("salary_min")
        raw_max = data.get("salary_max")
        salary_min = int(raw_min) if raw_min else None
        salary_max = int(raw_max) if raw_max else None

        published_at = None
        date_str = data.get("date")
        if date_str:
            try:
                published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        description = re.sub(r"<[^>]+>", " ", data.get("description") or "")
        description = re.sub(r"\s+", " ", description).strip()
        location = None
        if data.get("location"):
            location = str(data["location"]).strip() or None

        return RawJob(
            external_id=str(data["id"]),
            title=str(data["position"]),
            company=str(data.get("company") or "Unknown"),
            description=description,
            url=data.get("url") or data.get("apply_url") or "",
            location=location,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=None,  # RemoteOK does not expose currency
            employment_type=None,
            work_format="remote",
            experience_required=extract_required_experience_years(description),
            published_at=published_at,
            raw_data=data,
        )
