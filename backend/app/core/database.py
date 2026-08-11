"""Async SQLAlchemy engine, session factory and declarative base."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

# Fail fast on connectivity issues so readiness probes do not hang.
_ENGINE_OPTIONS: dict[str, object] = {
    "pool_pre_ping": True,
    "echo": False,
    "connect_args": {"timeout": 5},
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = create_async_engine(
    get_settings().database_url,
    **_ENGINE_OPTIONS,
)

async_session_factory = async_sessionmaker(
    _engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async database session.

    The session is always closed, even when the handler raises.
    """
    async with async_session_factory() as session:
        yield session
