"""M5.5: agent platform productionization - lifecycle versions, approval RBAC + SLA

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add agent lifecycle versions, approval RBAC roles and approval SLAs.

    Also extends ``agent_approvals`` with the SLA timestamps and rebuilds the
    DLQ unique index to cover both ``pending`` and ``warning`` states.
    """
    # --- agent_versions: append-only configuration versions -----------------
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.String(length=16), nullable=False),
        sa.Column("prompt_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=16), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("model_config", sa.JSON(), nullable=False),
        sa.Column("execution_policy_version", sa.String(length=32), nullable=False),
        sa.Column("retry_policy_version", sa.String(length=32), nullable=False),
        sa.Column("budget_policy_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "agent_id", "version", name="uq_agent_versions_ws_agent_version"
        ),
    )
    op.create_index(
        "uq_agent_versions_active",
        "agent_versions",
        ["workspace_id", "agent_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_agent_versions_ws_status", "agent_versions", ["workspace_id", "status"])
    op.create_index("ix_agent_versions_agent_id", "agent_versions", ["agent_id"])

    # --- agent_approval_roles: RBAC for the Approval Center -----------------
    op.create_table(
        "agent_approval_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("role_name", sa.String(length=64), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("actors", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "role_name", name="uq_agent_approval_roles_ws_name"),
    )
    op.create_index(
        "ix_agent_approval_roles_ws_enabled",
        "agent_approval_roles",
        ["workspace_id", "enabled"],
    )

    # --- agent_approval_slas: per-type SLA configuration --------------------
    op.create_table(
        "agent_approval_slas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("approval_type", sa.String(length=32), nullable=False),
        sa.Column("warning_after_seconds", sa.Integer(), nullable=False),
        sa.Column("expire_after_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "approval_type", name="uq_agent_approval_slas_ws_type"),
    )
    op.create_index(
        "ix_agent_approval_slas_ws_enabled",
        "agent_approval_slas",
        ["workspace_id", "enabled"],
    )

    # --- agent_approvals: SLA columns + DLQ index covering warning ----------
    op.add_column(
        "agent_approvals",
        sa.Column("sla_warning_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_approvals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index("uq_agent_approvals_dlq_pending", table_name="agent_approvals")
    op.create_index(
        "uq_agent_approvals_dlq_pending",
        "agent_approvals",
        ["workspace_id", "entity_id"],
        unique=True,
        postgresql_where=sa.text(
            "approval_type = 'DLQ_REPLAY' AND status IN ('pending', 'warning')"
        ),
        sqlite_where=sa.text("approval_type = 'DLQ_REPLAY' AND status IN ('pending', 'warning')"),
    )

    # --- agents: current configuration version -----------------------------
    op.add_column(
        "agents",
        sa.Column("current_version", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    """Reverse the M5.5 schema changes."""
    op.drop_column("agents", "current_version")

    op.drop_index("uq_agent_approvals_dlq_pending", table_name="agent_approvals")
    op.create_index(
        "uq_agent_approvals_dlq_pending",
        "agent_approvals",
        ["workspace_id", "entity_id"],
        unique=True,
        postgresql_where=sa.text("approval_type = 'DLQ_REPLAY' AND status = 'pending'"),
        sqlite_where=sa.text("approval_type = 'DLQ_REPLAY' AND status = 'pending'"),
    )
    op.drop_column("agent_approvals", "expires_at")
    op.drop_column("agent_approvals", "sla_warning_at")

    op.drop_index("ix_agent_approval_slas_ws_enabled", table_name="agent_approval_slas")
    op.drop_table("agent_approval_slas")

    op.drop_index("ix_agent_approval_roles_ws_enabled", table_name="agent_approval_roles")
    op.drop_table("agent_approval_roles")

    op.drop_index("ix_agent_versions_agent_id", table_name="agent_versions")
    op.drop_index("ix_agent_versions_ws_status", table_name="agent_versions")
    op.drop_index("uq_agent_versions_active", table_name="agent_versions")
    op.drop_table("agent_versions")
