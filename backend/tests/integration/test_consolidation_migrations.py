"""PostgreSQL migration round-trip tests for brand/legal-entity consolidation."""

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


@pytest.mark.asyncio
async def test_consolidation_migration_round_trip(pg_database_url: str) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0045")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0045"
        assert not await _table_exists(conn, "brands")
        assert not await _table_exists(conn, "legal_entities")
        assert not await _column_exists(conn, "products", "brand_id")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0046")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0046"
        for table in ("legal_entities", "brands", "commerce_attributions"):
            assert await _table_exists(conn, table)
        assert await _column_exists(conn, "products", "brand_id")
        assert await _constraint_exists(
            conn,
            "commerce_attributions",
            "uq_commerce_attributions_workspace_entity",
        )
        assert await _constraint_exists(
            conn,
            "commerce_attributions",
            "ck_commerce_attributions_intercompany_counterparty",
        )
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0045")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0045"
        assert not await _table_exists(conn, "commerce_attributions")
        assert not await _table_exists(conn, "brands")
        assert not await _column_exists(conn, "products", "brand_id")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0046")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0046"
        assert await _table_exists(conn, "commerce_attributions")
    finally:
        await conn.close()
