import os
import subprocess
import sys
from pathlib import Path

import pytest

# Set test environment variables before importing app
os.environ["DATABASE_URL"] = "postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["AI_API_KEY"] = "test_key"
# Keep unit tests hermetic: no Redis dependency in the LLM cache path
# (individual cache tests opt back in via monkeypatch on settings).
os.environ["LLM_CACHE_ENABLED"] = "false"


@pytest.fixture(scope="session")
def migrate_test_database():
    """Apply the real Alembic chain before integration tests run.

    ``Base.metadata.create_all`` is not a migration engine: it cannot add new
    columns to existing tables and previously allowed the test database to
    drift away from production. A clean CI database upgrades from the base;
    an inconsistent unstamped database fails explicitly instead of being
    silently patched.
    """
    database_url = os.environ["DATABASE_URL"]
    assert "test" in database_url.lower(), "Refusing to migrate a non-test database"
    backend_root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env=os.environ.copy(),
        check=True,
    )


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
async def db_session(migrate_test_database):
    """Create a fresh database session for each test with transaction rollback.
    This fixture is only used by integration tests; unit tests should not depend on it.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    # Create test engine
    test_engine = create_async_engine(
        str(settings.database_url),
        echo=False,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
    )

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

    async def truncate_all() -> None:
        assert "test" in str(os.environ["DATABASE_URL"]).lower(), (
            "Refusing to clean a non-test database"
        )
        await db_session.execute(text("TRUNCATE TABLE candidate_profiles CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE resume_profiles CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE job_sources CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE jobs CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE match_results CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE notification_logs CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE applications CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE application_status_history CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE hh_accounts CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE hh_resumes CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE hh_negotiations CASCADE;"))
        await db_session.execute(text("TRUNCATE TABLE hh_apply_attempts CASCADE;"))
        await db_session.commit()

    try:
        await truncate_all()
    except Exception:
        await db_session.rollback()
        # ignore missing tables

    yield

    try:
        await truncate_all()
    except Exception:
        await db_session.rollback()
        # ignore missing tables
