"""Add creative_calibration_runs table for creative learning loop (C8).

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-01

This migration adds the creative_calibration_runs table which stores
calibration proposals based on aggregated creative knowledge entries.
Calibration runs are always 'proposed' first and require human approval
before any changes can be applied.
"""

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add creative_calibration_runs table."""
    op.create_table(
        "creative_calibration_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("input_snapshot", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("successful_patterns", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("failure_patterns", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_calibration_workspace_status",
        "creative_calibration_runs",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop creative_calibration_runs table."""
    op.drop_index("ix_creative_calibration_workspace_status", table_name="creative_calibration_runs")
    op.drop_table("creative_calibration_runs")
