"""SuperJob API provider (https://docs.superjob.ru/)."""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.exceptions import JobSourceError
from app.core.logging import get_logger
from app.schemas.job import RawJob

logger = get_logger(__name__)

_CURRENCY_MAP = {"rur": "RUB", "rub": "RUB", "kzt": "KZT", "usd": "USD", "eur": "EUR"}
_EMPLOYMENT_MAP = {
    "полный рабочий день": "full_time",
    "неполный рабочий день": "part_time",
    "вахтовый метод": None,
    "свободный график": None,
}
_WORK_FORMAT_MAP = {
    "удалённая работа": "remote",
    "удаленная работа": "remote",
    "на территории работодателя": "office",
}


class SuperJobProvider:
    """SuperJob.ru API provider.

    Requires a client app id registered at https://api.superjob.ru/
    (sent as the ``X-api-app-id`` header). Pass it via source configuration:
    ``{"api_key": "...", "remote": true}``.
    """

    BASE_URL = "https://api.superjob.ru/2.0"
    CATALOGUE_REMOTE = 33  # "Remote work" rubric id in SuperJob catalogues
    MAX_PER_PAGE = 100

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.api_key = self.config.get("api_key")
        self.timeout = self.config.get("timeout", 30)

    def _headers(self) -> dict[str, str]:
        """Build request headers, validating that the API key is configured."""
        if not self.api_key:
            raise JobSourceError(
                "SuperJob API key is not configured. Register an app at "
                "https://api.superjob.ru/ and put it into source configuration "
                "as 'api_key'"
            )
        return {"X-api-app-id": str(self.api_key)}

    def _build_params(self, filters: dict | None, limit: int) -> dict[str, Any]:
        """Build query params from filters and source config."""
        filters = filters or {}
        params: dict[str, Any] = {
            "count": min(limit, self.MAX_PER_PAGE),
            "page": filters.get("page", 0),
        }
        if filters.get("text"):
            params["keywords[]"] = filters["text"]
        if filters.get("town") or self.config.get("town"):
            params["town"] = filters.get("town") or self.config.get("town")

        catalogues = list(self.config.get("catalogues", []))
        catalogues += [c for c in filters.get("catalogues", []) if c not in catalogues]
        remote = filters.get("remote", self.config.get("remote", False))
        if remote and self.CATALOGUE_REMOTE not in catalogues:
            catalogues.append(self.CATALOGUE_REMOTE)
        if catalogues:
            params["catalogues[]"] = catalogues
        return params

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list[RawJob]:
        """Fetch vacancies from SuperJob search."""
        params = self._build_params(filters, limit)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/vacancies/", headers=self._headers(), params=params
                )
                response.raise_for_status()
                data = response.json()

                objects = data.get("objects", [])
                jobs = [self._parse_vacancy(o) for o in objects if isinstance(o, dict)]
                logger.info(f"Fetched {len(jobs)} jobs from SuperJob")
                return jobs

        except httpx.HTTPError as e:
            logger.error(f"Error fetching jobs from SuperJob: {e}")
            raise

    async def get_job_details(self, external_id: str) -> RawJob:
        """Fetch a single vacancy by id."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/vacancies/{external_id}/", headers=self._headers()
                )
                response.raise_for_status()
                return self._parse_vacancy(response.json())

        except httpx.HTTPError as e:
            logger.error(f"Error fetching SuperJob vacancy {external_id}: {e}")
            raise

    def _parse_vacancy(self, data: dict[str, Any]) -> RawJob:
        """Parse a SuperJob vacancy object into RawJob (tolerant to missing fields)."""
        candidat = data.get("candidat") or {}
        description_parts = [
            candidat.get("requirements") or "",
            candidat.get("liability") or "",
            data.get("vacancy_text") or "",
            data.get("work") or "",
        ]
        description = "\n".join(str(p).strip() for p in description_parts if p)

        published_at = None
        timestamp = data.get("date_published")
        if timestamp:
            try:
                published_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
            except (ValueError, TypeError, OSError):
                pass

        currency = data.get("currency")
        currency = _CURRENCY_MAP.get(str(currency).lower(), str(currency).upper()) if currency else None
        employment_type = _EMPLOYMENT_MAP.get(
            str((data.get("type_of_work") or {}).get("title") or "").lower()
        )
        work_format = _WORK_FORMAT_MAP.get(
            str((data.get("place_of_work") or {}).get("title") or "").lower()
        )

        return RawJob(
            external_id=str(data["id"]),
            title=str(data.get("profession") or "Untitled"),
            company=str(data.get("firm_name") or "Unknown"),
            description=description or str(data.get("profession") or " "),
            url=str(data.get("link") or ""),
            location=(data.get("town") or {}).get("name"),
            salary_min=data.get("payment_from") or None,
            salary_max=data.get("payment_to") or None,
            currency=currency,
            employment_type=employment_type,
            work_format=work_format,
            published_at=published_at,
            raw_data=data,
        )
