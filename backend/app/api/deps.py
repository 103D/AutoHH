from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.repositories.candidate import CandidateRepository
from app.services.candidate import CandidateService

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def get_candidate_service(session: AsyncSession) -> CandidateService:
    """Dependency for candidate service."""
    repository = CandidateRepository(session)
    return CandidateService(repository)