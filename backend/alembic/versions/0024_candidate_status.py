"""M5.13: product candidate lifecycle status + WooCommerce draft payloads.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the product candidate lifecycle column (nullable) and the commerce
    draft payload table.

    ``candidate_status`` (candidate|approved|testing|winner|rejected) tracks
    the Product Candidate lifecycle and is decoupled from ``products.status``
    which stays the commerce/execution status. WooCommerce-synced rows keep
    ``candidate_status = NULL`` (downstream commerce source, not candidates).

    ``woocommerce_draft_payloads`` stores the generated WooCommerce draft
    payload after a human promotes a winner. Phase 1 never calls the
    WooCommerce write API - the payload is the human hand-off artifact.
    """
    op.add_column(
        "products",
        sa.Column("candidate_status", sa.String(length=16), nullable=True),
    )
    # Non-destructive backfill: intake candidates and in-test products become
    # Product Candidates; WooCommerce-synced rows stay NULL.
    op.execute("UPDATE products SET candidate_status = 'candidate' WHERE status = 'candidate'")
    op.execute("UPDATE products SET candidate_status = 'testing' WHERE status = 'test'")

    op.create_table(
        "woocommerce_draft_payloads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("product_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="generated"),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    """Reverse the M5.13 candidate/commerce boundary."""
    op.drop_table("woocommerce_draft_payloads")
    op.drop_column("products", "candidate_status")
