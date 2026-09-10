from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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


async def get_current_user_id() -> UUID:
    """Resolve the acting user for account-scoped endpoints.

    Interim single-user boundary (ADR-001 milestone 1): the deployment
    configures ``DEFAULT_USER_ID`` and every HH-account query is scoped by
    it. This MUST be replaced by a real authentication dependency before any
    multi-user or internet-facing rollout (ADR-001 production gate).
    """
    return UUID(settings.default_user_id)


def get_candidate_service(session: AsyncSession) -> CandidateService:
    """Dependency for candidate service."""
    repository = CandidateRepository(session)
    return CandidateService(repository)
