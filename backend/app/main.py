"""Nuotao AI OS backend entrypoint.

Exposes the FastAPI application with:
- ``GET /``: service information
- ``GET /api/v1/healthz``: liveness probe (no dependencies)
- ``GET /api/v1/readyz``: readiness probe (PostgreSQL + Redis checks)
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis import create_redis_client

setup_logging()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: create the shared Redis client on startup."""
    app.state.redis = create_redis_client()
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", summary="Service information", tags=["meta"])
async def root() -> dict[str, str]:
    """Return basic service metadata for operators."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
    }
