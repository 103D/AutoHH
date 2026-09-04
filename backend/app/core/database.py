from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Create or return existing async engine (lazy initialization).

    The engine is a process-wide singleton bound to the event loop of its
    first use. Safe consumers:
    - the FastAPI app (a single event loop per process);
    - async Celery workers (one loop per worker process);
    - sync Celery workers that call ``asyncio.run()`` per task MUST recreate
      the engine per loop (``reset_engine()`` then ``get_engine()``) or use a
      ``NullPool`` engine: sharing pooled asyncpg connections across event
      loops fails with "attached to a different loop".

    ``SourceFetchPipeline`` accepts an injected ``session_factory`` so tests
    (and exotic runtimes) can bypass this singleton entirely.
    """
    global _engine

    if _engine is None:
        if not settings.database_url:
            raise ValueError("DATABASE_URL not configured")

        _engine = create_async_engine(
            str(settings.database_url),
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    return _engine


def reset_engine() -> None:
    """Reset engine (useful for testing)."""
    global _engine
    _engine = None


async_session_maker = async_sessionmaker(
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
