"""Async SQLAlchemy engine, session factory and declarative base."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


def _build_engine_options(db_url: str) -> dict[str, object]:
    """Return engine options with connect_args appropriate for the driver.

    PostgreSQL (asyncpg) accepts ``ssl``; SQLite (aiosqlite) does not.
    Passing an unsupported kwarg to aiosqlite.connect() raises TypeError.
    """
    base = {"pool_pre_ping": True, "echo": False}
    if db_url.startswith("postgresql"):
        base["connect_args"] = {"timeout": 5, "ssl": False}
    elif db_url.startswith("sqlite"):
        base["connect_args"] = {"timeout": 5}
    return base


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine = create_async_engine(
    get_settings().database_url,
    **_build_engine_options(get_settings().database_url),
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
