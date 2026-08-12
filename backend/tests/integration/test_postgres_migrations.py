"""M5.2.1 PostgreSQL production validation (real PostgreSQL 16).

Runs the full Alembic chain (0001 -> 0021) against a real PostgreSQL server
(embedded binaries via pgserver), drills downgrade/upgrade, and proves the
constraints and isolation guarantees the schema relies on: FK, UNIQUE, JSONB,
Numeric, BIGSERIAL and workspace isolation, plus transaction-rollback
consistency for the agent task/execution/audit rows.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.integration.conftest import run_alembic


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))


async def _table_exists(conn, table: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1",
        table,
    )
    return row is not None


async def _column_type(conn, table: str, column: str) -> str | None:
    row = await conn.fetchrow(
        """
        SELECT udt_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=$1 AND column_name=$2
        """,
        table,
        column,
    )
    return row[0] if row else None


async def _fk_names(conn, table: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT conname FROM pg_constraint WHERE conrelid = $1::regclass AND contype = 'f'",
        table,
    )
    return [r[0] for r in rows]


async def _index_names(conn, table: str) -> list[str]:
    rows = await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = $1", table)
    return [r[0] for r in rows]


# --------------------------------------------------------------------------- #
# 1. Upgrade head on real PostgreSQL
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_alembic_upgrade_head_on_real_postgres(pg_migrated: str) -> None:
    """The full migration chain applies to real PostgreSQL and ends at 0021 (M5.6)."""
    conn = await _connect(pg_migrated)
    try:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0021"

        # Core brain schema tables (M1/M2)
        for table in (
            "workspaces",
            "event_log",
            "products",
            "product_cost",
            "suppliers",
            "rules",
            "rule_execution_logs",
            "ai_agent_runs",
            "product_sources",
            "product_cost_snapshots",
            "product_scores",
            "product_analysis_runs",
            "product_decisions",
            "product_ai_evaluations",
            "product_experiments",
        ):
            assert await _table_exists(conn, table), f"missing table {table}"

        # Marketing / customer / supply chain domains
        for table in (
            "campaigns",
            "creative_assets",
            "customer_feedback",
            "marketing_experiments",
            "customer_profiles",
            "product_reviews",
            "refund_cases",
            "purchase_orders",
            "inventory_snapshots",
            "shipment_records",
            "business_recommendations",
        ):
            assert await _table_exists(conn, table), f"missing table {table}"

        # M5 agent runtime tables
        for table in (
            "agents",
            "agent_tasks",
            "agent_executions",
            "agent_tools",
            "agent_memory",
            "agent_evaluations",
            "agent_execution_policies",
            "agent_budget_policies",
            "agent_retry_policies",
            "agent_task_attempts",
            "agent_metrics",
        ):
            assert await _table_exists(conn, table), f"missing table {table}"

        # M5.4 operations + M5.5 platform tables
        for table in (
            "agent_alerts",
            "agent_approvals",
            "agent_versions",
            "agent_approval_roles",
            "agent_approval_slas",
        ):
            assert await _table_exists(conn, table), f"missing table {table}"
    finally:
        await conn.close()


# --------------------------------------------------------------------------- #
# 2. Downgrade / upgrade drill (0020 -> 0019 -> 0017 -> 0012 -> head)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_downgrade_upgrade_drill_real_postgres(pg_database_url: str) -> None:
    """Downgrade drills (0020 -> 0019 -> 0017 -> 0012) then upgrade back to head."""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "head")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0021"
        assert await _column_type(conn, "agent_tasks", "idempotency_key") == "varchar"
        assert await _column_type(conn, "product_experiments", "decision_id") == "uuid"
    finally:
        await conn.close()

    # Downgrade 0021 -> 0020 drops the M5.6 experiment linkage columns.
    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0020")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0020"
        assert await _column_type(conn, "product_experiments", "decision_id") is None
        assert await _column_type(conn, "product_experiments", "hypothesis") is None
    finally:
        await conn.close()

    # Downgrade 0020 -> 0019 drops the M5.5 platform tables.
    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0019")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0019"
        assert await _table_exists(conn, "agent_versions") is False
        assert await _table_exists(conn, "agent_approval_roles") is False
        assert await _table_exists(conn, "agent_approval_slas") is False
    finally:
        await conn.close()

    # Downgrade 0019 -> 0017 drops the agent alerts + approvals tables.
    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0017")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0017"
        assert await _column_type(conn, "agent_tasks", "idempotency_key") is None
    finally:
        await conn.close()

    # Downgrade 0017 -> 0012 removes the agent runtime tables (M5.0/M5.1).
    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0012")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0012"
        assert await _table_exists(conn, "agents") is False
        assert await _table_exists(conn, "agent_execution_policies") is False
        # Supply chain domain from 0012 is still present.
        assert await _table_exists(conn, "purchase_orders") is True
    finally:
        await conn.close()

    # Upgrade back to head: everything is restored, including migration 0021.
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "head")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0021"
        assert await _table_exists(conn, "agents") is True
        assert await _table_exists(conn, "agent_metrics") is True
        assert await _table_exists(conn, "agent_versions") is True
        assert await _table_exists(conn, "agent_approval_roles") is True
        assert await _column_type(conn, "agent_tasks", "idempotency_key") == "varchar"
    finally:
        await conn.close()


# --------------------------------------------------------------------------- #
# 3. Types / constraints / workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_postgres_constraints_types_workspace_isolation(pg_migrated: str) -> None:
    """JSONB / Numeric / BIGSERIAL / UUID types + FK + UNIQUE + isolation."""
    conn = await _connect(pg_migrated)
    try:
        # JSONB columns
        assert await _column_type(conn, "event_log", "payload") == "jsonb"
        assert await _column_type(conn, "products", "attributes") == "jsonb"
        assert await _column_type(conn, "agent_executions", "context_snapshot") == "jsonb"
        # Numeric money columns
        assert await _column_type(conn, "product_cost", "total_cost") == "numeric"
        assert await _column_type(conn, "agent_metrics", "total_cost") == "numeric"
        # BIGSERIAL id (event_log.id is bigint)
        assert await _column_type(conn, "event_log", "id") == "int8"
        # UUID pk
        assert await _column_type(conn, "products", "id") == "uuid"

        # FK constraints exist on the runtime/audit tables.
        for table, expected in (
            ("agent_executions", "agent_tasks"),
            ("agent_task_attempts", "agent_tasks"),
            ("product_cost", "products"),
            ("inventory_snapshots", "products"),
            ("product_experiments", "product_decisions"),
        ):
            fks = await _fk_names(conn, table)
            assert fks, f"no FK on {table}"
            # verify the referenced table is the expected one
            row = await conn.fetchrow(
                """
                SELECT tc.table_name, ccu.table_name AS ref
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = $1 AND tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.table_name = $2
                LIMIT 1
                """,
                table,
                expected,
            )
            assert row is not None, f"{table} does not reference {expected}"

        # UNIQUE: agents (workspace_id, agent_id)
        uniques = await conn.fetch(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'agents'::regclass AND contype = 'u'
            """
        )
        assert "uq_agents_workspace_agent_id" in {r[0] for r in uniques}

        # Partial unique index on agent_tasks idempotency_key (0018).
        indexes = await _index_names(conn, "agent_tasks")
        assert "uq_agent_tasks_ws_agent_idem" in indexes

        # Workspace isolation: two workspaces, queries only see their own rows.
        ws_a = UUID("00000000-0000-0000-0000-00000000aaaa")
        ws_b = UUID("00000000-0000-0000-0000-00000000bbbb")
        await conn.execute(
            "INSERT INTO products (id, workspace_id, sku, name) VALUES "
            "($1, $2, 'SKU-A', 'Product A'), ($3, $4, 'SKU-B', 'Product B')",
            UUID("00000000-0000-0000-0000-00000000aa01"),
            ws_a,
            UUID("00000000-0000-0000-0000-00000000bb01"),
            ws_b,
        )
        count_a = await conn.fetchval("SELECT count(*) FROM products WHERE workspace_id = $1", ws_a)
        count_b = await conn.fetchval("SELECT count(*) FROM products WHERE workspace_id = $1", ws_b)
        assert count_a == 1
        assert count_b == 1

        # UNIQUE (workspace_id, sku): same sku in the same workspace fails.
        try:
            await conn.execute(
                "INSERT INTO products (id, workspace_id, sku, name) VALUES "
                "($1, $2, 'SKU-A', 'Duplicate')",
                UUID("00000000-0000-0000-0000-00000000aa02"),
                ws_a,
            )
            raise AssertionError("duplicate (workspace, sku) should violate the unique index")
        except asyncpg.exceptions.UniqueViolationError:
            pass
    finally:
        await conn.close()


