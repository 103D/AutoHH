#!/usr/bin/env python3
"""Create candidate profile manually from Resume.md (no AI parsing)."""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_engine
from app.core.exceptions import NotFoundError
from app.repositories.candidate import CandidateRepository
from app.schemas.candidate import CandidateProfileCreate, CandidateProfileUpdate
from app.services.candidate import CandidateService

DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-100000000001")


async def create_profile_manually():
    """Create candidate profile with data from Resume.md."""
    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        try:
            # Read resume text
            resume_path = Path(__file__).parent.parent.parent / "Resume.md"
            resume_text = resume_path.read_text(encoding="utf-8")

            # Manual profile data from Resume.md
            profile_data = {
                "desired_positions": ["Аналитик данных", "BI-аналитик"],
                "skills": [
                    "SQL", "PostgreSQL", "Python", "pandas", "Power BI", "MS Excel",
                    "ETL", "Data Cleaning", "Data Visualization", "KPI Analysis",
                    "Statistical Analysis System", "Business Analysis", "Retail Analytics", "Git"
                ],
                "technologies": {
                    "databases": ["PostgreSQL"],
                    "languages": ["Python", "SQL"],
                    "tools": ["Power BI", "MS Excel", "Git"],
                    "libraries": ["pandas"]
                },
                "experience_years": 2,
                "experience_level": "junior",
                "education": [
                    {
                        "institution": "IITU",
                        "year": 2025,
                        "degree": "неоконченное высшее",
                        "field": "Информационной технологии, Компьютерные науки"
                    }
                ],
                "languages": {"ru": "native", "en": "C1", "kk": "C1"},
                "location": "Алматы",
                "work_formats": ["remote", "office"],
                "employment_types": ["full_time"],
                "desired_salary_min": None,
                "desired_salary_max": None,
                "salary_currency": "KZT",
                "relocation_possible": False,
                "business_trips_acceptable": True,
                "additional_preferences": {
                    "name": "Муллахимов Дияр",
                    "email": "diar20190529@gmail.com",
                    "phone": "+7 (708) 1070368",
                    "telegram": "@petkaphollin",
                    "specializations": ["BI-аналитик", "аналитик данных"],
                    "summary": "Data Analyst с 2+ годами коммерческого опыта в retail-аналитике"
                },
                "resume_versions": {"original": resume_text}
            }

            service = CandidateService(CandidateRepository(session))
            try:
                existing = await service.get_profile_by_user(DEFAULT_USER_ID)
            except NotFoundError:
                existing = None

            if existing:
                print(f"Profile already exists: {existing.id} - updating")
                update = CandidateProfileUpdate(**profile_data)
                await service.update_profile(existing.id, update)
                profile_id = existing.id
            else:
                print("Creating new profile")
                created = await service.create_profile(
                    CandidateProfileCreate(user_id=DEFAULT_USER_ID, **profile_data)
                )
                profile_id = created.id

            await session.commit()

            print("\n=== Candidate profile created ===")
            print(f"Profile ID: {profile_id}")
            print(f"Positions: {', '.join(profile_data['desired_positions'])}")
            print(f"Experience: {profile_data['experience_years']} years")
            print(f"Skills: {', '.join(profile_data['skills'][:5])}...")
            print(f"Resume stored: {len(resume_text)} chars")

        except Exception as e:
            await session.rollback()
            print(f"Error: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(create_profile_manually())
