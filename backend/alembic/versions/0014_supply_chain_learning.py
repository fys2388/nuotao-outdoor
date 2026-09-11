"""M4.2: supply chain learning loop - supplier/logistics evaluations, pattern runs, calibration

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M4.2 supply chain learning loop tables."""

    # --- supplier_ai_evaluations -------------------------------------------------
    op.create_table(
        "supplier_ai_evaluations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
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
        "ix_supplier_evaluations_workspace_supplier",
        "supplier_ai_evaluations",
        ["workspace_id", "supplier_id"],
    )
    op.create_index(
        "ix_supplier_evaluations_workspace_bucket",
        "supplier_ai_evaluations",
        ["workspace_id", "confidence_bucket"],
    )

    # --- logistics_ai_evaluations -------------------------------------------------
    op.create_table(
        "logistics_ai_evaluations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "shipment_id",
            UUID(),
            sa.ForeignKey("shipment_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("carrier", sa.String(64), nullable=True),
        sa.Column("route", sa.String(255), nullable=True),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("delay_reason", sa.String(500), nullable=True),
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
        "ix_logistics_evaluations_workspace_shipment",
        "logistics_ai_evaluations",
        ["workspace_id", "shipment_id"],
    )
    op.create_index(
        "ix_logistics_evaluations_workspace_carrier",
        "logistics_ai_evaluations",
        ["workspace_id", "carrier"],
    )

    # --- supplier_pattern_runs ----------------------------------------------------
    op.create_table(
        "supplier_pattern_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "supplier_id", UUID(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
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
        "ix_supplier_pattern_runs_workspace_type",
        "supplier_pattern_runs",
        ["workspace_id", "pattern_type"],
    )
    op.create_index(
        "ix_supplier_pattern_runs_supplier_id",
        "supplier_pattern_runs",
        ["supplier_id"],
    )

    # --- logistics_pattern_runs ---------------------------------------------------
    op.create_table(
        "logistics_pattern_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "shipment_id",
            UUID(),
            sa.ForeignKey("shipment_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("carrier", sa.String(64), nullable=True),
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
        "ix_logistics_pattern_runs_workspace_type",
        "logistics_pattern_runs",
        ["workspace_id", "pattern_type"],
    )
    op.create_index(
        "ix_logistics_pattern_runs_shipment_id",
        "logistics_pattern_runs",
        ["shipment_id"],
    )

    # --- supply_chain_calibration_runs ----------------------------------------------
    op.create_table(
        "supply_chain_calibration_runs",
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
        "ix_supply_chain_calibration_workspace_status",
        "supply_chain_calibration_runs",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop the M4.2 learning loop tables (not for production)."""
    op.drop_table("supply_chain_calibration_runs")
    op.drop_table("logistics_pattern_runs")
    op.drop_table("supplier_pattern_runs")
    op.drop_table("logistics_ai_evaluations")
    op.drop_table("supplier_ai_evaluations")
