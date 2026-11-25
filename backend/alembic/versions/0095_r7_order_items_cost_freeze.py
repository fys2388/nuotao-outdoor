"""0095: M4 V2.8 Phase 3C -- Order Items Cost Freeze (R7).

upgrade():
- Add 9 nullable columns to `order_items` for per-line cost audit traceability:
    product_mapping_id       FK -> product_mappings.id (SET NULL)
    supplier_offer_mapping_id FK -> supplier_offer_mappings.id (SET NULL)
    product_cost_snapshot_id FK -> product_cost_snapshots.id (SET NULL)
    unit_landed_cost         Numeric(12,2) default 0
    total_landed_cost        Numeric(12,2) default 0
    profit_snapshot_id       Uuid FK -> product_cost_snapshots.id (SET NULL)
    rule_version             String(32) NOT NULL default 'v1'
    confidence               Numeric(3,2) nullable
    trace_id                 String(64) nullable
- Add composite UNIQUE(workspace_id, id) on reference tables for compound FKs later.
- Add indexes ix_order_items_cost_snapshot / ix_order_items_mapping / ix_order_items_trace.

downgrade():
- Drop indexes, drop UNIQUE constraints, drop columns in reverse order.

Notes:
- down_revision = "0091": 0092 is not yet on origin/main (local-only branch);
  this migration independently adds R7 columns without requiring 0092's schema.
  When 0092/0093/0094 land on main, update this to "0094" for the canonical chain.
- Red-line compliance: no production DB connection; all new columns are nullable
  (LEGACY_UNKNOWN semantics for historical rows); 0076 untouched.
- Design only: not executed on production without Owner approval.

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
    # R7: per-line order cost freeze + identity versioning (nullable = LEGACY_UNKNOWN)
    op.add_column("order_items", sa.Column("product_mapping_id", sa.Uuid(), nullable=True))
    op.add_column("order_items", sa.Column("supplier_offer_mapping_id", sa.Uuid(), nullable=True))
    op.add_column("order_items", sa.Column("product_cost_snapshot_id", sa.Uuid(), nullable=True))
    op.add_column(
        "order_items",
        sa.Column("unit_landed_cost", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "order_items",
        sa.Column(
            "total_landed_cost", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column("order_items", sa.Column("profit_snapshot_id", sa.Uuid(), nullable=True))
    op.add_column(
        "order_items",
        sa.Column(
            "rule_version", sa.String(32), nullable=False, server_default=sa.text("'v1'")
        ),
    )
    op.add_column("order_items", sa.Column("confidence", sa.Numeric(3, 2), nullable=True))
    op.add_column("order_items", sa.Column("trace_id", sa.String(64), nullable=True))

    # Ensure UNIQUE(workspace_id, id) exists on referenced tables for future compound FKs
    for tbl, cname in [
        ("product_mappings", "uq_pm_workspace_id"),
        ("supplier_offer_mappings", "uq_som_workspace_id"),
        ("product_cost_snapshots", "uq_pcs_workspace_id"),
    ]:
        if not _constraint_exists(tbl, cname):
            op.create_unique_constraint(cname, tbl, ["workspace_id", "id"])

    # Performance indexes
    op.create_index("ix_order_items_cost_snapshot", "order_items", ["product_cost_snapshot_id"])
    op.create_index("ix_order_items_mapping", "order_items", ["product_mapping_id"])
    op.create_index("ix_order_items_trace", "order_items", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_trace", table_name="order_items")
    op.drop_index("ix_order_items_mapping", table_name="order_items")
    op.drop_index("ix_order_items_cost_snapshot", table_name="order_items")
    for cname, tbl in [
        ("uq_pcs_workspace_id", "product_cost_snapshots"),
        ("uq_som_workspace_id", "supplier_offer_mappings"),
        ("uq_pm_workspace_id", "product_mappings"),
    ]:
        try:
            op.drop_constraint(cname, tbl, type_="unique")
        except Exception:
            pass
    # Reverse column drops
    for col in (
        "trace_id",
        "confidence",
        "rule_version",
        "profit_snapshot_id",
        "total_landed_cost",
        "unit_landed_cost",
        "product_cost_snapshot_id",
        "supplier_offer_mapping_id",
        "product_mapping_id",
    ):
        op.drop_column("order_items", col)
