"""Tests for the health check endpoints."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app
from fastapi.testclient import TestClient


class _FakeSession:
    """Minimal stand-in for an async SQLAlchemy session."""

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeRedis:
    """Minimal stand-in for the async Redis client."""

    async def ping(self) -> bool:
        return True


def test_healthz_returns_ok(client: TestClient) -> None:
    """Liveness probe must succeed without any external dependency."""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_service_info(client: TestClient) -> None:
    """Root endpoint reports service metadata."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Nuotao AI OS"


@pytest.mark.parametrize(
    ("db_ok", "redis_ok", "expected"),
    [
        (True, True, "ok"),
        (False, True, "degraded"),
        (True, False, "degraded"),
    ],
)
def test_readyz_reflects_dependency_health(
    client: TestClient,
    db_ok: bool,
    redis_ok: bool,
    expected: str,
) -> None:
    """Readiness must report degraded when any dependency fails."""

    class FailingOrNotSession(_FakeSession):
        async def execute(self, *args: Any, **kwargs: Any) -> None:
            if not db_ok:
                raise ConnectionError("database unavailable")
            return None

    class FailingOrNotRedis(_FakeRedis):
        async def ping(self) -> bool:
            if not redis_ok:
                raise ConnectionError("redis unavailable")
            return True

    async def override_db() -> AsyncIterator[FailingOrNotSession]:
        yield FailingOrNotSession()

    async def override_redis() -> AsyncIterator[FailingOrNotRedis]:
        yield FailingOrNotRedis()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis
    try:
        response = client.get("/api/v1/readyz")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == expected
        assert body["checks"]["database"] == (
            "ok" if db_ok else "error: ConnectionError"
        )
        assert body["checks"]["redis"] == (
            "ok" if redis_ok else "error: ConnectionError"
        )
    finally:
        app.dependency_overrides.clear()
