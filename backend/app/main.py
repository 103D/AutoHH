from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core import setup_logging
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    setup_logging()
    yield
    # Shutdown
    pass

app = FastAPI(
    title="Job Hunter API",
    description="AI-powered job hunting automation system",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix=settings.api_v1_prefix)

@app.get("/health")
async def health_check():
    """Health check endpoint with dependency status."""
    from sqlalchemy import text

    from app.core.database import get_engine

    db_healthy = False
    redis_healthy = False

    # Check database
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_healthy = True
    except Exception:
        pass

    # Check redis
    try:
        import redis.asyncio as redis
        if settings.redis_url:
            client = redis.from_url(str(settings.redis_url))
            await client.aclose()
            redis_healthy = True
    except Exception:
        pass

    status_val = "healthy" if (db_healthy and redis_healthy) else "degraded"

    return {
        "status": status_val,
        "version": "0.1.0",
        "database": "ok" if db_healthy else "error",
        "redis": "ok" if redis_healthy else "error",
    }
