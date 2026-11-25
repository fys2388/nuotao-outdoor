"""0095: M4 V2.8 Phase 3C R7 -- Order Items Cost Snapshot Freeze.

V1.3 frozen design alignment:
- Migration chain (per §6.1): 0093 ← 0094 ← 0095 ← 0096 ← 0097.
  Currently: 0092/0093 not yet on origin/main; this migration is placed
  independently with down_revision="0091" as a placeholder.
  TODO: After 0093/0094 land on main, update down_revision to "0094".
- Field names strictly follow V1.3 §3.3 canonical names (not renamed variants).
- All new columns are nullable (= LEGACY_UNKNOWN for historical rows);
  no backfill; no server_default on non-nullable placeholder.
- Composite UNIQUE(workspace_id, id) added to referenced tables for future
  compound FKs required by downstream 0096/0097 migrations.

Revision: 0095
Create Date: 2026-11-25
"""

from __future__ import annotations

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
        for item in insp.get_unique_constraints(table):
            if item["name"] == name:
                return True
        for idx in insp.get_indexes(table):
            if idx["name"] == name:
                return True
        return False
    except Exception:
        return False


def upgrade() -> None:
    # R7: per-line order cost snapshot freeze (V1.3 §3.3 canonical fields).
    # Historical rows remain NULL (= LEGACY_UNKNOWN semantics).
    op.add_column("order_items", sa.Column("product_mapping_id", sa.Uuid(), nullable=True))
    op.add_column("order_items", sa.Column("supplier_offer_mapping_id", sa.Uuid(), nullable=True))
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
        sa.Column("trace_id", sa.String(64), nullable=True),
    )

    # Compound FK prerequisite: ensure UNIQUE(workspace_id, id) on referenced tables.
    # These constraints are logically redundant with PK(id) but required by
    # PostgreSQL FK rules for composite FKs, and enforce workspace isolation.
    # See V1.3 §5.5 for rationale.
    for tbl, cname in [
        ("product_mappings", "uq_pm_workspace_id"),
        ("supplier_offer_mappings", "uq_som_workspace_id"),
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
        ("uq_som_workspace_id", "supplier_offer_mappings"),
        ("uq_pm_workspace_id", "product_mappings"),
    ]:
        try:
            op.drop_constraint(cname, tbl, type_="unique")
        except Exception:
            pass

    # Reverse column drops (V1.3 §3.3 field order reversed).
    for col in (
        "trace_id",
        "pricing_rule_version",
        "evidence_grade",
        "currency",
        "unit_cost",
        "cost_snapshot_version",
        "cost_snapshot_id",
        "supplier_offer_mapping_id",
        "product_mapping_id",
    ):
        op.drop_column("order_items", col)
