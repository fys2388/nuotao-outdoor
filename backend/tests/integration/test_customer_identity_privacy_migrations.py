"""PostgreSQL migration round-trip tests for customer identity/privacy."""

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
async def test_customer_identity_privacy_migration_round_trip(
    pg_database_url: str,
) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0044")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0044"
        assert not await _column_exists(
            conn, "customer_accounts", "merged_into_account_id"
        )
        assert not await _table_exists(conn, "customer_identity_links")
        assert not await _table_exists(conn, "customer_consent_events")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0045")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0045"
        for table in (
            "customer_identity_links",
            "customer_account_merges",
            "customer_consent_events",
            "data_subject_requests",
            "data_subject_request_actions",
        ):
            assert await _table_exists(conn, table)
        assert await _column_exists(
            conn, "customer_accounts", "merged_into_account_id"
        )
        assert await _column_exists(conn, "orders", "customer_account_id")
        assert await _column_exists(
            conn, "email_subscriptions", "customer_account_id"
        )
        assert await _constraint_exists(
            conn,
            "customer_identity_links",
            "uq_customer_identity_links_account_identity",
        )
        assert await _constraint_exists(
            conn,
            "customer_consent_events",
            "uq_customer_consent_events_workspace_idempotency",
        )
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0044")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0044"
        assert not await _table_exists(conn, "customer_identity_links")
        assert not await _column_exists(
            conn, "customer_accounts", "merged_into_account_id"
        )
        assert not await _column_exists(conn, "orders", "customer_account_id")
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0045")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0045"
        assert await _table_exists(conn, "customer_identity_links")
        assert await _table_exists(conn, "data_subject_requests")
    finally:
        await conn.close()
