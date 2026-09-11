"""M6: e-commerce capabilities — image generation, activity plans, influencers.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add M6 tables: image_generation_tasks, activity_plans, influencers,
    influencer_collaborations."""

    # --- image_generation_tasks ---
    op.create_table(
        "image_generation_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("prompt", sa.String(length=4000), nullable=False),
        sa.Column("negative_prompt", sa.String(length=2000), nullable=True),
        sa.Column("use_case", sa.String(length=32), nullable=False, server_default="main_image"),
        sa.Column("requested_model", sa.String(length=64), nullable=False, server_default="wan2.7-image"),
        sa.Column("actual_model", sa.String(length=64), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("image_path", sa.String(length=1024), nullable=True),
        sa.Column("cost_cny", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_image_gen_workspace_status", "workspace_id", "status"),
        sa.Index("ix_image_gen_workspace_product", "workspace_id", "product_id"),
        sa.Index("ix_image_gen_workspace_use_case", "workspace_id", "use_case"),
    )

    # --- activity_plans ---
    op.create_table(
        "activity_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("activity_type", sa.String(length=32), nullable=False, server_default="other"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("budget_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("budget_currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("target_revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("target_orders", sa.Integer(), nullable=True),
        sa.Column("target_roas", sa.Numeric(8, 2), nullable=True),
        sa.Column("plan_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("approval_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(length=2000), nullable=True),
        sa.Column("parent_plan_id", sa.Uuid(), sa.ForeignKey("activity_plans.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_activity_plans_workspace_status", "workspace_id", "status"),
        sa.Index("ix_activity_plans_workspace_type", "workspace_id", "activity_type"),
        sa.Index("ix_activity_plans_workspace_approval", "workspace_id", "approval_status"),
    )

    # --- influencers ---
    op.create_table(
        "influencers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False, server_default="instagram"),
        sa.Column("profile_url", sa.String(length=2048), nullable=True),
        sa.Column("followers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("avg_views", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_info", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("rating", sa.Numeric(3, 1), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_influencers_workspace_platform", "workspace_id", "platform"),
        sa.Index("ix_influencers_workspace_category", "workspace_id", "category"),
        sa.Index("ix_influencers_workspace_region", "workspace_id", "region"),
    )

    # --- influencer_collaborations ---
    op.create_table(
        "influencer_collaborations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("influencer_id", sa.Uuid(), sa.ForeignKey("influencers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("activity_plan_id", sa.Uuid(), sa.ForeignKey("activity_plans.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("collab_type", sa.String(length=32), nullable=False, server_default="product_seeding"),
        sa.Column("compensation_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("compensation_currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("commission_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("content_requirements", sa.String(length=2000), nullable=True),
        sa.Column("content_url", sa.String(length=2048), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="prospecting"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Index("ix_collab_workspace_influencer", "workspace_id", "influencer_id"),
        sa.Index("ix_collab_workspace_activity", "workspace_id", "activity_plan_id"),
        sa.Index("ix_collab_workspace_status", "workspace_id", "status"),
    )


def downgrade() -> None:
    """Reverse M6 migration."""
    op.drop_table("influencer_collaborations")
    op.drop_table("influencers")
    op.drop_table("activity_plans")
    op.drop_table("image_generation_tasks")
