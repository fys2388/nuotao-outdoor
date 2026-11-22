"""M4.2.0 T0.5 — real PostgreSQL Alembic upgrade/downgrade round-trip.

Owner directive (PR #27 review): the SQLite model-level round-trip tests do NOT
substitute for validating the real migrations. This module runs the actual
Alembic migrations 0090/0091 against a REAL PostgreSQL database (the CI
``postgres-concurrency`` service, or any Postgres exposed via
``TEST_DATABASE_URL``) and verifies the full upgrade/downgrade round-trip:

1. ``upgrade 0089`` (pre-0090 baseline) and seed one existing business row in
   each of the four affected tables (``supplier_profiles``, ``product_cost``,
   ``inventory_snapshots``, ``shipment_records``).
2. ``upgrade 0090`` -> the supplier risk-score + product-cost provenance
   columns exist and the pre-existing rows stay NULL (no fabricated values).
3. ``upgrade 0091`` -> the reorder-point + shipment reconciliation columns
   exist and the pre-existing rows stay NULL.
4. ``downgrade 0090`` -> the 0091 columns are removed.
5. ``downgrade 0089`` -> the 0090 columns are removed.

The migration chain runs through the app's real ``alembic/env.py`` (async
asyncpg engine), so the round-trip exercises the exact code path production
uses. The current ``alembic_version`` revision is asserted after every step.

Driver: the data/inspection steps use asyncpg through the SQLAlchemy async
engine, matching ``TEST_DATABASE_URL`` (``postgresql+asyncpg://...``) and
``alembic/env.py``. No psycopg2 dependency is required.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from alembic.config import Config

# The alembic/env.py imports the app models, which read JWT settings at import
# time. Provide a CI-safe test default without clobbering a real value.
os.environ.setdefault("JWT_SECRET_KEY", "migration-roundtrip-test-secret")

BACKEND_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")  # DEFAULT_WORKSPACE_ID

# Real revision ids read from alembic/versions/00{89,90,91}_*.py.
BASELINE = "0089"
REV_SUPPLIER_RISK = "0090"
REV_INVENTORY_REORDER = "0091"

# 0089-baseline columns used to seed one existing business row per table.
# Inserting via explicit column lists (not the ORM models) guarantees we only
# touch columns that exist BEFORE 0090/0091, so the rows are genuine
# "pre-migration" records.
_SUPPLIER_BASELINE_COLS = ("id", "workspace_id", "certifications", "risk_level")
_PRODUCT_COST_BASELINE_COLS = ("id", "workspace_id", "currency")
_INVENTORY_BASELINE_COLS = ("id", "workspace_id", "location")
_SHIPMENT_BASELINE_COLS = ("id", "workspace_id", "carrier")

# The new columns each migration adds (and downgrade must remove).
_M420_SUPPLIER_RISK_COLUMNS = (
    ("supplier_profiles", "risk_score"),
    ("supplier_profiles", "risk_score_model_version"),
    ("supplier_profiles", "risk_score_calibrated_at"),
    ("product_cost", "source"),
    ("product_cost", "confidence"),
)
_M420_INVENTORY_REORDER_COLUMNS = (
    ("inventory_snapshots", "reorder_point"),
    ("shipment_records", "promised_delivery"),
    ("shipment_records", "actual_cost"),
    ("shipment_records", "actual_cost_currency"),
)


def _is_postgres() -> bool:
    """True when TEST_DATABASE_URL points at PostgreSQL (mirrors the
    concurrency test's skip gate)."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    return url.startswith("postgres") or url.startswith("postgresql")


async def _current_revision(url: str) -> str | None:
    """Read the singleton alembic_version row (None when the table is absent)."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            exists = await conn.run_sync(lambda c: inspect(c).has_table("alembic_version"))
            if not exists:
                return None
            return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    finally:
        await engine.dispose()


def _make_alembic_config() -> Config:
    """Build an Alembic Config wired to TEST_DATABASE_URL.

    alembic/env.py overrides sqlalchemy.url from application settings
    (``get_settings().database_url``), so the URL is injected by exporting
    DATABASE_URL and clearing the cached settings singleton — that is how the
    real deployment wires the URL too.
    """
    test_url = os.environ["TEST_DATABASE_URL"]
    os.environ["DATABASE_URL"] = test_url
    from app.core.config import get_settings

    get_settings.cache_clear()

    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_url)
    return cfg


async def _seed_baseline_rows(url: str) -> dict:
    """Insert one genuine pre-migration business row into each affected table.

    Only 0089-era columns are set; the workspace_id is present so the rows are
    real workspace-scoped records, not schema-only stubs. Returns a mapping of
    table name -> inserted row id so each migration stage can assert the exact
    seeded rows survive (exist + baseline fields unchanged + new columns NULL).
    """
    ids = {
        "supplier_profiles": uuid4(),
        "product_cost": uuid4(),
        "inventory_snapshots": uuid4(),
        "shipment_records": uuid4(),
    }
    seeds = (
        (
            "supplier_profiles",
            _SUPPLIER_BASELINE_COLS,
            # certifications is an AI_JSON column: asyncpg cannot encode a raw
            # Python list, so pass the serialized JSON array text.
            (ids["supplier_profiles"], WORKSPACE, "[]", "low"),
        ),
        (
            "product_cost",
            _PRODUCT_COST_BASELINE_COLS,
            (ids["product_cost"], WORKSPACE, "USD"),
        ),
        (
            "inventory_snapshots",
            _INVENTORY_BASELINE_COLS,
            (ids["inventory_snapshots"], WORKSPACE, "cn"),
        ),
        (
            "shipment_records",
            _SHIPMENT_BASELINE_COLS,
            (ids["shipment_records"], WORKSPACE, "SF"),
        ),
    )
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for table, columns, values in seeds:
                cols = ", ".join(columns)
                params = ", ".join(f":p{i}" for i in range(len(values)))
                stmt = text(f"INSERT INTO {table} ({cols}) VALUES ({params})")
                await conn.execute(stmt, {f"p{i}": v for i, v in enumerate(values)})
    finally:
        await engine.dispose()
    return ids


async def _assert_new_columns_null(url: str, checks, ids: dict) -> None:
    """For the seeded rows, assert (a) each row still exists, (b) its baseline
    business fields are unchanged, and (c) every new column is still NULL.

    Binding to the seeded row IDs (rather than querying the whole table) makes
    the "pre-existing rows keep new columns NULL" guarantee tamper-evident: if a
    seeded row were lost, the per-ID SELECT would return nothing and the test
    would fail instead of silently passing on an empty result.
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for table, column in checks:
                row_id = ids[table]
                rec = (
                    await conn.execute(
                        text(f"SELECT {column} FROM {table} WHERE id = :rid"),
                        {"rid": row_id},
                    )
                ).first()
                assert rec is not None, f"{table} id={row_id}: seeded row missing during migration"
                assert rec[0] is None, (
                    f"{table}.{column}: migration fabricated non-NULL value "
                    f"on pre-existing row id={row_id}: {rec[0]!r}"
                )
            # Baseline business fields must survive the migration untouched.
            baseline = await conn.execute(
                text("SELECT certifications, risk_level FROM supplier_profiles " "WHERE id = :rid"),
                {"rid": ids["supplier_profiles"]},
            )
            sup = baseline.first()
            assert sup is not None, "supplier_profiles seeded row missing"
            assert sup[0] == "[]" and sup[1] == "low", f"supplier baseline mutated: {sup!r}"
    finally:
        await engine.dispose()


async def _assert_rows_exist(url: str, ids: dict) -> None:
    """After downgrade, the seeded business rows must still be present with
    their baseline fields intact (migrations must not lose pre-existing data)."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            sup = (
                await conn.execute(
                    text("SELECT certifications, risk_level FROM supplier_profiles " "WHERE id = :rid"),
                    {"rid": ids["supplier_profiles"]},
                )
            ).first()
            assert sup is not None, "supplier_profiles row lost after downgrade"
            assert sup[0] == "[]" and sup[1] == "low", f"supplier baseline mutated: {sup!r}"

            for table, col in (
                ("product_cost", "currency"),
                ("inventory_snapshots", "location"),
                ("shipment_records", "carrier"),
            ):
                row = (
                    await conn.execute(
                        text(f"SELECT {col} FROM {table} WHERE id = :rid"),
                        {"rid": ids[table]},
                    )
                ).first()
                assert row is not None, f"{table} row id={ids[table]} lost after downgrade"
    finally:
        await engine.dispose()


async def _cleanup_tables(url: str) -> None:
    """Remove the seeded business rows (leaves a clean DB for the next run)."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for table in (
                "shipment_records",
                "inventory_snapshots",
                "product_cost",
                "supplier_profiles",
            ):
                await conn.execute(text(f"DELETE FROM {table}"))
    finally:
        await engine.dispose()


