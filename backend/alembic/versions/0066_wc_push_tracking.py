"""Add WC push tracking to creative_studio_assets for idempotency.

P0-6: WooCommerce Idempotency + Publish Gate
- Prevents duplicate WooCommerce pushes for the same asset
- Tracks wc_pushed_at and wc_media_id for audit trail

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0066"
down_revision: Union[str, None] = "0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add wc_pushed_at and wc_media_id columns."""
    op.add_column(
        "creative_studio_assets",
        sa.Column("wc_pushed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "creative_studio_assets",
        sa.Column("wc_media_id", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_creative_studio_assets_wc_pushed",
        "creative_studio_assets",
        ["workspace_id", "wc_pushed_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove wc_pushed_at and wc_media_id columns."""
    op.drop_index("ix_creative_studio_assets_wc_pushed", table_name="creative_studio_assets")
    op.drop_column("creative_studio_assets", "wc_pushed_at")
    op.drop_column("creative_studio_assets", "wc_media_id")