"""Add agent agreements, rebate tiers, and rebate accruals.

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "b2b_agent_agreements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agreement_number", sa.String(32), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=False),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "qualification_basis",
            sa.String(16),
            nullable=False,
            server_default="invoiced",
        ),
        sa.Column(
            "calculation_method",
            sa.String(24),
            nullable=False,
            server_default="retroactive",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("terminated_by", sa.String(128), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
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
            "status IN ('draft', 'pending_approval', 'active', 'rejected', 'expired', 'terminated')",
            name="ck_b2b_agent_agreement_status",
        ),
        sa.CheckConstraint(
            "qualification_basis IN ('ordered', 'invoiced', 'paid')",
            name="ck_b2b_agent_agreement_qualification_basis",
        ),
        sa.CheckConstraint(
            "calculation_method = 'retroactive'",
            name="ck_b2b_agent_agreement_calculation_method",
        ),
        sa.CheckConstraint(
            "effective_to > effective_from",
            name="ck_b2b_agent_agreement_period",
        ),
        sa.CheckConstraint(
            "target_amount > 0",
            name="ck_b2b_agent_agreement_target",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "agreement_number",
            name="uq_b2b_agent_agreements_workspace_number",
        ),
    )
    op.create_index(
        "ix_b2b_agent_agreements_workspace_id",
        "b2b_agent_agreements",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_agent_agreements_agent_id",
        "b2b_agent_agreements",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_agent_agreements_status",
        "b2b_agent_agreements",
        ["status"],
    )
    op.create_index(
        "ix_b2b_agent_agreements_workspace_status",
        "b2b_agent_agreements",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_agent_agreements_workspace_agent",
        "b2b_agent_agreements",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_agent_active_agreement",
        "b2b_agent_agreements",
        ["workspace_id", "agent_id"],
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "b2b_rebate_tiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("min_sales_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("max_sales_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("rebate_percent", sa.Numeric(5, 2), nullable=False),
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
            "min_sales_amount >= 0",
            name="ck_b2b_rebate_tier_min",
        ),
        sa.CheckConstraint(
            "max_sales_amount IS NULL OR max_sales_amount > min_sales_amount",
            name="ck_b2b_rebate_tier_range",
        ),
        sa.CheckConstraint(
            "rebate_percent >= 0 AND rebate_percent <= 100",
            name="ck_b2b_rebate_tier_percent",
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["b2b_agent_agreements.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_b2b_rebate_tiers_workspace_id",
        "b2b_rebate_tiers",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_rebate_tiers_agreement_id",
        "b2b_rebate_tiers",
        ["agreement_id"],
    )
    op.create_index(
        "ix_b2b_rebate_tiers_workspace_agreement",
        "b2b_rebate_tiers",
        ["workspace_id", "agreement_id"],
    )

    op.create_table(
        "b2b_rebate_accruals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("accrual_number", sa.String(32), nullable=False),
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("qualification_basis", sa.String(16), nullable=False),
        sa.Column(
            "calculation_method",
            sa.String(24),
            nullable=False,
            server_default="retroactive",
        ),
        sa.Column("qualifying_sales", sa.Numeric(14, 2), nullable=False),
        sa.Column("rebate_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("rebate_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column(
            "evidence",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(128), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('draft', 'pending_approval', 'approved', 'rejected', 'settled')",
            name="ck_b2b_rebate_accrual_status",
        ),
        sa.CheckConstraint(
            "qualification_basis IN ('ordered', 'invoiced', 'paid')",
            name="ck_b2b_rebate_accrual_qualification_basis",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_b2b_rebate_accrual_period",
        ),
        sa.CheckConstraint(
            "qualifying_sales >= 0",
            name="ck_b2b_rebate_accrual_sales",
        ),
        sa.CheckConstraint(
            "rebate_percent >= 0 AND rebate_percent <= 100",
            name="ck_b2b_rebate_accrual_percent",
        ),
        sa.CheckConstraint(
            "rebate_amount >= 0",
            name="ck_b2b_rebate_accrual_amount",
        ),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["b2b_agent_agreements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["b2b_agents.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "accrual_number",
            name="uq_b2b_rebate_accruals_workspace_number",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "agreement_id",
            "period_start",
            "period_end",
            name="uq_b2b_rebate_accruals_workspace_period",
        ),
    )
    op.create_index(
        "ix_b2b_rebate_accruals_workspace_id",
        "b2b_rebate_accruals",
        ["workspace_id"],
    )
    op.create_index(
        "ix_b2b_rebate_accruals_agreement_id",
        "b2b_rebate_accruals",
        ["agreement_id"],
    )
    op.create_index(
        "ix_b2b_rebate_accruals_agent_id",
        "b2b_rebate_accruals",
        ["agent_id"],
    )
    op.create_index(
        "ix_b2b_rebate_accruals_status",
        "b2b_rebate_accruals",
        ["status"],
    )
    op.create_index(
        "ix_b2b_rebate_accruals_workspace_status",
        "b2b_rebate_accruals",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_b2b_rebate_accruals_workspace_agent",
        "b2b_rebate_accruals",
        ["workspace_id", "agent_id"],
    )
    op.create_index(
        "ix_b2b_rebate_accruals_workspace_period",
        "b2b_rebate_accruals",
        ["workspace_id", "period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_b2b_rebate_accruals_workspace_period",
        table_name="b2b_rebate_accruals",
    )
    op.drop_index(
        "ix_b2b_rebate_accruals_workspace_agent",
        table_name="b2b_rebate_accruals",
    )
    op.drop_index(
        "ix_b2b_rebate_accruals_workspace_status",
        table_name="b2b_rebate_accruals",
    )
    op.drop_index(
        "ix_b2b_rebate_accruals_status",
        table_name="b2b_rebate_accruals",
    )
    op.drop_index(
        "ix_b2b_rebate_accruals_agent_id",
        table_name="b2b_rebate_accruals",
    )
    op.drop_index(
        "ix_b2b_rebate_accruals_agreement_id",
        table_name="b2b_rebate_accruals",
    )
    op.drop_index(
        "ix_b2b_rebate_accruals_workspace_id",
        table_name="b2b_rebate_accruals",
    )
    op.drop_table("b2b_rebate_accruals")

    op.drop_index(
        "ix_b2b_rebate_tiers_workspace_agreement",
        table_name="b2b_rebate_tiers",
    )
    op.drop_index(
        "ix_b2b_rebate_tiers_agreement_id",
        table_name="b2b_rebate_tiers",
    )
    op.drop_index(
        "ix_b2b_rebate_tiers_workspace_id",
        table_name="b2b_rebate_tiers",
    )
    op.drop_table("b2b_rebate_tiers")

    op.drop_index(
        "ix_b2b_agent_active_agreement",
        table_name="b2b_agent_agreements",
    )
    op.drop_index(
        "ix_b2b_agent_agreements_workspace_agent",
        table_name="b2b_agent_agreements",
    )
    op.drop_index(
        "ix_b2b_agent_agreements_workspace_status",
        table_name="b2b_agent_agreements",
    )
    op.drop_index(
        "ix_b2b_agent_agreements_status",
        table_name="b2b_agent_agreements",
    )
    op.drop_index(
        "ix_b2b_agent_agreements_agent_id",
        table_name="b2b_agent_agreements",
    )
    op.drop_index(
        "ix_b2b_agent_agreements_workspace_id",
        table_name="b2b_agent_agreements",
    )
    op.drop_table("b2b_agent_agreements")
