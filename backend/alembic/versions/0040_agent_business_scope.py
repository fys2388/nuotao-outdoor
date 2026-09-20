"""Add B2C/B2B/SHARED business scope to the Agent platform.

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

_SCOPE_CHECK = "business_scope IN ('B2C', 'B2B', 'SHARED')"


def _add_scope(
    table: str,
    *,
    constraint: str,
    index: str | None = None,
) -> None:
    op.add_column(
        table,
        sa.Column(
            "business_scope",
            sa.String(length=8),
            nullable=False,
            server_default="SHARED",
        ),
    )
    op.create_check_constraint(constraint, table, _SCOPE_CHECK)
    if index:
        op.create_index(index, table, ["workspace_id", "business_scope"])


def _drop_scope(
    table: str,
    *,
    constraint: str,
    index: str | None = None,
) -> None:
    if index:
        op.drop_index(index, table_name=table)
    op.drop_constraint(constraint, table, type_="check")
    op.drop_column(table, "business_scope")


def upgrade() -> None:
    _add_scope(
        "agents",
        constraint="ck_agents_business_scope",
        index="ix_agents_workspace_business_scope",
    )
    _add_scope(
        "agent_tasks",
        constraint="ck_agent_tasks_business_scope",
        index="ix_agent_tasks_workspace_business_scope",
    )
    _add_scope(
        "agent_executions",
        constraint="ck_agent_executions_business_scope",
        index="ix_agent_executions_workspace_business_scope",
    )
    _add_scope(
        "agent_tools",
        constraint="ck_agent_tools_business_scope",
        index="ix_agent_tools_workspace_business_scope",
    )
    _add_scope(
        "agent_execution_policies",
        constraint="ck_agent_execution_policies_business_scope",
    )
    _add_scope(
        "agent_budget_policies",
        constraint="ck_agent_budget_policies_business_scope",
    )
    _add_scope(
        "agent_versions",
        constraint="ck_agent_versions_business_scope",
    )
    _add_scope(
        "agent_approval_roles",
        constraint="ck_agent_approval_roles_business_scope",
        index="ix_agent_approval_roles_ws_business_scope",
    )
    _add_scope(
        "agent_approvals",
        constraint="ck_agent_approvals_business_scope",
        index="ix_agent_approvals_ws_business_scope",
    )

    op.drop_constraint(
        "uq_agent_exec_pol_ws_agent_ver",
        "agent_execution_policies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_exec_pol_ws_agent_scope_ver",
        "agent_execution_policies",
        ["workspace_id", "agent_id", "business_scope", "policy_version"],
    )
    op.drop_constraint(
        "uq_agent_budget_pol_ws_agent_ver",
        "agent_budget_policies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_budget_pol_ws_agent_scope_ver",
        "agent_budget_policies",
        ["workspace_id", "agent_id", "business_scope", "policy_version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_agent_budget_pol_ws_agent_scope_ver",
        "agent_budget_policies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_budget_pol_ws_agent_ver",
        "agent_budget_policies",
        ["workspace_id", "agent_id", "policy_version"],
    )
    op.drop_constraint(
        "uq_agent_exec_pol_ws_agent_scope_ver",
        "agent_execution_policies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_exec_pol_ws_agent_ver",
        "agent_execution_policies",
        ["workspace_id", "agent_id", "policy_version"],
    )

    _drop_scope(
        "agent_approvals",
        constraint="ck_agent_approvals_business_scope",
        index="ix_agent_approvals_ws_business_scope",
    )
    _drop_scope(
        "agent_approval_roles",
        constraint="ck_agent_approval_roles_business_scope",
        index="ix_agent_approval_roles_ws_business_scope",
    )
    _drop_scope(
        "agent_versions",
        constraint="ck_agent_versions_business_scope",
    )
    _drop_scope(
        "agent_budget_policies",
        constraint="ck_agent_budget_policies_business_scope",
    )
    _drop_scope(
        "agent_execution_policies",
        constraint="ck_agent_execution_policies_business_scope",
    )
    _drop_scope(
        "agent_tools",
        constraint="ck_agent_tools_business_scope",
        index="ix_agent_tools_workspace_business_scope",
    )
    _drop_scope(
        "agent_executions",
        constraint="ck_agent_executions_business_scope",
        index="ix_agent_executions_workspace_business_scope",
    )
    _drop_scope(
        "agent_tasks",
        constraint="ck_agent_tasks_business_scope",
        index="ix_agent_tasks_workspace_business_scope",
    )
    _drop_scope(
        "agents",
        constraint="ck_agents_business_scope",
        index="ix_agents_workspace_business_scope",
    )
