#!/usr/bin/env python3
"""Initialize HeadHunter Kazakhstan job source."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import get_engine
from app.repositories.job import JobSourceRepository
from app.schemas.job import JobSourceCreate
from app.services.job import JobSourceService
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

async def init_hh_source():
    """Initialize HeadHunter KZ source."""
    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            repo = JobSourceRepository(session)
            service = JobSourceService(repo)
            
            # Check if already exists
            try:
                existing = await service.get_source_by_name("HeadHunter_KZ")
                print(f"Source already exists: {existing.id}")
                return
            except Exception:
                pass
            
            # Create new source
            source = JobSourceCreate(
                name="HeadHunter_KZ",
                type="api",
                enabled=True,
                configuration={
                    "filters": {
                        "area": "40",  # Kazakhstan
                        "text": "analyst OR python OR data",
                    },
                    "limit": 50,
                    "timeout": 30,
                }
            )
        
            created = await service.create_source(source)
            await session.commit()
            
            print(f"Created source: {created.id}")
            print(f"Name: {created.name}")
            print(f"Type: {created.type}")
            print(f"Enabled: {created.enabled}")
            
        except Exception as e:
            await session.rollback()
            print(f"Error: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(init_hh_source())