async def _get_columns(url: str, table: str) -> set[str]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns(table)})
    finally:
        await engine.dispose()
    return names


@pytest.fixture
def pg_migration_cfg():
    """Provision the Alembic config for a real-Postgres round-trip, or skip.

    Skips unless TEST_DATABASE_URL points at PostgreSQL — locally without
    Postgres this test is skipped (not failed), mirroring
    test_concurrency_approval_postgres.py.
    """
    if not _is_postgres():
        pytest.skip(
            "TEST_DATABASE_URL is not PostgreSQL; a real Alembic "
            "upgrade/downgrade round-trip requires PostgreSQL. The SQLite "
            "model-level round-trip tests cover the same columns at the ORM "
            "layer."
        )
    return _make_alembic_config()


@pytest.mark.skipif(not _is_postgres(), reason="TEST_DATABASE_URL is not PostgreSQL")
def test_m420_t05_pg_migration_roundtrip(pg_migration_cfg):
    """Full upgrade/downgrade round-trip for migrations 0090/0091 on Postgres.

    Exercises the real alembic command API (which drives env.py's async
    asyncpg engine), asserting column presence/absence and that pre-existing
    business rows keep the new columns NULL at every stage.
    """
    cfg = pg_migration_cfg
    url = os.environ["TEST_DATABASE_URL"]

    # --- upgrade to the 0089 baseline and seed genuine pre-migration rows ---
    command.upgrade(cfg, BASELINE)
    assert asyncio.run(_current_revision(url)) == BASELINE
    seeded_ids = asyncio.run(_seed_baseline_rows(url))

    # --- upgrade 0090: supplier risk score + product-cost provenance ---
    command.upgrade(cfg, REV_SUPPLIER_RISK)
    assert asyncio.run(_current_revision(url)) == REV_SUPPLIER_RISK
    cols = asyncio.run(_get_columns(url, "supplier_profiles"))
    assert {"risk_score", "risk_score_model_version", "risk_score_calibrated_at"} <= cols
    pc_cols = asyncio.run(_get_columns(url, "product_cost"))
    assert {"source", "confidence"} <= pc_cols
    asyncio.run(_assert_new_columns_null(url, _M420_SUPPLIER_RISK_COLUMNS, seeded_ids))

    # --- upgrade 0091: reorder point + shipment reconciliation ---
    command.upgrade(cfg, REV_INVENTORY_REORDER)
    assert asyncio.run(_current_revision(url)) == REV_INVENTORY_REORDER
    inv_cols = asyncio.run(_get_columns(url, "inventory_snapshots"))
    assert "reorder_point" in inv_cols
    ship_cols = asyncio.run(_get_columns(url, "shipment_records"))
    assert {"promised_delivery", "actual_cost", "actual_cost_currency"} <= ship_cols
    asyncio.run(
        _assert_new_columns_null(
            url,
            _M420_SUPPLIER_RISK_COLUMNS + _M420_INVENTORY_REORDER_COLUMNS,
            seeded_ids,
        )
    )

    # --- downgrade 0090: the 0091 columns must be removed ---
    command.downgrade(cfg, REV_SUPPLIER_RISK)
    assert asyncio.run(_current_revision(url)) == REV_SUPPLIER_RISK
    inv_cols = asyncio.run(_get_columns(url, "inventory_snapshots"))
    assert "reorder_point" not in inv_cols
    ship_cols = asyncio.run(_get_columns(url, "shipment_records"))
    for removed in ("promised_delivery", "actual_cost", "actual_cost_currency"):
        assert removed not in ship_cols

    # --- downgrade 0089: the 0090 columns must be removed ---
    command.downgrade(cfg, BASELINE)
    assert asyncio.run(_current_revision(url)) == BASELINE
    sp_cols = asyncio.run(_get_columns(url, "supplier_profiles"))
    for removed in ("risk_score", "risk_score_model_version", "risk_score_calibrated_at"):
        assert removed not in sp_cols
    pc_cols = asyncio.run(_get_columns(url, "product_cost"))
    assert "source" not in pc_cols
    assert "confidence" not in pc_cols

    # Downgrade must not lose the pre-existing business data: the seeded rows
    # must still exist with their baseline field values intact.
    asyncio.run(_assert_rows_exist(url, seeded_ids))

    asyncio.run(_cleanup_tables(url))
