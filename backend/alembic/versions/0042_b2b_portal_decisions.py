"""Record customer portal quote decisions.

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "b2b_quotes",
        sa.Column("accepted_by", sa.String(128), nullable=True),
    )
    op.add_column(
        "b2b_quotes",
        sa.Column("rejected_by", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("b2b_quotes", "rejected_by")
    op.drop_column("b2b_quotes", "accepted_by")
