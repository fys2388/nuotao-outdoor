"""0095: M4 V2.8 Phase 3C R7 -- Order Items Cost Snapshot Freeze.

V1.3 frozen design alignment (§3.3 canonical 9 fields + §5.5 composite FK):
  product_mapping_id, cost_snapshot_id, cost_snapshot_version,
  unit_cost, currency, evidence_grade, pricing_rule_version,
  pricing_engine_version, trace_id.

Composite FKs (V1.3 §5.5 + §6.1 0095 line):
  FK: order_items(workspace_id, product_mapping_id)
      -> product_mappings(workspace_id, id)  ON DELETE RESTRICT
  FK: order_items(workspace_id, cost_snapshot_id)
      -> product_cost_snapshots(workspace_id, id)  ON DELETE RESTRICT

ON DELETE RESTRICT rationale (E-15):
  - Historical order rows are an immutable audit trail; silently unbinding
    the cost snapshot would destroy R7 lineage integrity.
  - RESTRICT forces explicit handling before any delete of a referenced
    snapshot/mapping (aligns with R7 "historical data cannot be reinterpreted").
  - SET NULL was rejected in E-14 review; RESTRICT is the fail-closed choice.
    If business later requires cascade-free deletion, that is a separate
    Owner-approved change, not a silent migration default.

Notes:
- supplier_offer_mapping_id REMOVED: not part of V1.3 §3.3 canonical set.
- Migration chain (per §6.1): 0093 <- 0094 <- 0095 <- 0096 <- 0097.
  down_revision="0091" is a temporary placeholder for isolated development.
  TODO: update to "0094" after 0094 merges to main.
- All new columns are nullable (= LEGACY_UNKNOWN for historical rows).

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

FK_ORDER_ITEMS_PM = "fk_order_items_product_mapping"
FK_ORDER_ITEMS_PCS = "fk_order_items_cost_snapshot"


def _constraint_exists(table: str, name: str) -> bool:
    """Check whether a constraint or index with this name already exists."""
    try:
        insp = sa.inspect(op.get_bind())
        if any(item["name"] == name for item in insp.get_unique_constraints(table)):
            return True
        if any(idx["name"] == name for idx in insp.get_indexes(table)):
            return True
        # Foreign keys: use get_foreign_keys (name may be auto-generated).
        return any(fk.get("name") == name for fk in insp.get_foreign_keys(table))
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
    # Redundant with PK(id) but required by PostgreSQL for composite FK target sets.
    # See V1.3 §5.5.
    for tbl, cname in [
        ("product_mappings", "uq_pm_workspace_id"),
        ("product_cost_snapshots", "uq_pcs_workspace_id"),
    ]:
        if not _constraint_exists(tbl, cname):
            op.create_unique_constraint(cname, tbl, ["workspace_id", "id"])

    # Composite FKs (V1.3 §5.5 + §6.1 0095): workspace-isolated references.
    # RESTRICT = fail-closed: order lineage cannot be silently unbound.
    if not _constraint_exists("order_items", FK_ORDER_ITEMS_PM):
        op.create_foreign_key(
            FK_ORDER_ITEMS_PM,
            "order_items",
            "product_mappings",
            ["workspace_id", "product_mapping_id"],
            ["workspace_id", "id"],
            ondelete="RESTRICT",
        )
    if not _constraint_exists("order_items", FK_ORDER_ITEMS_PCS):
        op.create_foreign_key(
            FK_ORDER_ITEMS_PCS,
            "order_items",
            "product_cost_snapshots",
            ["workspace_id", "cost_snapshot_id"],
            ["workspace_id", "id"],
            ondelete="RESTRICT",
        )

    # Performance indexes for lineage tracing.
    op.create_index("ix_order_items_cost_snapshot", "order_items", ["cost_snapshot_id"])
    op.create_index("ix_order_items_mapping", "order_items", ["product_mapping_id"])
    op.create_index("ix_order_items_trace", "order_items", ["trace_id"])


def downgrade() -> None:
    # Reverse indexes first (they depend on columns).
    op.drop_index("ix_order_items_trace", table_name="order_items")
    op.drop_index("ix_order_items_mapping", table_name="order_items")
    op.drop_index("ix_order_items_cost_snapshot", table_name="order_items")

    # Reverse composite FKs (drop before the columns they reference).
    for fk in (FK_ORDER_ITEMS_PCS, FK_ORDER_ITEMS_PM):
        with contextlib.suppress(Exception):
            op.drop_constraint(fk, "order_items", type_="foreignkey")

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
