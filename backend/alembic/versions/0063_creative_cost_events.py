"""Add creative_cost_events table for creative cost tracking (C9).

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-01

This migration adds the creative_cost_events table which stores
detailed cost events for creative generation operations. Each event
records the model used, cost estimates, actual costs, and metadata
for comprehensive cost tracking and reporting.
"""

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add creative_cost_events table."""
    op.create_table(
        "creative_cost_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("generation_run_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("brief_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("cost_category", sa.String(32), nullable=False, server_default="generation"),
        sa.Column("estimated_cost", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("actual_cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("context", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generation_run_id"], ["creative_generation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["creative_studio_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["brief_id"], ["creative_briefs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cce_date",
        "creative_cost_events",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_cce_model",
        "creative_cost_events",
        ["workspace_id", "model"],
    )
    op.create_index(
        "ix_cce_asset_type",
        "creative_cost_events",
        ["workspace_id", "asset_type"],
    )
    op.create_index(
        "ix_cce_brief",
        "creative_cost_events",
        ["workspace_id", "brief_id"],
    )
    op.create_index(
        "ix_cce_product",
        "creative_cost_events",
        ["workspace_id", "product_id"],
    )
    op.create_index(
        "ix_cce_run",
        "creative_cost_events",
        ["generation_run_id"],
    )
    op.create_index(
        "ix_cce_asset",
        "creative_cost_events",
        ["asset_id"],
    )
    op.create_index(
        "ix_cce_brief_id",
        "creative_cost_events",
        ["brief_id"],
    )
    op.create_index(
        "ix_cce_product_id",
        "creative_cost_events",
        ["product_id"],
    )
    op.create_index(
        "ix_cce_model_name",
        "creative_cost_events",
        ["model"],
    )
    op.create_index(
        "ix_cce_asset_type_name",
        "creative_cost_events",
        ["asset_type"],
    )
    op.create_index(
        "ix_cce_cost_cat",
        "creative_cost_events",
        ["cost_category"],
    )


def downgrade() -> None:
    """Drop creative_cost_events table."""
    op.drop_index("ix_cce_cost_cat", table_name="creative_cost_events")
    op.drop_index("ix_cce_asset_type_name", table_name="creative_cost_events")
    op.drop_index("ix_cce_model_name", table_name="creative_cost_events")
    op.drop_index("ix_cce_product_id", table_name="creative_cost_events")
    op.drop_index("ix_cce_brief_id", table_name="creative_cost_events")
    op.drop_index("ix_cce_asset", table_name="creative_cost_events")
    op.drop_index("ix_cce_run", table_name="creative_cost_events")
    op.drop_index("ix_cce_product", table_name="creative_cost_events")
    op.drop_index("ix_cce_brief", table_name="creative_cost_events")
    op.drop_index("ix_cce_asset_type", table_name="creative_cost_events")
    op.drop_index("ix_cce_model", table_name="creative_cost_events")
    op.drop_index("ix_cce_date", table_name="creative_cost_events")
    op.drop_table("creative_cost_events")
