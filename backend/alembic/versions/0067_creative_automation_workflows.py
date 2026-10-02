"""Create creative_automation_workflows table for workflow automation.

C11: Creative Automation Workflow
- Defines automated creative production pipelines
- Supports manual, scheduled, and event-based triggers
- Tracks run history and success rates

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0067"
down_revision: Union[str, None] = "0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create creative_automation_workflows table."""
    op.create_table(
        "creative_automation_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("workflow_type", sa.String(32), nullable=False),
        sa.Column("trigger_type", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="inactive"),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(16), nullable=True),
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(128), nullable=False, server_default="system"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Indexes
    op.create_index(
        "ix_creative_automation_workflows_workspace_id",
        "creative_automation_workflows",
        ["workspace_id"],
    )
    op.create_index(
        "ix_creative_automation_workflows_workflow_type",
        "creative_automation_workflows",
        ["workflow_type"],
    )
    op.create_index(
        "ix_creative_automation_workflows_status",
        "creative_automation_workflows",
        ["status"],
    )
    op.create_index(
        "ix_caw_workspace_status",
        "creative_automation_workflows",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_caw_workspace_type",
        "creative_automation_workflows",
        ["workspace_id", "workflow_type"],
    )
    op.create_index(
        "ix_caw_workspace_trigger",
        "creative_automation_workflows",
        ["workspace_id", "trigger_type"],
    )


def downgrade() -> None:
    """Drop creative_automation_workflows table."""
    op.drop_table("creative_automation_workflows")