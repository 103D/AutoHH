from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core import setup_logging
from app.core.config import settings
from app.core.logging import get_logger, set_request_id

logger = get_logger(__name__)


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


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Attach a correlation id to the request and log a structured summary."""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    set_request_id(request_id)
    start = perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "operation": "http_request",
            },
        )
        return response
    finally:
        set_request_id(None)

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


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus scrape endpoint (task spec #22)."""
    from fastapi import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    from app.core.metrics import metrics_enabled

    if not metrics_enabled():
        return Response(status_code=404)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
