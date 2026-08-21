import os

import pytest

# Set test environment variables before importing app
os.environ["DATABASE_URL"] = "postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["AI_API_KEY"] = "test_key"


@pytest.fixture(autouse=True)
async def reset_db_engine():
    """Reset database engine before and after each test to avoid event loop issues.

    The global engine in app.core.database is created lazily and binds to
    the event loop of the first call. pytest-asyncio creates a new loop
    per test, so we must reset the engine to ensure it re-creates in the
    current loop.
    """
    from app.core.database import reset_engine

    reset_engine()
    yield
    reset_engine()


# Database fixtures are optional, not autouse
@pytest.fixture(scope="function")
async def db_session():
    """Create a fresh database session for each test with transaction rollback.
    This fixture is only used by integration tests; unit tests should not depend on it.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.models.base import Base

    # Create test engine
    test_engine = create_async_engine(
        str(settings.database_url),
        echo=False,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )

    # Create tables if they don't exist
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Provide session
    async with async_session() as session:
        yield session

    # Cleanup
    await test_engine.dispose()


@pytest.fixture(scope="function")
async def cleanup_db(db_session):
    """Clean up database after test; only used by integration tests."""
    from sqlalchemy import text

    yield

    try:
        await db_session.execute(text("TRUNCATE TABLE candidate_profiles CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE job_sources CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE jobs CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE match_results CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE notification_logs CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE applications CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE application_status_history CASCADE;"))
        await db_session.commit()
    except Exception:
        await db_session.rollback()
        # ignore missing tables