# --------------------------------------------------------------------------- #
# 4. Transaction rollback consistency
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_transaction_rollback_consistency(pg_migrated: str) -> None:
    """A rolled-back transaction leaves no task/execution/audit rows behind."""
    engine = create_async_engine(pg_migrated)
    ws = UUID("00000000-0000-0000-0000-00000000cc01")
    agent_id = UUID("00000000-0000-0000-0000-00000000cc02")
    task_id = UUID("00000000-0000-0000-0000-00000000cc03")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO agents (id, workspace_id, agent_id, name, domain, "
                    "model_provider, model_name, prompt_version, permission_level, status) "
                    "VALUES (:id, :ws, 'PROD-ROLLBACK', 'Rollback Agent', 'product', "
                    "'openai', 'gpt-4o-mini', 'v1', 'L2', 'active')"
                ),
                {"id": agent_id, "ws": ws},
            )
            await conn.execute(
                text(
                    "INSERT INTO agent_tasks (id, workspace_id, agent_id, input, status) "
                    "VALUES (:id, :ws, :agent, '{}'::jsonb, 'pending')"
                ),
                {"id": task_id, "ws": ws, "agent": agent_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO agent_executions "
                    "(id, workspace_id, agent_id, task_id, context_snapshot, input, output) "
                    "VALUES (:id, :ws, :agent, :task, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)"
                ),
                {
                    "id": UUID("00000000-0000-0000-0000-00000000cc04"),
                    "ws": ws,
                    "agent": agent_id,
                    "task": task_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO agent_task_attempts "
                    "(id, workspace_id, task_id, attempt_number, status) "
                    "VALUES (:id, :ws, :task, 1, 'running')"
                ),
                {
                    "id": UUID("00000000-0000-0000-0000-00000000cc05"),
                    "ws": ws,
                    "task": task_id,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO event_log (workspace_id, event_type, entity_type, entity_id) "
                    "VALUES (:ws, 'agent.task_created', 'agent_task', :task)"
                ),
                {"ws": ws, "task": str(task_id)},
            )
            await conn.execute(text("SELECT 1/0"))  # force rollback

        raise AssertionError("transaction should have raised")
    except Exception as exc:  # noqa: BLE001 - SQLAlchemy wraps the asyncpg error
        assert "division by zero" in str(exc).lower()
    finally:
        async with engine.begin() as conn:
            for table in ("agent_task_attempts", "agent_executions", "agent_tasks", "agents"):
                result = await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE workspace_id = :ws"), {"ws": ws}
                )
                assert result.scalar_one() == 0, f"{table} leaked rows after rollback"
            result = await conn.execute(
                text("SELECT count(*) FROM event_log WHERE workspace_id = :ws"), {"ws": ws}
            )
            assert result.scalar_one() == 0
        await engine.dispose()


@pytest.mark.asyncio
async def test_fk_enforcement_on_real_postgres(pg_migrated: str) -> None:
    """agent_executions rejects a task_id that does not exist (FK)."""
    engine = create_async_engine(pg_migrated)
    ws = UUID("00000000-0000-0000-0000-00000000dd01")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO agent_executions "
                    "(id, workspace_id, agent_id, task_id, context_snapshot, input, output) "
                    "VALUES (:id, :ws, NULL, :task, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)"
                ),
                {
                    "id": UUID("00000000-0000-0000-0000-00000000dd02"),
                    "ws": ws,
                    "task": UUID("00000000-0000-0000-0000-00000000dd03"),
                },
            )
            raise AssertionError("orphan agent_execution should violate the FK")
    except Exception as exc:  # noqa: BLE001 - SQLAlchemy wraps the asyncpg error
        assert "foreign key" in str(exc).lower()
    finally:
        await engine.dispose()
