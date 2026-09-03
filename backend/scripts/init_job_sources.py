#!/usr/bin/env python3
"""Initialize job sources for the career intelligence platform.

Creates job source records for all providers: HeadHunter KZ, HeadHunter
Remote, Habr Career, Zarplata, SuperJob (disabled until an API key is set)
and the manual source for hand-added vacancies (LinkedIn, referrals).

Usage:
    python scripts/init_job_sources.py
    python scripts/init_job_sources.py --with-superjob-key <API_KEY>
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_engine
from app.core.logging import setup_logging
from app.repositories.job import JobSourceRepository
from app.schemas.job import JobSourceCreate
from app.services.job import JobSourceService

SOURCES: list[dict] = [
    {
        "name": "HeadHunter_KZ",
        "type": "hh_kz",
        "enabled": True,
        "configuration": {
            "filters": {"area": "40", "text": "analyst OR python OR data"},
            "limit": 50,
            "timeout": 30,
        },
    },
    {
        "name": "HeadHunter_Remote",
        "type": "hh_remote",
        "enabled": True,
        "configuration": {
            "filters": {"area": "40", "text": "analyst OR data"},
            "limit": 50,
            "timeout": 30,
        },
    },
    {
        "name": "Habr_Career",
        "type": "habr_career",
        "enabled": True,
        "configuration": {
            "query": "data analyst",
            "remote": True,
            "limit": 50,
            "timeout": 30,
        },
    },
    {
        "name": "Zarplata",
        "type": "zarplata",
        "enabled": True,
        "configuration": {
            "query": "аналитик данных",
            "remote": False,
            "limit": 50,
            "timeout": 30,
        },
    },
    {
        "name": "RemoteOK",
        "type": "remote_ok",
        "enabled": True,
        "configuration": {
            # Optional tag filter: "python", "data", "devops", etc.
            "tag": None,
            "limit": 50,
            "timeout": 30,
        },
    },
    {
        "name": "SuperJob",
        "type": "superjob",
        # Disabled until an API key from https://api.superjob.ru/ is provided
        "enabled": False,
        "configuration": {"remote": True, "limit": 50, "timeout": 30, "api_key": None},
    },
    {
        "name": "Manual",
        "type": "manual",
        "enabled": True,
        "configuration": {"jobs": []},
    },
]

async def init_job_sources(superjob_api_key: str | None = None) -> None:
    """Create all job sources, skipping ones that already exist."""
    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            repo = JobSourceRepository(session)
            service = JobSourceService(repo)

            created_count = 0
            skipped_count = 0

            for spec in SOURCES:
                spec = dict(spec)
                configuration = dict(spec.get("configuration", {}))
                if spec["name"] == "SuperJob" and superjob_api_key:
                    configuration["api_key"] = superjob_api_key
                    spec["enabled"] = True
                spec["configuration"] = configuration

                try:
                    existing = await service.get_source_by_name(spec["name"])
                    print(f"Source already exists: {spec['name']} ({existing.id})")
                    skipped_count += 1
                    continue
                except Exception:
                    pass

                created = await service.create_source(JobSourceCreate(**spec))
                print(
                    f"Created source: {created.name} "
                    f"(id={created.id}, type={created.type}, enabled={created.enabled})"
                )
                created_count += 1

            await session.commit()
            print(f"\nDone: created={created_count}, skipped={skipped_count}")

        except Exception as e:
            await session.rollback()
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    setup_logging()
    key = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--with-superjob-key" else None
    asyncio.run(init_job_sources(key))
