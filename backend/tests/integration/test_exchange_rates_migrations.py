"""PostgreSQL migration round-trip tests for audit exchange rates."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from tests.integration.conftest import run_alembic


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
            )
            """,
            table,
        )
    )


async def _constraint_exists(
    conn: asyncpg.Connection,
    table: str,
    constraint: str,
) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = $1::regclass AND conname = $2
            )
            """,
            table,
            constraint,
        )
    )


async def _index_exists(
    conn: asyncpg.Connection,
    table: str,
    index: str,
) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = $1
                  AND indexname = $2
            )
            """,
            table,
            index,
        )
    )


@pytest.mark.asyncio
async def test_exchange_rates_migration_upgrade_downgrade_upgrade(
    pg_database_url: str,
) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0040")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0040"
        assert not await _table_exists(conn, "exchange_rates")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0041")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0041"
        assert await _table_exists(conn, "exchange_rates")
        assert await _constraint_exists(
            conn,
            "exchange_rates",
            "uq_exchange_rates_workspace_pair_date",
        )
        assert await _constraint_exists(
            conn,
            "exchange_rates",
            "ck_exchange_rates_positive",
        )
        assert await _index_exists(
            conn,
            "exchange_rates",
            "ix_exchange_rates_workspace_pair_date",
        )
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0040")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0040"
        assert not await _table_exists(conn, "exchange_rates")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0041")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0041"
        assert await _table_exists(conn, "exchange_rates")
    finally:
        await conn.close()
