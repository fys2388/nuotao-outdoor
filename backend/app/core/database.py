"""Async SQLAlchemy engine, session factory and declarative base."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
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


# The engine and session factory are created LAZILY (on first attribute access
# via module __getattr__), not at import time. This lets Alembic import the
# models (to populate Base.metadata) without triggering FastAPI's engine
# creation: previously the module-level ``create_async_engine`` raised
# "loaded 'psycopg2' is not async" whenever the application DATABASE_URL used
# a non-async driver (e.g. plain ``postgresql://``), breaking the Alembic CLI
# before any migration could run. Deferring creation to first real use
# (get_db, scripts, workers) preserves FastAPI runtime behaviour while making
# the model import side-effect free.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
# Declared so static analysis (ruff) treats it as a defined module name; it is
# resolved lazily via __getattr__ (no real value is bound at import time).
async_session_factory: async_sessionmaker[AsyncSession]


def _get_engine() -> AsyncEngine:
    """Create (once) and return the shared async engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            **_build_engine_options(get_settings().database_url),
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create (once) and return the shared async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


def __getattr__(name: str):
    """PEP 562: lazily resolve ``_engine`` / ``async_session_factory``.

    ``Base`` is a normal module attribute and is resolved without triggering
    engine creation; only an explicit access to ``_engine`` or
    ``async_session_factory`` (e.g. ``from app.core.database import _engine``,
    ``async_session_factory()``) creates the engine on first use.
    """
    if name == "_engine":
        return _get_engine()
    if name == "async_session_factory":
        return _get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async database session.

    The session is always closed, even when the handler raises.
    """
    async with _get_session_factory()() as session:
        yield session
