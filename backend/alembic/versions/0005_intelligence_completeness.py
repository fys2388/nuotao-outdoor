"""product intelligence completeness: landed cost model, candidates, evidence, experiments

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend the landed cost model and add M2.1.5 intelligence tables."""

    # --- landed cost model: rename purchase_price -> purchase_cost -----------
    op.alter_column("product_cost", "purchase_price", new_column_name="purchase_cost")
    op.alter_column("product_cost_snapshots", "purchase_price", new_column_name="purchase_cost")

    # --- product_cost: new landed cost columns + version ----------------------
    for column in (
        sa.Column("international_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("packaging", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_estimate", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("handling", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_landed_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
    ):
        op.add_column("product_cost", column)

    op.execute(
        sa.text(
            "UPDATE product_cost SET "
            "international_shipping = first_leg_shipping + last_leg_shipping, "
            "total_landed_cost = total_cost, version = 'v1'"
        )
    )

    # --- product_cost_snapshots: same extensions ------------------------------
    for column in (
        sa.Column("international_shipping", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("packaging", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax_estimate", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("handling", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_landed_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
    ):
        op.add_column("product_cost_snapshots", column)

    op.execute(
        sa.text(
            "UPDATE product_cost_snapshots SET "
            "international_shipping = first_leg_shipping + last_leg_shipping, "
            "total_landed_cost = total_cost, version = 'v1'"
        )
    )

    # --- product_sourcing_candidates ------------------------------------------
    op.create_table(
        "product_sourcing_candidates",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("supplier_code", sa.String(64), nullable=True),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="1688"),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("purchase_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("moq", sa.Integer(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("trend_score", sa.Numeric(4, 2), nullable=True),
        sa.Column("profit_model", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_sourcing_candidates_workspace_id", "product_sourcing_candidates", ["workspace_id"]
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_sourcing_candidates_product "
            "ON product_sourcing_candidates (workspace_id, product_id)"
        )
    )

    # --- product_score_evidences ----------------------------------------------
    op.create_table(
        "product_score_evidences",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_score_id",
            UUID(),
            sa.ForeignKey("product_scores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0"),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_product_score_evidences_workspace_id", "product_score_evidences", ["workspace_id"]
    )
    op.create_index(
        "ix_product_score_evidences_score_id", "product_score_evidences", ["product_score_id"]
    )

    # --- product_experiments ---------------------------------------------------
    op.create_table(
        "product_experiments",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("experiment_type", sa.String(32), nullable=False, server_default="market_test"),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("experiment", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calibration", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_product_experiments_workspace_id", "product_experiments", ["workspace_id"])
    op.execute(
        sa.text(
            "CREATE INDEX ix_product_experiments_product "
            "ON product_experiments (workspace_id, product_id)"
        )
    )


def downgrade() -> None:
    """Drop M2.1.5 tables and revert cost columns."""
    op.drop_table("product_experiments")
    op.drop_table("product_score_evidences")
    op.drop_table("product_sourcing_candidates")
    op.drop_column("product_cost_snapshots", "version")
    op.drop_column("product_cost_snapshots", "total_landed_cost")
    op.drop_column("product_cost_snapshots", "handling")
    op.drop_column("product_cost_snapshots", "tax_estimate")
    op.drop_column("product_cost_snapshots", "packaging")
    op.drop_column("product_cost_snapshots", "international_shipping")
    op.drop_column("product_cost", "version")
    op.drop_column("product_cost", "total_landed_cost")
    op.drop_column("product_cost", "handling")
    op.drop_column("product_cost", "tax_estimate")
    op.drop_column("product_cost", "packaging")
    op.drop_column("product_cost", "international_shipping")
    op.alter_column("product_cost_snapshots", "purchase_cost", new_column_name="purchase_price")
    op.alter_column("product_cost", "purchase_cost", new_column_name="purchase_price")
