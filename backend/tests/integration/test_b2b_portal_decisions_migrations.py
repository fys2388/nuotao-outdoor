"""PostgreSQL migration round-trip tests for B2B portal quote decisions."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from tests.integration.conftest import run_alembic


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )


async def _column_exists(
    conn: asyncpg.Connection,
    table: str,
    column: str,
) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = $1
                  AND column_name = $2
            )
            """,
            table,
            column,
        )
    )


@pytest.mark.asyncio
async def test_b2b_portal_decision_migration_upgrade_downgrade_upgrade(
    pg_database_url: str,
) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0041")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0041"
        assert not await _column_exists(conn, "b2b_quotes", "accepted_by")
        assert not await _column_exists(conn, "b2b_quotes", "rejected_by")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0042")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0042"
        assert await _column_exists(conn, "b2b_quotes", "accepted_by")
        assert await _column_exists(conn, "b2b_quotes", "rejected_by")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0041")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0041"
        assert not await _column_exists(conn, "b2b_quotes", "accepted_by")
        assert not await _column_exists(conn, "b2b_quotes", "rejected_by")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0042")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0042"
        assert await _column_exists(conn, "b2b_quotes", "accepted_by")
        assert await _column_exists(conn, "b2b_quotes", "rejected_by")
    finally:
        await conn.close()
