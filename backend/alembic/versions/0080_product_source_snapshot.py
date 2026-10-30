"""0080: Add source_snapshot field to products table.

This field stores a JSON snapshot of the 1688 source page captured at selection
time, including original images and description text. Used for:
- AI copy generation reference
- 1688 vs WC page comparison
- Data quality tracking

Revision ID: 0080
Revises: 0079
Create Date: 2026-10-11
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by the Alembic system.
revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add source_snapshot JSON column to products table."""
    op.add_column(
        "products",
        sa.Column(
            "source_snapshot",
            sa.JSON(),
            nullable=True,
            comment="1688 source page snapshot (images + description) captured at selection time",
        ),
    )


def downgrade() -> None:
    """Remove source_snapshot column from products table."""
    op.drop_column("products", "source_snapshot")
