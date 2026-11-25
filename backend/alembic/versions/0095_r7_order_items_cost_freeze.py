"""0095: M4 V2.8 Phase 3C R7 -- Order Items Cost Snapshot Freeze.

V1.3 frozen design alignment (§3.3 canonical 9 fields):
  product_mapping_id, cost_snapshot_id, cost_snapshot_version,
  unit_cost, currency, evidence_grade, pricing_rule_version,
  pricing_engine_version, trace_id.

Notes:
- supplier_offer_mapping_id REMOVED: not part of V1.3 §3.3 canonical set;
  supplier offer lineage is tracked via product_mapping_id -> supplier_offer_mappings
  through R13 (0097), not directly on order_items.
- Migration chain (per §6.1): 0093 <- 0094 <- 0095 <- 0096 <- 0097.
  Currently 0092/0093 not on origin/main; down_revision="0091" is a temporary
  placeholder for isolated development. TODO: update to "0094" after 0094 merges.
- All new columns are nullable (= LEGACY_UNKNOWN for historical rows);
  no backfill; no server_default.
- Composite UNIQUE(workspace_id, id) added to referenced tables for future
  compound FKs required by downstream 0096/0097 migrations (V1.3 §5.5).

Revision: 0095
Create Date: 2026-11-25
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa

from alembic import op

revision = "0095"
down_revision = "0091"  # TODO: set to "0094" after 0094 merges to main
branch_labels = None
depends_on = None


def _constraint_exists(table: str, name: str) -> bool:
    """Check whether a unique constraint or partial index already exists."""
    try:
        insp = sa.inspect(op.get_bind())
        if any(item["name"] == name for item in insp.get_unique_constraints(table)):
            return True
        return any(idx["name"] == name for idx in insp.get_indexes(table))
    except Exception:
        return False


def upgrade() -> None:
    # R7: per-line order cost snapshot freeze (V1.3 §3.3 canonical 9 fields).
    # Historical rows remain NULL (= LEGACY_UNKNOWN semantics).
    op.add_column("order_items", sa.Column("product_mapping_id", sa.Uuid(), nullable=True))
    op.add_column(
        "order_items",
        sa.Column("cost_snapshot_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("cost_snapshot_version", sa.String(16), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("currency", sa.String(8), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("evidence_grade", sa.String(4), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("pricing_rule_version", sa.String(32), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("pricing_engine_version", sa.String(32), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("trace_id", sa.String(64), nullable=True),
    )

    # Compound FK prerequisite: ensure UNIQUE(workspace_id, id) on referenced tables.
    # These constraints are logically redundant with PK(id) but required by
    # PostgreSQL FK rules for composite FKs, and enforce workspace isolation.
    # See V1.3 §5.5 for rationale.
    for tbl, cname in [
        ("product_mappings", "uq_pm_workspace_id"),
        ("product_cost_snapshots", "uq_pcs_workspace_id"),
    ]:
        if not _constraint_exists(tbl, cname):
            op.create_unique_constraint(cname, tbl, ["workspace_id", "id"])

    # Performance indexes for lineage tracing.
    op.create_index("ix_order_items_cost_snapshot", "order_items", ["cost_snapshot_id"])
    op.create_index("ix_order_items_mapping", "order_items", ["product_mapping_id"])
    op.create_index("ix_order_items_trace", "order_items", ["trace_id"])


def downgrade() -> None:
    # Reverse indexes first (they depend on columns).
    op.drop_index("ix_order_items_trace", table_name="order_items")
    op.drop_index("ix_order_items_mapping", table_name="order_items")
    op.drop_index("ix_order_items_cost_snapshot", table_name="order_items")

    # Reverse compound unique constraints (added by upgrade, safe to drop).
    for cname, tbl in [
        ("uq_pcs_workspace_id", "product_cost_snapshots"),
        ("uq_pm_workspace_id", "product_mappings"),
    ]:
        with contextlib.suppress(Exception):
            op.drop_constraint(cname, tbl, type_="unique")

    # Reverse column drops (V1.3 §3.3 canonical field order reversed).
    for col in (
        "trace_id",
        "pricing_engine_version",
        "pricing_rule_version",
        "evidence_grade",
        "currency",
        "unit_cost",
        "cost_snapshot_version",
        "cost_snapshot_id",
        "product_mapping_id",
    ):
        op.drop_column("order_items", col)
