"""0091: inventory_snapshots reorder point + shipment_records reconciliation (M4.2.0 T0.5).

Adds the reorder-point column for M4.2.4 replenishment and the promised-vs-actual
reconciliation columns for M4.2.4 landed-cost / on-time reconciliation. All new
columns are nullable with no default, so existing rows stay NULL (meaning
"not yet computed / unknown") and no historical data is fabricated.

inventory_snapshots new columns:
- reorder_point: stock threshold that triggers replenishment (Integer).
  NULL means not yet computed.

shipment_records new columns (promised vs actual reconciliation):
- promised_delivery: promised delivery date (DateTime(timezone=True)).
- actual_cost: actual incurred cost / freight / duty (Numeric(12,2)).
- actual_cost_currency: currency of the actual cost (String(8)).

Revision: 0091
Create Date: 2026-11-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_snapshots",
        sa.Column("reorder_point", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shipment_records",
        sa.Column("promised_delivery", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "shipment_records",
        sa.Column("actual_cost", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "shipment_records",
        sa.Column("actual_cost_currency", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shipment_records", "actual_cost_currency")
    op.drop_column("shipment_records", "actual_cost")
    op.drop_column("shipment_records", "promised_delivery")
    op.drop_column("inventory_snapshots", "reorder_point")
