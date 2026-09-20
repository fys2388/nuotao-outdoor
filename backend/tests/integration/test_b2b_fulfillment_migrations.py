"""PostgreSQL migration round-trip tests for B2B fulfillment."""

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
async def test_b2b_fulfillment_migration_upgrade_downgrade_upgrade(
    pg_database_url: str,
) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0038")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0038"
        assert not await _table_exists(conn, "b2b_order_fulfillments")
        assert not await _table_exists(conn, "b2b_order_fulfillment_items")
        assert not await _column_exists(conn, "shipment_records", "b2b_order_id")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0039")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0039"
        assert await _table_exists(conn, "b2b_order_fulfillments")
        assert await _table_exists(conn, "b2b_order_fulfillment_items")
        assert await _column_exists(conn, "shipment_records", "b2b_order_id")
        assert await _constraint_exists(
            conn,
            "shipment_records",
            "fk_shipment_records_b2b_order_id",
        )
        assert await _constraint_exists(
            conn,
            "b2b_order_fulfillments",
            "uq_b2b_fulfillments_workspace_order",
        )
        assert await _constraint_exists(
            conn,
            "b2b_order_fulfillment_items",
            "ck_b2b_fulfillment_item_balance",
        )
        assert await _index_exists(
            conn,
            "shipment_records",
            "ix_shipment_records_b2b_order_id",
        )
        assert await _index_exists(
            conn,
            "b2b_order_fulfillments",
            "ix_b2b_fulfillments_workspace_status",
        )
        assert await _index_exists(
            conn,
            "b2b_order_fulfillment_items",
            "ix_b2b_fulfillment_items_workspace_product",
        )
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0038")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0038"
        assert not await _table_exists(conn, "b2b_order_fulfillments")
        assert not await _table_exists(conn, "b2b_order_fulfillment_items")
        assert not await _column_exists(conn, "shipment_records", "b2b_order_id")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0039")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0039"
        assert await _table_exists(conn, "b2b_order_fulfillments")
        assert await _column_exists(conn, "shipment_records", "b2b_order_id")
    finally:
        await conn.close()
