"""M5.7: product analyst real business validation - dataset + result history

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the staging validation-case dataset + append-only result history.

    ``product_validation_cases`` distinguishes real business data
    (``staging_real``) from synthetic fixtures (``staging_synthetic``) so a
    report can never mistake one for the other. ``result_history`` on
    ``product_experiments`` keeps every measured outcome append-only; the
    current ``actual_result`` stays the latest recorded outcome and is never
    overwritten silently.
    """
    op.create_table(
        "product_validation_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("product_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_product_validation_cases_source",
        "product_validation_cases",
        "source IN ('staging_real', 'staging_synthetic')",
    )
    op.add_column("product_experiments", sa.Column("result_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Reverse the M5.7 validation dataset changes."""
    op.drop_column("product_experiments", "result_history")
    op.drop_table("product_validation_cases")
