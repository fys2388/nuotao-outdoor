"""Add B2B credit policy, risk, hold, and insurance controls.

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "b2b_credit_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("watch_score", sa.Integer(), nullable=False, server_default="35"),
        sa.Column("hold_score", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("freeze_score", sa.Integer(), nullable=False, server_default="80"),
        sa.Column(
            "max_utilization_percent",
            sa.Numeric(7, 2),
            nullable=False,
            server_default="100",
        ),
        sa.Column("max_overdue_days", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("auto_hold_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "auto_freeze_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "insurance_required_above",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(128), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'active', 'rejected', 'superseded')",
            name="ck_b2b_credit_policy_status",
        ),
        sa.CheckConstraint(
            "watch_score >= 0 AND watch_score < hold_score "
            "AND hold_score < freeze_score AND freeze_score <= 100",
            name="ck_b2b_credit_policy_score_order",
        ),
        sa.CheckConstraint(
            "max_utilization_percent >= 0",
            name="ck_b2b_credit_policy_utilization",
        ),
        sa.CheckConstraint(
            "max_overdue_days >= 0",
            name="ck_b2b_credit_policy_overdue",
        ),
        sa.CheckConstraint(
            "insurance_required_above >= 0",
            name="ck_b2b_credit_policy_insurance_required",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "version_number",
            name="uq_b2b_credit_policies_workspace_version",
        ),
    )
    op.create_index(
        "ix_b2b_credit_policies_workspace_id",
        "b2b_credit_policies",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_credit_policies_status",
        "b2b_credit_policies",
        ["status"],
    )
    op.create_index(
        "ix_b2b_credit_policies_workspace_status",
        "b2b_credit_policies",
        ["workspace_id", "status"],
    )
    op.create_index(
        "uq_b2b_credit_policy_active_workspace",
        "b2b_credit_policies",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.add_column(
        "b2b_agents",
        sa.Column(
            "credit_status",
            sa.String(16),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "b2b_agents",
        sa.Column("credit_status_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "b2b_agents",
        sa.Column("credit_status_updated_by", sa.String(128), nullable=True),
    )
    op.add_column(
        "b2b_agents",
        sa.Column(
            "credit_status_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "b2b_agents",
        sa.Column("credit_policy_id", sa.Uuid(), nullable=True),
    )
    op.create_check_constraint(
        "ck_b2b_agents_credit_status",
        "b2b_agents",
        "credit_status IN ('normal', 'watch', 'hold', 'frozen')",
    )
    op.create_foreign_key(
        "fk_b2b_agents_credit_policy_id",
        "b2b_agents",
        "b2b_credit_policies",
        ["credit_policy_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_b2b_agents_credit_status",
        "b2b_agents",
        ["credit_status"],
    )
    op.create_index(
        "ix_b2b_agents_workspace_credit_status",
        "b2b_agents",
        ["workspace_id", "credit_status"],
    )

    op.create_table(
        "b2b_credit_risk_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("recommended_action", sa.String(16), nullable=False),
        sa.Column("applied_action", sa.String(16), nullable=False, server_default="none"),
        sa.Column("credit_status_before", sa.String(16), nullable=False),
        sa.Column("credit_status_after", sa.String(16), nullable=False),
        sa.Column("exposure_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("overdue_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("utilization_percent", sa.Numeric(9, 2), nullable=False),
        sa.Column("overdue_ratio_percent", sa.Numeric(9, 2), nullable=False),
        sa.Column("max_days_overdue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "past_due_invoice_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "written_off_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "insurance_coverage_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "insurance_coverage_percent",
            sa.Numeric(7, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("net_exposure_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("assessed_by", sa.String(128), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_b2b_credit_score"),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_b2b_credit_risk_level",
        ),
        sa.CheckConstraint(
            "recommended_action IN ('none', 'watch', 'hold', 'freeze')",
            name="ck_b2b_credit_recommended_action",
        ),
        sa.CheckConstraint(
            "applied_action IN ('none', 'watch', 'hold', 'freeze')",
            name="ck_b2b_credit_applied_action",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["b2b_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["b2b_credit_policies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_b2b_credit_risk_assessments_workspace_id",
        "b2b_credit_risk_assessments",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_credit_risk_assessments_agent_id",
        "b2b_credit_risk_assessments",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_risk_assessments_policy_id",
        "b2b_credit_risk_assessments",
        ["policy_id"],
    )
    op.create_index(
        "ix_b2b_credit_assessments_workspace_agent",
        "b2b_credit_risk_assessments",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_assessments_workspace_assessed",
        "b2b_credit_risk_assessments",
        ["workspace_id", "assessed_at"],
    )

    op.create_table(
        "b2b_credit_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("previous_status", sa.String(16), nullable=False),
        sa.Column("new_status", sa.String(16), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "previous_status IN ('normal', 'watch', 'hold', 'frozen')",
            name="ck_b2b_credit_event_previous_status",
        ),
        sa.CheckConstraint(
            "new_status IN ('normal', 'watch', 'hold', 'frozen')",
            name="ck_b2b_credit_event_new_status",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["b2b_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["b2b_credit_risk_assessments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_b2b_credit_status_events_workspace_id",
        "b2b_credit_status_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_credit_status_events_agent_id",
        "b2b_credit_status_events",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_status_events_assessment_id",
        "b2b_credit_status_events",
        ["assessment_id"],
    )
    op.create_index(
        "ix_b2b_credit_events_workspace_agent",
        "b2b_credit_status_events",
        ["workspace_id", "agent_id"],
    )

    op.create_table(
        "b2b_credit_insurance_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("policy_number", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("coverage_limit", sa.Numeric(14, 2), nullable=False),
        sa.Column("coverage_percent", sa.Numeric(7, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'expired', 'cancelled')",
            name="ck_b2b_credit_insurance_status",
        ),
        sa.CheckConstraint("coverage_limit > 0", name="ck_b2b_credit_insurance_limit"),
        sa.CheckConstraint(
            "coverage_percent > 0 AND coverage_percent <= 100",
            name="ck_b2b_credit_insurance_percent",
        ),
        sa.CheckConstraint(
            "effective_to >= effective_from",
            name="ck_b2b_credit_insurance_period",
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["b2b_agents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "policy_number",
            name="uq_b2b_credit_insurance_workspace_number",
        ),
    )
    op.create_index(
        "ix_b2b_credit_insurance_policies_workspace_id",
        "b2b_credit_insurance_policies",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_policies_agent_id",
        "b2b_credit_insurance_policies",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_policies_status",
        "b2b_credit_insurance_policies",
        ["status"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_workspace_agent",
        "b2b_credit_insurance_policies",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_workspace_effective",
        "b2b_credit_insurance_policies",
        ["workspace_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "b2b_credit_insurance_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("claim_number", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("claimed_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "recovered_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("settled_by", sa.String(128), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settlement_reference", sa.String(160), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'rejected', 'settled')",
            name="ck_b2b_credit_claim_status",
        ),
        sa.CheckConstraint("claimed_amount > 0", name="ck_b2b_credit_claim_amount"),
        sa.CheckConstraint(
            "recovered_amount >= 0 AND recovered_amount <= claimed_amount",
            name="ck_b2b_credit_claim_recovered",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["b2b_credit_insurance_policies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["b2b_invoices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_id"], ["b2b_agents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "claim_number",
            name="uq_b2b_credit_claims_workspace_number",
        ),
    )
    op.create_index(
        "ix_b2b_credit_insurance_claims_workspace_id",
        "b2b_credit_insurance_claims",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_claims_policy_id",
        "b2b_credit_insurance_claims",
        ["policy_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_claims_invoice_id",
        "b2b_credit_insurance_claims",
        ["invoice_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_claims_agent_id",
        "b2b_credit_insurance_claims",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_insurance_claims_status",
        "b2b_credit_insurance_claims",
        ["status"],
    )
    op.create_index(
        "ix_b2b_credit_claims_workspace_agent",
        "b2b_credit_insurance_claims",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_credit_claims_workspace_status",
        "b2b_credit_insurance_claims",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_b2b_credit_claims_workspace_status",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_index(
        "ix_b2b_credit_claims_workspace_agent",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_claims_status",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_claims_agent_id",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_claims_invoice_id",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_claims_policy_id",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_claims_workspace_id",
        table_name="b2b_credit_insurance_claims",
    )
    op.drop_table("b2b_credit_insurance_claims")

    op.drop_index(
        "ix_b2b_credit_insurance_workspace_effective",
        table_name="b2b_credit_insurance_policies",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_workspace_agent",
        table_name="b2b_credit_insurance_policies",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_policies_status",
        table_name="b2b_credit_insurance_policies",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_policies_agent_id",
        table_name="b2b_credit_insurance_policies",
    )
    op.drop_index(
        "ix_b2b_credit_insurance_policies_workspace_id",
        table_name="b2b_credit_insurance_policies",
    )
    op.drop_table("b2b_credit_insurance_policies")

    op.drop_index(
        "ix_b2b_credit_events_workspace_agent",
        table_name="b2b_credit_status_events",
    )
    op.drop_index(
        "ix_b2b_credit_status_events_assessment_id",
        table_name="b2b_credit_status_events",
    )
    op.drop_index(
        "ix_b2b_credit_status_events_agent_id",
        table_name="b2b_credit_status_events",
    )
    op.drop_index(
        "ix_b2b_credit_status_events_workspace_id",
        table_name="b2b_credit_status_events",
    )
    op.drop_table("b2b_credit_status_events")

    op.drop_index(
        "ix_b2b_credit_assessments_workspace_assessed",
        table_name="b2b_credit_risk_assessments",
    )
    op.drop_index(
        "ix_b2b_credit_assessments_workspace_agent",
        table_name="b2b_credit_risk_assessments",
    )
    op.drop_index(
        "ix_b2b_credit_risk_assessments_policy_id",
        table_name="b2b_credit_risk_assessments",
    )
    op.drop_index(
        "ix_b2b_credit_risk_assessments_agent_id",
        table_name="b2b_credit_risk_assessments",
    )
    op.drop_index(
        "ix_b2b_credit_risk_assessments_workspace_id",
        table_name="b2b_credit_risk_assessments",
    )
    op.drop_table("b2b_credit_risk_assessments")

    op.drop_index("ix_b2b_agents_workspace_credit_status", table_name="b2b_agents")
    op.drop_index("ix_b2b_agents_credit_status", table_name="b2b_agents")
    op.drop_constraint(
        "fk_b2b_agents_credit_policy_id",
        "b2b_agents",
        type_="foreignkey",
    )
    op.drop_constraint("ck_b2b_agents_credit_status", "b2b_agents", type_="check")
    op.drop_column("b2b_agents", "credit_policy_id")
    op.drop_column("b2b_agents", "credit_status_updated_at")
    op.drop_column("b2b_agents", "credit_status_updated_by")
    op.drop_column("b2b_agents", "credit_status_reason")
    op.drop_column("b2b_agents", "credit_status")

    op.drop_index(
        "uq_b2b_credit_policy_active_workspace",
        table_name="b2b_credit_policies",
    )
    op.drop_index(
        "ix_b2b_credit_policies_workspace_status",
        table_name="b2b_credit_policies",
    )
    op.drop_index(
        "ix_b2b_credit_policies_status",
        table_name="b2b_credit_policies",
    )
    op.drop_index(
        "ix_b2b_credit_policies_workspace_id",
        table_name="b2b_credit_policies",
    )
    op.drop_table("b2b_credit_policies")
