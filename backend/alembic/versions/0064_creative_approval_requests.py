"""Add creative_approval_requests table for human-in-the-loop approval (C10).

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-01

This migration adds the creative_approval_requests table which stores
approval requests for high-risk creative operations. Requests are
automatically created for high-cost generations, bulk operations,
and WooCommerce pushes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add creative_approval_requests table."""
    op.create_table(
        "creative_approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("context", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("estimated_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("asset_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requested_by", sa.String(128), nullable=False, server_default="system"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_result", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_car_workspace_status",
        "creative_approval_requests",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_car_workspace_type",
        "creative_approval_requests",
        ["workspace_id", "request_type"],
    )
    op.create_index(
        "ix_car_workspace_risk",
        "creative_approval_requests",
        ["workspace_id", "risk_level"],
    )
    op.create_index(
        "ix_car_request_type",
        "creative_approval_requests",
        ["request_type"],
    )
    op.create_index(
        "ix_car_status",
        "creative_approval_requests",
        ["status"],
    )
    op.create_index(
        "ix_car_risk_level",
        "creative_approval_requests",
        ["risk_level"],
    )
    op.create_index(
        "ix_car_requested_at",
        "creative_approval_requests",
        ["requested_at"],
    )


def downgrade() -> None:
    """Drop creative_approval_requests table."""
    op.drop_index("ix_car_requested_at", table_name="creative_approval_requests")
    op.drop_index("ix_car_risk_level", table_name="creative_approval_requests")
    op.drop_index("ix_car_status", table_name="creative_approval_requests")
    op.drop_index("ix_car_request_type", table_name="creative_approval_requests")
    op.drop_index("ix_car_workspace_risk", table_name="creative_approval_requests")
    op.drop_index("ix_car_workspace_type", table_name="creative_approval_requests")
    op.drop_index("ix_car_workspace_status", table_name="creative_approval_requests")
    op.drop_table("creative_approval_requests")
