"""Add creative_knowledge_entries table for creative learning loop (C7).

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-01

This migration adds the creative_knowledge_entries table which stores
patterns learned from creative assets (success/failure patterns, style
patterns, prompt patterns, etc.). These entries ground the Creative Agent
in evidence when generating new briefs and prompts.
"""

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add creative_knowledge_entries table."""
    op.create_table(
        "creative_knowledge_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("brief_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(128), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["creative_studio_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["brief_id"], ["creative_briefs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_knowledge_workspace_category",
        "creative_knowledge_entries",
        ["workspace_id", "category"],
    )
    op.create_index(
        "ix_creative_knowledge_workspace_product",
        "creative_knowledge_entries",
        ["workspace_id", "product_id"],
    )
    op.create_index(
        "ix_creative_knowledge_workspace_asset",
        "creative_knowledge_entries",
        ["workspace_id", "asset_id"],
    )
    op.create_index(
        "ix_creative_knowledge_workspace_type",
        "creative_knowledge_entries",
        ["workspace_id", "entry_type"],
    )
    op.create_index(
        "ix_creative_knowledge_workspace_asset_type",
        "creative_knowledge_entries",
        ["workspace_id", "asset_type"],
    )
    op.create_index(
        "ix_creative_knowledge_entries_entry_type",
        "creative_knowledge_entries",
        ["entry_type"],
    )
    op.create_index(
        "ix_creative_knowledge_entries_product_id",
        "creative_knowledge_entries",
        ["product_id"],
    )
    op.create_index(
        "ix_creative_knowledge_entries_asset_id",
        "creative_knowledge_entries",
        ["asset_id"],
    )
    op.create_index(
        "ix_creative_knowledge_entries_brief_id",
        "creative_knowledge_entries",
        ["brief_id"],
    )
    op.create_index(
        "ix_creative_knowledge_entries_category",
        "creative_knowledge_entries",
        ["category"],
    )
    op.create_index(
        "ix_creative_knowledge_entries_asset_type",
        "creative_knowledge_entries",
        ["asset_type"],
    )


def downgrade() -> None:
    """Drop creative_knowledge_entries table."""
    op.drop_index("ix_creative_knowledge_entries_asset_type", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_entries_category", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_entries_brief_id", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_entries_asset_id", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_entries_product_id", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_entries_entry_type", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_workspace_asset_type", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_workspace_type", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_workspace_asset", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_workspace_product", table_name="creative_knowledge_entries")
    op.drop_index("ix_creative_knowledge_workspace_category", table_name="creative_knowledge_entries")
    op.drop_table("creative_knowledge_entries")
