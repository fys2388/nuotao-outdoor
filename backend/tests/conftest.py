"""Shared pytest fixtures for the backend test suite."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints.auth import get_current_user, get_current_workspace_id
from app.core.database import Base, get_db
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.main import app
from app.models.user import User
from app.schemas.user import UserResponse


@pytest.fixture()
async def db_engine():
    """In-memory SQLite engine with all models created (no external deps)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def db_session(db_engine):
    """Async session bound to the in-memory SQLite database."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture()
def client() -> TestClient:
    """TestClient for endpoints that do not need the database."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def api_client(db_session):
    """TestClient with get_db overridden to the in-memory SQLite session.

    Seeds a real, active admin User row so the procurement approval choke point
    (M4.2.0-R2) can verify the approver against the users table — the service
    layer independently loads the authenticated user and checks it is active
    with an admin/operator role. The override returns that real user id.
    """
    import hashlib

    def _hash(pw: str) -> str:
        return hashlib.sha256(pw.encode()).hexdigest()

    async def _seed_admin() -> User:
        admin = User(
            id=uuid4(),
            username="admin",
            email="admin@example.com",
            hashed_password=_hash("x"),
            role="admin",
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)
        return admin

    admin_row = asyncio.run(_seed_admin())

    async def override_get_db():
        yield db_session

    admin = UserResponse(
        id=str(admin_row.id),
        username=admin_row.username,
        email=admin_row.email,
        role=admin_row.role,
        is_active=admin_row.is_active,
        created_at=datetime.now(UTC),
    )

    def override_current_user() -> UserResponse:
        return admin

    def override_workspace_id() -> UUID:
        return DEFAULT_WORKSPACE_ID

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_current_workspace_id] = override_workspace_id
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    if app.dependency_overrides.get(get_current_user) is override_current_user:
        app.dependency_overrides.pop(get_current_user, None)
    if app.dependency_overrides.get(get_current_workspace_id) is override_workspace_id:
        app.dependency_overrides.pop(get_current_workspace_id, None)


@pytest.fixture(autouse=True)
def _default_actor_provider_body() -> None:
    """Business tests default to the body actor provider.

    Staging config sets ACTOR_PROVIDER=header in backend/.env; identity
    tests opt into the JWT/header path by explicitly setting
    ``actor_provider=header`` on the settings singleton. This fixture keeps
    the pre-M5.14 business tests (state machines, pilot, supply chain,
    runtime) running under their original body-actor semantics.
    """
    from app.core.config import get_settings

    get_settings().actor_provider = "body"
    yield


@pytest.fixture(autouse=True)
def _memory_queue_backend() -> None:
    """Force the in-memory task queue backend for all tests (no Redis)."""
    from app.core.config import get_settings
    from app.services import task_queue

    get_settings().task_queue_backend = "memory"
    task_queue.reset_queue_backend_cache()
    yield
    task_queue.reset_queue_backend_cache()


@pytest.fixture(autouse=True)
def _restore_runtime_settings() -> None:
    """Restore M5 runtime settings to their configured defaults per test.

    Runtime tests mutate the settings singleton (reclaim idle, heartbeat
    timeout, dedup TTL, ...); without a restore these leak across tests and
    change dedup/health semantics. Defaults come from a fresh Settings
    instance so cross-file leaks are repaired too.
    """
    from app.core.config import Settings, get_settings

    defaults = Settings()
    settings = get_settings()
    keys = (
        "task_queue_reclaim_idle_ms",
        "task_queue_reconcile_idle_seconds",
        "task_queue_dedup_ttl_seconds",
        "worker_heartbeat_timeout_seconds",
        "worker_heartbeat_interval_seconds",
        "worker_registry_ttl_seconds",
        # LLM gateway tests mutate these on the settings singleton; without a
        # restore the fake keys leak into readiness/other checks.
        "openai_api_key",
        "deepseek_api_key",
        "llm_provider",
        "llm_fallback_provider",
        "database_url",
        "redis_url",
    )
    yield
    for key in keys:
        setattr(settings, key, getattr(defaults, key))
