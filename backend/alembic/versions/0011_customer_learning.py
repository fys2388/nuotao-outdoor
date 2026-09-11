"""M3.4: customer learning loop - evaluations, pattern runs, calibration + context links

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add M3.4 customer learning tables + cross-domain customer links."""

    # --- cross-domain links (orders.customer_reference_id, refunds.customer_id)
    op.add_column(
        "orders",
        sa.Column("customer_reference_id", sa.String(128), nullable=True),
    )
    op.create_index("ix_orders_customer_reference_id", "orders", ["customer_reference_id"])
    op.add_column(
        "refund_cases",
        sa.Column(
            "customer_id",
            UUID(),
            sa.ForeignKey("customer_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_refund_cases_customer_id", "refund_cases", ["customer_id"])

    # --- customer_ai_evaluations ---------------------------------------------
    op.create_table(
        "customer_ai_evaluations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "customer_id",
            UUID(),
            sa.ForeignKey("customer_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "actual_behavior", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("accuracy", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prediction_result", sa.String(16), nullable=True),
        sa.Column("error_type", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("confidence_bucket", sa.String(8), nullable=True),
        sa.Column("success_flag", sa.Boolean(), nullable=True),
        sa.Column(
            "metric_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("human_rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_customer_evaluations_workspace_customer",
        "customer_ai_evaluations",
        ["workspace_id", "customer_id"],
    )
    op.create_index(
        "ix_customer_evaluations_workspace_bucket",
        "customer_ai_evaluations",
        ["workspace_id", "confidence_bucket"],
    )
    op.create_index(
        "ix_customer_ai_evaluations_customer_id", "customer_ai_evaluations", ["customer_id"]
    )

    # --- customer_pattern_runs ------------------------------------------------
    op.create_table(
        "customer_pattern_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "customer_id",
            UUID(),
            sa.ForeignKey("customer_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pattern_type", sa.String(32), nullable=False),
        sa.Column("input_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_pattern", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_customer_pattern_runs_workspace_type",
        "customer_pattern_runs",
        ["workspace_id", "pattern_type"],
    )
    op.create_index(
        "ix_customer_pattern_runs_customer_id", "customer_pattern_runs", ["customer_id"]
    )

    # --- customer_calibration_runs ---------------------------------------------
    op.create_table(
        "customer_calibration_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("input_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "successful_patterns", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "failure_patterns", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_customer_calibration_workspace_status",
        "customer_calibration_runs",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop M3.4 tables and revert cross-domain links (not for production)."""
    op.drop_table("customer_calibration_runs")
    op.drop_table("customer_pattern_runs")
    op.drop_table("customer_ai_evaluations")
    op.drop_index("ix_refund_cases_customer_id", table_name="refund_cases")
    op.drop_column("refund_cases", "customer_id")
    op.drop_index("ix_orders_customer_reference_id", table_name="orders")
    op.drop_column("orders", "customer_reference_id")
