"""M3.1: marketing intelligence - campaigns, creatives, feedback, experiments

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M3.1 marketing intelligence tables."""

    # --- campaigns ----------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("campaign_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("budget", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("spend", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Numeric(8, 6), nullable=True),
        sa.Column("cpc", sa.Numeric(12, 4), nullable=True),
        sa.Column("conversion", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("roas", sa.Numeric(10, 4), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_campaigns_workspace_platform", "campaigns", ["workspace_id", "platform"])
    op.create_index("ix_campaigns_workspace_product", "campaigns", ["workspace_id", "product_id"])
    op.create_index("ix_campaigns_product_id", "campaigns", ["product_id"])
    op.execute(
        sa.text(
            "ALTER TABLE campaigns ADD CONSTRAINT "
            "uq_campaigns_workspace_platform_campaign UNIQUE (workspace_id, platform, campaign_id)"
        )
    )

    # --- creative_assets -----------------------------------------------------
    op.create_table(
        "creative_assets",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("platform", sa.String(16), nullable=False, server_default="meta"),
        sa.Column("asset_type", sa.String(24), nullable=False, server_default="image"),
        sa.Column("reference", sa.String(1024), nullable=True),
        sa.Column("hook", sa.String(500), nullable=True),
        sa.Column("angle", sa.String(255), nullable=True),
        sa.Column("copy", sa.String(2000), nullable=True),
        sa.Column(
            "performance_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_creative_assets_workspace_product", "creative_assets", ["workspace_id", "product_id"]
    )
    op.create_index(
        "ix_creative_assets_workspace_platform", "creative_assets", ["workspace_id", "platform"]
    )
    op.create_index("ix_creative_assets_product_id", "creative_assets", ["product_id"])

    # --- customer_feedback ---------------------------------------------------
    op.create_table(
        "customer_feedback",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("source", sa.String(24), nullable=False, server_default="other"),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("issue_type", sa.String(32), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_feedback_workspace_product", "customer_feedback", ["workspace_id", "product_id"]
    )
    op.create_index(
        "ix_feedback_workspace_sentiment", "customer_feedback", ["workspace_id", "sentiment"]
    )
    op.create_index("ix_feedback_product_id", "customer_feedback", ["product_id"])

    # --- marketing_experiments ----------------------------------------------
    op.create_table(
        "marketing_experiments",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("hypothesis", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("variant_a", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("variant_b", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("calibration", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_marketing_experiments_workspace_product",
        "marketing_experiments",
        ["workspace_id", "product_id"],
    )
    op.create_index(
        "ix_marketing_experiments_workspace_status",
        "marketing_experiments",
        ["workspace_id", "status"],
    )
    op.create_index("ix_marketing_experiments_product_id", "marketing_experiments", ["product_id"])


def downgrade() -> None:
    """Drop the M3.1 marketing tables (not for production)."""
    op.drop_table("marketing_experiments")
    op.drop_table("customer_feedback")
    op.drop_table("creative_assets")
    op.drop_table("campaigns")
