"""Add dedup_key to creative_generation_runs for idempotency.

P0-5: Generation Idempotency
- Prevents duplicate generation runs for the same brief/operation/input/model/parameters
- Uses SHA-256 hash of key components as the dedup_key

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0065"
down_revision: Union[str, None] = "0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dedup_key column and unique index."""
    op.add_column(
        "creative_generation_runs",
        sa.Column("dedup_key", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_creative_runs_dedup_key",
        "creative_generation_runs",
        ["dedup_key"],
        unique=True,
    )


def downgrade() -> None:
    """Remove dedup_key column and index."""
    op.drop_index("ix_creative_runs_dedup_key", table_name="creative_generation_runs")
    op.drop_column("creative_generation_runs", "dedup_key")