"""Add workflow_runs and workflow_exceptions tables for Product Factory Orchestrator.

Revision ID: 0072_workflow_run
Revises: 0071_product_data_integrity_tracking
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workflow_runs ──────────────────────────────────────────────
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_type", sa.String(32), nullable=False, server_default="product_factory"),
        sa.Column("current_stage", sa.String(32), nullable=False, server_default="CANDIDATE_READY"),
        sa.Column("execution_status", sa.String(24), nullable=False, server_default="RUNNING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("stage_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_workspace_id", "workflow_runs", ["workspace_id"])
    op.create_index("ix_workflow_runs_product_id", "workflow_runs", ["product_id"])
    op.create_index("ix_workflow_runs_current_stage", "workflow_runs", ["current_stage"])
    op.create_index("ix_workflow_runs_execution_status", "workflow_runs", ["execution_status"])
    op.create_index("ix_workflow_runs_ws_status", "workflow_runs", ["workspace_id", "execution_status"])
    op.create_index("ix_workflow_runs_stage", "workflow_runs", ["workspace_id", "current_stage"])
    op.create_index(
        "uq_workflow_runs_ws_product_type_active",
        "workflow_runs",
        ["workspace_id", "product_id", "workflow_type"],
        unique=True,
        postgresql_where=sa.text("execution_status NOT IN ('COMPLETED', 'FAILED', 'EXCEPTION')"),
    )

    # ── workflow_exceptions ──────────────────────────────────────────
    op.create_table(
        "workflow_exceptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_action", sa.String(128), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_exceptions_workspace_id", "workflow_exceptions", ["workspace_id"])
    op.create_index("ix_workflow_exceptions_workflow_run_id", "workflow_exceptions", ["workflow_run_id"])
    op.create_index("ix_workflow_exceptions_product_id", "workflow_exceptions", ["product_id"])
    op.create_index("ix_workflow_exceptions_stage", "workflow_exceptions", ["stage"])
    op.create_index("ix_workflow_exceptions_ws_created", "workflow_exceptions", ["workspace_id", sa.text("created_at DESC")])
    op.create_index("ix_workflow_exceptions_run", "workflow_exceptions", ["workflow_run_id"])
    op.create_index("ix_workflow_exceptions_stage_ws", "workflow_exceptions", ["workspace_id", "stage"])


def downgrade() -> None:
    op.drop_table("workflow_exceptions")
    op.drop_table("workflow_runs")
