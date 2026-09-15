"""Add auditable workspace exchange rates.

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("base_currency", sa.String(8), nullable=False),
        sa.Column("quote_currency", sa.String(8), nullable=False),
        sa.Column("rate", sa.Numeric(20, 12), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="manual"),
        sa.Column("source_reference", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "base_currency <> quote_currency",
            name="ck_exchange_rates_distinct_currency",
        ),
        sa.CheckConstraint("rate > 0", name="ck_exchange_rates_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "base_currency",
            "quote_currency",
            "effective_date",
            name="uq_exchange_rates_workspace_pair_date",
        ),
    )
    op.create_index(
        "ix_exchange_rates_workspace_id",
        "exchange_rates",
        ["workspace_id"],
    )
    op.create_index(
        "ix_exchange_rates_effective_date",
        "exchange_rates",
        ["effective_date"],
    )
    op.create_index(
        "ix_exchange_rates_workspace_pair_date",
        "exchange_rates",
        ["workspace_id", "base_currency", "quote_currency", "effective_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_exchange_rates_workspace_pair_date", table_name="exchange_rates")
    op.drop_index("ix_exchange_rates_effective_date", table_name="exchange_rates")
    op.drop_index("ix_exchange_rates_workspace_id", table_name="exchange_rates")
    op.drop_table("exchange_rates")
