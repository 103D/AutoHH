from typing import Any

from app.providers.jobs.base import JobSourceProvider
from app.providers.jobs.hh_kz import HeadHunterKZProvider

def create_job_provider(source_type: str, config: dict[str, Any] | None = None) -> JobSourceProvider:
    """Factory for creating job source providers."""
    
    providers = {
        "hh_kz": HeadHunterKZProvider,
    }
    
    provider_class = providers.get(source_type)
    if not provider_class:
        raise ValueError(f"Unknown job source type: {source_type}")
    
    return provider_class(config)