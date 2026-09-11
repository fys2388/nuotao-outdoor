"""Health check endpoints.

- ``GET /healthz``: liveness - the process is up (no external dependencies).
- ``GET /readyz``: readiness - PostgreSQL and Redis are reachable.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["health 健康检查"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]


@router.get("/healthz", summary="存活检查 / Liveness probe")
async def healthz() -> dict[str, str]:
    """返回 OK 表示进程存活；不访问任何外部服务。 / Return OK when the process is alive; never touches external services."""
    return {"status": "ok"}


@router.get("/readyz", summary="就绪检查 / Readiness probe")
async def readyz(
    db: DbSession,
    redis_client: RedisClient,
) -> dict[str, Any]:
    """Return service readiness by probing PostgreSQL and Redis.

    A degraded status is reported (with per-dependency details) instead of a
    500, so external probes can decide how to handle partial failures.
    """
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"

    healthy = all(value == "ok" for value in checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }
