import os
import pytest

# Set test environment variables before importing app
os.environ["DATABASE_URL"] = "postgresql+asyncpg://jobhunter:password@localhost:5432/jobhunter_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["AI_API_KEY"] = "test_key"

@pytest.fixture(scope="function", autouse=True)
async def cleanup_db():
    """Clean up database between tests."""
    from sqlalchemy import text
    from app.core.database import async_session_maker
    
    yield
    
    # Truncate all tables after each test
    async with async_session_maker() as session:
        await session.execute(text("TRUNCATE TABLE candidate_profiles CASCADE;"))
        await session.commit()