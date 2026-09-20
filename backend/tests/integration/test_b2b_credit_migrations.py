"""PostgreSQL migration round-trip tests for B2B credit risk and insurance."""

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
                WHERE table_schema = 'public'
                  AND table_name = $1
            )
            """,
            table,
        )
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


async def _index_exists(conn: asyncpg.Connection, index: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = $1
            )
            """,
            index,
        )
    )


@pytest.mark.asyncio
async def test_b2b_credit_migration_upgrade_downgrade_upgrade(
    pg_database_url: str,
) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0043")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0043"
        assert not await _table_exists(conn, "b2b_credit_policies")
        assert not await _column_exists(conn, "b2b_agents", "credit_status")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0044")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0044"
        for table in (
            "b2b_credit_policies",
            "b2b_credit_risk_assessments",
            "b2b_credit_status_events",
            "b2b_credit_insurance_policies",
            "b2b_credit_insurance_claims",
        ):
            assert await _table_exists(conn, table)
        assert await _column_exists(conn, "b2b_agents", "credit_status")
        assert await _column_exists(conn, "b2b_agents", "credit_policy_id")
        assert await _index_exists(conn, "uq_b2b_credit_policy_active_workspace")
        assert await _index_exists(conn, "ix_b2b_agents_workspace_credit_status")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0043")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0043"
        assert not await _table_exists(conn, "b2b_credit_policies")
        assert not await _column_exists(conn, "b2b_agents", "credit_status")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0044")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0044"
        assert await _table_exists(conn, "b2b_credit_policies")
        assert await _column_exists(conn, "b2b_agents", "credit_status")
    finally:
        await conn.close()
