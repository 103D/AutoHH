from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker, get_engine
from app.repositories.candidate import CandidateRepository
from app.services.candidate import CandidateService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session."""
    engine = get_engine()
    session_factory = async_session_maker.__class__(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_candidate_service(session: AsyncSession) -> CandidateService:
    """Dependency for candidate service."""
    repository = CandidateRepository(session)
    return CandidateService(repository)
