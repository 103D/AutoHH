#!/usr/bin/env python3
"""Initialize candidate profile from a resume text file.

Parses the resume (default: first.txt in the repository root) with AI, creates
the candidate_profiles record and stores the original resume text as
resume_versions["original"].

Usage:
    python scripts/init_candidate.py                     # use first.txt
    python scripts/init_candidate.py path/to/resume.txt  # custom resume file
    python scripts/init_candidate.py --salary-min 400000 --salary-max 700000
"""

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_engine
from app.core.exceptions import NotFoundError
from app.core.logging import setup_logging
from app.repositories.candidate import CandidateRepository
from app.schemas.candidate import CandidateProfileCreate, CandidateProfileUpdate
from app.services.candidate import CandidateService
from app.services.resume_parser import ResumeParserService

# Single-user setup: fixed user id for the main candidate
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-100000000001")
DEFAULT_RESUME_PATH = Path(__file__).parent.parent.parent / "first.txt"


async def init_candidate(
    resume_path: Path,
    user_id: uuid.UUID,
    salary_min: int | None,
    salary_max: int | None,
) -> None:
    """Parse resume file and create/update the candidate profile."""
    engine = get_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            resume_text = resume_path.read_text(encoding="utf-8")

            parser = ResumeParserService()
            print(f"Parsing resume: {resume_path}")
            parsed = await parser.parse_file(resume_path)
            profile_data = parser.to_profile_data(
                parsed, salary_min=salary_min, salary_max=salary_max
            )

            # Keep only real resume versions here; parse metadata goes to
            # additional_preferences so the API doesn't treat it as a resume
            existing_versions: dict = {}
            profile_data["additional_preferences"] = {
                "parsed_at": datetime.now(UTC).isoformat(),
                "parsed_from": resume_path.name,
                "full_name": parsed.full_name,
                "summary": parsed.summary,
            }

            service = CandidateService(CandidateRepository(session))
            try:
                existing = await service.get_profile_by_user(user_id)
            except NotFoundError:
                existing = None

            if existing:
                print(f"Profile already exists: {existing.id} - updating fields")
                existing_versions = dict(existing.resume_versions or {})
                existing_versions.setdefault("original", resume_text)
                profile_data["resume_versions"] = existing_versions
                update = CandidateProfileUpdate(**profile_data)
                await service.update_profile(existing.id, update)
                profile_id = existing.id
            else:
                profile_data["resume_versions"] = {"original": resume_text}
                created = await service.create_profile(
                    CandidateProfileCreate(user_id=user_id, **profile_data)
                )
                profile_id = created.id

            await session.commit()

            print("\n=== Candidate profile initialized ===")
            print(f"Profile ID:         {profile_id}")
            print(f"User ID:            {user_id}")
            print(f"Name:               {parsed.full_name or 'n/a'}")
            print(f"Positions:          {', '.join(parsed.desired_positions)}")
            print(f"Experience:         {parsed.experience_years} years "
                  f"({parsed.experience_level})")
            print(f"Skills:             {', '.join(parsed.skills)}")
            print(f"Location:           {parsed.location or 'n/a'}")
            print(f"Work formats:       {', '.join(parsed.work_formats) or 'n/a'}")
            print(f"Employment types:   {', '.join(parsed.employment_types) or 'n/a'}")
            print(f"Languages:          {parsed.languages}")
            print(f"Salary:             {profile_data['desired_salary_min']} - "
                  f"{profile_data['desired_salary_max']} "
                  f"{profile_data['salary_currency']}")
            print(f"Resume 'original':  stored ({len(resume_text)} chars)")

        except Exception as e:
            await session.rollback()
            print(f"Error: {e}")
            raise


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize candidate profile from a resume text file"
    )
    parser.add_argument(
        "resume",
        nargs="?",
        default=None,
        help="Path to resume text file (default: first.txt in repository root)",
    )
    parser.add_argument(
        "--salary-min",
        type=int,
        default=None,
        help="Override desired salary minimum (resume has no salary by default)",
    )
    parser.add_argument(
        "--salary-max",
        type=int,
        default=None,
        help="Override desired salary maximum (resume has no salary by default)",
    )
    parser.add_argument(
        "--user-id",
        type=uuid.UUID,
        default=DEFAULT_USER_ID,
        help=f"User ID for the profile (default: {DEFAULT_USER_ID})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    setup_logging()
    args = parse_args()
    resume_file = Path(args.resume) if args.resume else DEFAULT_RESUME_PATH
    asyncio.run(init_candidate(resume_file, args.user_id, args.salary_min, args.salary_max))
