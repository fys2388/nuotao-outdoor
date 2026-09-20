"""PostgreSQL round-trip tests for Agent business-scope migration 0040."""

from __future__ import annotations

import asyncio

import asyncpg

from tests.integration.conftest import run_alembic


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )


async def _column(
    conn: asyncpg.Connection,
    table: str,
    column: str,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT column_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
          AND column_name = $2
        """,
        table,
        column,
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


async def _assert_scope_schema(conn: asyncpg.Connection) -> None:
    scoped_tables = (
        "agents",
        "agent_tasks",
        "agent_executions",
        "agent_tools",
        "agent_execution_policies",
        "agent_budget_policies",
        "agent_versions",
        "agent_approval_roles",
        "agent_approvals",
    )
    for table in scoped_tables:
        column = await _column(conn, table, "business_scope")
        assert column is not None, table
        assert column["is_nullable"] == "NO"
        assert "SHARED" in str(column["column_default"])

    assert await _constraint_exists(conn, "agents", "ck_agents_business_scope")
    assert await _constraint_exists(conn, "agent_tasks", "ck_agent_tasks_business_scope")
    assert await _constraint_exists(
        conn,
        "agent_approvals",
        "ck_agent_approvals_business_scope",
    )
    assert await _index_exists(
        conn,
        "agent_executions",
        "ix_agent_executions_workspace_business_scope",
    )
    assert await _constraint_exists(
        conn,
        "agent_execution_policies",
        "uq_agent_exec_pol_ws_agent_scope_ver",
    )
    assert await _constraint_exists(
        conn,
        "agent_budget_policies",
        "uq_agent_budget_pol_ws_agent_scope_ver",
    )


async def test_agent_business_scope_upgrade_downgrade_upgrade(
    pg_database_url: str,
) -> None:
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0039")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0039"
        assert await _column(conn, "agents", "business_scope") is None
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0040")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0040"
        await _assert_scope_schema(conn)
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0039")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0039"
        assert await _column(conn, "agents", "business_scope") is None
        assert await _constraint_exists(
            conn,
            "agent_execution_policies",
            "uq_agent_exec_pol_ws_agent_ver",
        )
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0040")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0040"
        await _assert_scope_schema(conn)
    finally:
        await conn.close()
