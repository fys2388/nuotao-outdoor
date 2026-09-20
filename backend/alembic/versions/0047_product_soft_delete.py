"""Soft delete for products.

Adds ``products.deleted_at`` and replaces the workspace+sku unique constraint
with a partial unique index that only constrains live (non-deleted) rows, so a
soft-deleted SKU can be re-imported or re-created.

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_TABLE = "products"
_UNIQUE = "uq_products_workspace_sku"
_DELETED_INDEX = "ix_products_deleted_at"
_LIVE_WHERE = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(_DELETED_INDEX, _TABLE, ["deleted_at"])

    # Full-table unique constraint -> partial unique index over live rows.
    op.drop_constraint(_UNIQUE, _TABLE, type_="unique")
    op.create_index(
        _UNIQUE,
        _TABLE,
        ["workspace_id", "sku"],
        unique=True,
        postgresql_where=_LIVE_WHERE,
    )


def downgrade() -> None:
    op.drop_index(_UNIQUE, table_name=_TABLE, postgresql_where=_LIVE_WHERE)
    op.create_unique_constraint(_UNIQUE, _TABLE, ["workspace_id", "sku"])
    op.drop_index(_DELETED_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "deleted_at")
