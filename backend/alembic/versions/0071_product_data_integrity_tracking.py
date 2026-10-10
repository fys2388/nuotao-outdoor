"""V3.0 data integrity tracking fields on ``products``.

Adds the columns required by the V3.0 evaluation pipeline to track
whether each candidate has enough structured data to be scored:

* ``data_integrity_status`` — overall completeness status
  (``complete`` / ``partial`` / ``missing``; NULL until the first check).
* ``data_integrity_score`` — numeric completeness score 0-100.
* ``data_integrity_missing`` — JSONB list of missing field names.
* ``data_integrity_checked_at`` — timestamp of the last integrity check.
* ``data_integrity_trace_id`` — trace ID for auditability.
* ``data_integrity_version`` — version of the integrity check logic.

All nullable columns are NULL until the first integrity check runs, so rows
created before this migration are not falsely marked incomplete.
``data_integrity_missing`` and ``data_integrity_version`` carry server
defaults so existing rows get sensible initial values.

Revision ID: 0071
Revises: 0069
Create Date: 2026-10-05

Chains off 0069 rather than 0070: 0070 alters ``product_mappings``, which the
application database role does not own (``must be owner of table
product_mappings``), so it cannot be part of an upgrade path the app role can
actually run. It is kept in-tree as ``0070_product_mapping_workspace_scope.py
.dsh-parked`` for a future run as the table owner.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0071"
down_revision = "0069"
branch_labels = None
depends_on = None

_TABLE = "products"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("data_integrity_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("data_integrity_score", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "data_integrity_missing",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "data_integrity_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("data_integrity_trace_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "data_integrity_version",
            sa.String(length=16),
            nullable=False,
            server_default="v1",
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "data_integrity_version")
    op.drop_column(_TABLE, "data_integrity_trace_id")
    op.drop_column(_TABLE, "data_integrity_checked_at")
    op.drop_column(_TABLE, "data_integrity_missing")
    op.drop_column(_TABLE, "data_integrity_score")
    op.drop_column(_TABLE, "data_integrity_status")
