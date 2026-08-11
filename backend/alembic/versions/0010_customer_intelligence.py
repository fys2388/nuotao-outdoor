"""M3.3: customer intelligence - profiles, interactions, reviews, refunds, knowledge

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M3.3 customer intelligence tables."""

    # --- customer_profiles ----------------------------------------------------
    op.create_table(
        "customer_profiles",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("customer_reference_id", sa.String(128), nullable=False),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("segment", sa.String(32), nullable=True),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_order_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_profiles_workspace_segment", "customer_profiles", ["workspace_id", "segment"])
    op.execute(
        sa.text(
            "ALTER TABLE customer_profiles ADD CONSTRAINT "
            "uq_customer_profiles_workspace_reference UNIQUE (workspace_id, customer_reference_id)"
        )
    )

    # --- customer_interactions ------------------------------------------------
    op.create_table(
        "customer_interactions",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "customer_id", UUID(), sa.ForeignKey("customer_profiles.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("channel", sa.String(16), nullable=False, server_default="other"),
        sa.Column("interaction_type", sa.String(32), nullable=False, server_default="message"),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_customer_interactions_workspace_customer",
        "customer_interactions",
        ["workspace_id", "customer_id"],
    )
    op.create_index(
        "ix_customer_interactions_workspace_channel",
        "customer_interactions",
        ["workspace_id", "channel"],
    )
    op.create_index("ix_customer_interactions_customer_id", "customer_interactions", ["customer_id"])
    op.create_index("ix_customer_interactions_product_id", "customer_interactions", ["product_id"])

    # --- product_reviews -------------------------------------------------------
    op.create_table(
        "product_reviews",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("platform", sa.String(16), nullable=False, server_default="other"),
        sa.Column("rating", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("issue_type", sa.String(32), nullable=True),
        sa.Column("keywords", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_reviews_workspace_product", "product_reviews", ["workspace_id", "product_id"])
    op.create_index("ix_product_reviews_workspace_sentiment", "product_reviews", ["workspace_id", "sentiment"])
    op.create_index("ix_product_reviews_product_id", "product_reviews", ["product_id"])

    # --- refund_cases ----------------------------------------------------------
    op.create_table(
        "refund_cases",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "order_id", UUID(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="other"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("resolution", sa.String(32), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refund_cases_workspace_category", "refund_cases", ["workspace_id", "category"])
    op.create_index("ix_refund_cases_workspace_product", "refund_cases", ["workspace_id", "product_id"])
    op.create_index("ix_refund_cases_order_id", "refund_cases", ["order_id"])
    op.create_index("ix_refund_cases_product_id", "refund_cases", ["product_id"])

    # --- customer_knowledge_entries --------------------------------------------
    op.create_table(
        "customer_knowledge_entries",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "customer_id", UUID(), sa.ForeignKey("customer_profiles.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("entry_type", sa.String(32), nullable=False, server_default="purchase_pattern"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_customer_knowledge_workspace_cat",
        "customer_knowledge_entries",
        ["workspace_id", "category"],
    )
    op.create_index(
        "ix_customer_knowledge_workspace_customer",
        "customer_knowledge_entries",
        ["workspace_id", "customer_id"],
    )
    op.create_index("ix_customer_knowledge_customer_id", "customer_knowledge_entries", ["customer_id"])
    op.create_index("ix_customer_knowledge_product_id", "customer_knowledge_entries", ["product_id"])
    op.create_index("ix_customer_knowledge_entry_type", "customer_knowledge_entries", ["entry_type"])


def downgrade() -> None:
    """Drop the M3.3 customer intelligence tables (not for production)."""
    op.drop_table("customer_knowledge_entries")
    op.drop_table("refund_cases")
    op.drop_table("product_reviews")
    op.drop_table("customer_interactions")
    op.drop_table("customer_profiles")
