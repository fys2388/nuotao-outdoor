"""Alembic environment: wires migrations to the app's async engine."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Drivers acceptable to the async migration engine, normalized to asyncpg.
_ASYNC_PG_DRIVER = "postgresql+asyncpg"


def _normalize_async_pg_url(url: str) -> str:
    """Normalize a database URL for the asyncpg-based migration engine.

    Uses ``sqlalchemy.engine.make_url`` (never string concatenation) so all
    URL components (credentials, host, port, database, query params) are
    preserved exactly. Only the driver is adjusted:

    - ``postgresql`` (no driver) -> ``postgresql+asyncpg``
    - ``postgresql+asyncpg``     -> unchanged
    - anything else (sqlite, psycopg2, psycopg, unknown) -> fail-closed error

    This affects only the Alembic migration engine; the FastAPI application
    (``app/core/database.py``) builds its own engine and is not touched.
    """
    parsed = make_url(url)
    drivername = parsed.drivername
    if drivername == "postgresql":
        # Replace only the driver; credentials/host/db/query are kept.
        normalized = parsed.set(drivername=_ASYNC_PG_DRIVER)
        return str(normalized)
    if drivername == _ASYNC_PG_DRIVER:
        return str(parsed)
    raise ValueError(
        f"Alembic async migrations require a PostgreSQL URL using asyncpg. "
        f"Got driver '{drivername}'. Set DATABASE_URL to a "
        f"'postgresql://... ' or 'postgresql+asyncpg://...' URL. "
        f"Refusing to fall back to a synchronous or non-PostgreSQL driver."
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    # asyncpg driver only supports async connections. For offline (--sql)
    # mode we only need the PG dialect to render SQL — no live connection.
    # Strip "+asyncpg" so context.configure can build a sync dialect stub.
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure and run migrations against a live connection."""
    # Import models lazily here — offline mode never calls this function,
    # so create_async_engine() in database.py is never triggered during
    # --sql runs, avoiding a psycopg2 dependency in the staging venv.
    import app.models  # noqa: F401  - registers models on Base.metadata
    from app.core.database import Base

    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine created for this process.

    The database URL is normalized to ``postgresql+asyncpg`` so that the
    async engine resolves the asyncpg driver deterministically, regardless
    of which synchronous PostgreSQL drivers (psycopg2/psycopg) are also
    installed in the venv. Unsupported drivers fail closed (see
    ``_normalize_async_pg_url``).
    """
    import sqlalchemy.dialects.postgresql  # noqa: F401 - ensure dialect registry loaded

    url = _normalize_async_pg_url(config.get_main_option("sqlalchemy.url"))
    # Build the engine from the normalized URL directly. async_engine_from_config
    # accepts a plain options dict, so pass the section with the normalized
    # sqlalchemy.url — this avoids any ini/section caching ambiguity.
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live database."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
