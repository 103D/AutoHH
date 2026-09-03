from typing import Any

from app.providers.jobs.base import JobSourceProvider
from app.providers.jobs.habr_career import HabrCareerProvider
from app.providers.jobs.hh_kz import HeadHunterKZProvider
from app.providers.jobs.hh_remote import HeadHunterRemoteProvider
from app.providers.jobs.manual import ManualProvider
from app.providers.jobs.remote_ok import RemoteOkProvider
from app.providers.jobs.superjob import SuperJobProvider
from app.providers.jobs.zarplata import ZarplataProvider


def create_job_provider(
    source_type: str, config: dict[str, Any] | None = None
) -> JobSourceProvider:
    """Factory for creating job source providers."""

    providers = {
        "hh_kz": HeadHunterKZProvider,
        "hh_remote": HeadHunterRemoteProvider,
        "habr_career": HabrCareerProvider,
        "zarplata": ZarplataProvider,
        "superjob": SuperJobProvider,
        "manual": ManualProvider,
        "remote_ok": RemoteOkProvider,
    }

    provider_class = providers.get(source_type)
    if not provider_class:
        raise ValueError(f"Unknown job source type: {source_type}")

    return provider_class(config)
