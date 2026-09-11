"""M5.6: product analyst production pilot - experiment decision linkage

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Link product experiments to the approved decision that spawned them.

    Adds the second human control point (``started_by``) and the proposal
    fields (hypothesis / expected / baseline / target metrics) so the pilot
    loop ``decision -> experiment proposal -> human start -> actual result``
    is fully auditable. All new columns are nullable: existing experiments
    keep working unchanged.
    """
    op.add_column("product_experiments", sa.Column("decision_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_product_experiments_decision",
        "product_experiments",
        "product_decisions",
        ["decision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_product_experiments_decision_id", "product_experiments", ["decision_id"])
    op.add_column(
        "product_experiments", sa.Column("hypothesis", sa.String(length=2000), nullable=True)
    )
    op.add_column("product_experiments", sa.Column("expected_metrics", sa.JSON(), nullable=True))
    op.add_column("product_experiments", sa.Column("baseline", sa.JSON(), nullable=True))
    op.add_column("product_experiments", sa.Column("target_metrics", sa.JSON(), nullable=True))
    op.add_column(
        "product_experiments", sa.Column("source_trace_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "product_experiments", sa.Column("approved_by", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "product_experiments", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "product_experiments", sa.Column("started_by", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    """Reverse the M5.6 experiment columns."""
    op.drop_column("product_experiments", "started_by")
    op.drop_column("product_experiments", "approved_at")
    op.drop_column("product_experiments", "approved_by")
    op.drop_column("product_experiments", "source_trace_id")
    op.drop_column("product_experiments", "target_metrics")
    op.drop_column("product_experiments", "baseline")
    op.drop_column("product_experiments", "expected_metrics")
    op.drop_column("product_experiments", "hypothesis")
    op.drop_index("ix_product_experiments_decision_id", table_name="product_experiments")
    op.drop_constraint("fk_product_experiments_decision", "product_experiments", type_="foreignkey")
    op.drop_column("product_experiments", "decision_id")
