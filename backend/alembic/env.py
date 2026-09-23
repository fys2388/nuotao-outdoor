"""Alembic environment: wires migrations to the app's async engine."""

import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)


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
    """Run migrations using an async engine created for this process."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
