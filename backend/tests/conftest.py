"""Shared pytest fixtures for the backend test suite."""

import pytest
from app.core.database import Base, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


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
    """TestClient with get_db overridden to the in-memory SQLite session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
