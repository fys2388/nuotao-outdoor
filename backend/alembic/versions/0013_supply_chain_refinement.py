"""M4.1 refinement: supplier factory_type, PO partial_received, inventory snapshot_time + CN/US/EU warehouses

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the M4.1 refinement columns and warehouse location policy."""
    # Supplier intelligence: factory type (factory / trading / agent).
    op.add_column(
        "supplier_profiles",
        sa.Column("factory_type", sa.String(32), nullable=True),
    )

    # Inventory: snapshot_time captures when the stock count was taken.
    op.add_column(
        "inventory_snapshots",
        sa.Column(
            "snapshot_time",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Warehouse locations: normalize legacy values to cn / us / eu.
    op.execute("UPDATE inventory_snapshots SET location = 'cn' WHERE location = 'cn-main'")
    op.execute(
        "UPDATE inventory_snapshots SET location = 'us' WHERE location IN ('us-main', 'us-west')"
    )
    op.execute(
        "UPDATE inventory_snapshots SET location = 'eu' WHERE location IN ('eu-main', 'eu-west')"
    )
    op.alter_column("inventory_snapshots", "location", server_default="cn")
    op.create_check_constraint(
        "ck_inventory_location",
        "inventory_snapshots",
        "location IN ('cn', 'us', 'eu')",
    )


def downgrade() -> None:
    """Roll back the M4.1 refinement (not for production)."""
    op.drop_constraint("ck_inventory_location", "inventory_snapshots", type_="check")
    op.alter_column("inventory_snapshots", "location", server_default="cn-main")
    op.drop_column("inventory_snapshots", "snapshot_time")
    op.drop_column("supplier_profiles", "factory_type")
