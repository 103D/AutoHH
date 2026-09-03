"""HeadHunter provider variant focused on remote vacancies."""

from typing import Any

from app.providers.jobs.hh_kz import HeadHunterKZProvider


class HeadHunterRemoteProvider(HeadHunterKZProvider):
    """HeadHunter provider that fetches only remote vacancies.

    Reuses the HH KZ parsing logic but forces the ``schedule=remote`` filter,
    so candidates get vacancies available from anywhere (KZ area by default).
    """

    DEFAULT_FILTERS: dict[str, Any] = {"schedule": "remote"}

    def _build_filters(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        """Merge defaults <- source config <- explicit call filters."""
        merged: dict[str, Any] = dict(self.DEFAULT_FILTERS)
        merged.update(self.config.get("filters", {}))
        merged.update(filters or {})
        return merged

    async def fetch_jobs(self, filters: dict | None = None, limit: int = 100) -> list:
        """Fetch remote jobs from HeadHunter."""
        return await super().fetch_jobs(filters=self._build_filters(filters), limit=limit)
