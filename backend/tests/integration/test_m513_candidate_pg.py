"""M5.13 Product Candidate Source Correction - real PostgreSQL integration.

Validates the M5.13 DDL (products.candidate_status + woocommerce_draft_payloads)
against a real PostgreSQL engine (embedded pgserver), drills 0024
downgrade/upgrade, proves the activation gate passes with a Product Candidate
(no WooCommerce product), and runs the full candidate -> winner -> promote ->
human approval -> draft payload chain on real PostgreSQL.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import run_alembic

WORKSPACE = UUID("10000000-0000-0000-0000-000000000001")
OTHER_WORKSPACE = UUID("20000000-0000-0000-0000-000000000001")


async def _connect(url: str) -> asyncpg.Connection:
    return await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1))


# --------------------------------------------------------------------------- #
# 1. 0024 downgrade/upgrade drill on real PostgreSQL
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_0024_downgrade_upgrade_drill(pg_database_url: str) -> None:
    """0023 -> 0024 -> 0023 -> 0024 keeps data and schema consistent."""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0023")
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0024")

    conn = await _connect(pg_database_url)
    try:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0024"
        # candidate_status exists and is nullable.
        row = await conn.fetchrow(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name='products' AND column_name='candidate_status'"
        )
        assert row is not None
        assert row[1] == "YES"
        # WooCommerce draft payload table exists.
        table = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables WHERE table_name='woocommerce_draft_payloads'"
        )
        assert table == 1
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0023")
    conn = await _connect(pg_database_url)
    try:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0023"
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='products' AND column_name='candidate_status'"
        )
        assert row is None
        table = await conn.fetchval(
            "SELECT 1 FROM information_schema.tables WHERE table_name='woocommerce_draft_payloads'"
        )
        assert table is None
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "head")
    conn = await _connect(pg_database_url)
    try:
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0024"
    finally:
        await conn.close()


# --------------------------------------------------------------------------- #
# 2. Activation gate: candidate source passes without WooCommerce
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_activation_gate_real_products_candidate_source(pg_migrated: str) -> None:
    """A 1688 Product Candidate satisfies the gate (real_product_source=candidate)."""
    from app.core.config import get_settings
    from app.pilot import activation_gate

    engine = create_async_engine(pg_migrated)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO products (id, workspace_id, sku, name, status, "
                "candidate_status, source, source_url) "
                "VALUES (:id, :ws, :sku, :name, 'candidate', 'candidate', "
                "'intake', :url)"
            ),
            {
                "id": UUID("30000000-0000-0000-0000-000000000101"),
                "ws": WORKSPACE,
                "sku": "1688-CAND-1",
                "name": "Real 1688 Candidate",
                "url": "https://detail.1688.com/offer/123456789.html",
            },
        )
        await session.commit()

    settings = get_settings()
    original_url = settings.database_url
    settings.database_url = pg_migrated
    try:
        checks = await activation_gate._db_gate_checks(WORKSPACE, settings)  # noqa: SLF001
    finally:
        settings.database_url = original_url
    await engine.dispose()

    assert checks["real_products"]["status"] == "PASS", checks["real_products"]["detail"]
    assert "candidate" in checks["real_products"]["detail"]


@pytest.mark.asyncio
async def test_activation_gate_blocked_without_products(pg_migrated: str) -> None:
    """With no candidate and no commerce product the gate stays BLOCKED."""
    from app.core.config import get_settings
    from app.pilot import activation_gate

    settings = get_settings()
    original_url = settings.database_url
    settings.database_url = pg_migrated
    try:
        checks = await activation_gate._db_gate_checks(WORKSPACE, settings)  # noqa: SLF001
    finally:
        settings.database_url = original_url

    assert checks["real_products"]["status"] == "BLOCKED"
    assert "BLOCKED_REAL_PRODUCT" in checks["real_products"]["detail"]


# --------------------------------------------------------------------------- #
# 3. Full candidate -> winner -> promote chain on real PostgreSQL
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_candidate_promote_chain_real_postgres(pg_migrated: str) -> None:
    """Intake -> winner -> promote approval -> approve -> draft payload (real PG)."""
    from decimal import Decimal

    from app.schemas.product_intelligence import ProductIntakeRequest
    from app.services import product_intelligence as pi

    engine = create_async_engine(pg_migrated)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        data = ProductIntakeRequest(
            title="PG Camping Headlamp",
            sku="PG-HEADLAMP-001",
            source_type="1688",
            source_url="https://detail.1688.com/offer/987654321.html",
            purchase_cost=Decimal("10.00"),
            domestic_shipping=Decimal("1.00"),
            first_leg_shipping=Decimal("2.00"),
            last_leg_shipping=Decimal("3.00"),
            weight_kg=Decimal("0.30"),
            dimensions={"length": 8, "width": 5, "height": 4},
        )
        result = await pi.intake_product(
            session, workspace_id=WORKSPACE, data=data, trace_id="t-pg-1"
        )
        product_id = result.product.id
        assert result.product.candidate_status == "candidate"

        for status_name in ("approved", "testing", "winner"):
            await pi.update_candidate_status(
                session,
                workspace_id=WORKSPACE,
                product_id=product_id,
                new_status=status_name,
                actor="ops-a",
                trace_id="t-pg-1",
            )
        winner = (
            await session.execute(
                text("SELECT candidate_status FROM products WHERE id = :id"),
                {"id": product_id},
            )
        ).scalar_one()
        assert winner == "winner"

        approval = await pi.request_promote(
            session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            actor="ops-a",
            trace_id="t-pg-1",
        )
        assert approval.approval_type == "PRODUCT_CANDIDATE"
        assert approval.status == "pending"

        draft = await pi.finalize_promote(
            session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            actor="ops-a",
            trace_id="t-pg-1",
        )
        assert draft.status == "generated"
        assert draft.payload["metadata"]["source_type"] == "1688"
        assert draft.payload["metadata"]["product_id"] == str(product_id)
        assert draft.payload["metadata"]["trace_id"] == "t-pg-1"
        await session.commit()
    await engine.dispose()
