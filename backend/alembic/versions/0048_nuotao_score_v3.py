"""Nuotao Product Score V3.0 data foundation.

Introduces the data底座 required by docs/nuotao_product_score_v3.0.md:

* ``product_nuotao_scores`` — append-only history of the six-dimension Nuotao
  Score (Value / Utility / Weight&Packability / Durability / Brand Fit /
  Differentiation), total 0-100, grade and the triggered veto reasons.
* ``products.funnel_stage`` — V3.0 selection funnel stage. It is deliberately
  decoupled from the existing M5.13 ``candidate_status`` lifecycle, which is
  left untouched.
* ``products.reject_reasons`` — latest veto snapshot for list-level filtering;
  full per-run evidence stays in ``product_nuotao_scores``.

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

_PRODUCTS = "products"
_SCORE_TABLE = "product_nuotao_scores"


def upgrade() -> None:
    # --- V3.0 Nuotao Score history (append-only) ----------------------------
    op.create_table(
        _SCORE_TABLE,
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "product_id",
            UUID(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Six brand dimensions, each scored 0.0-10.0.
        sa.Column("value_score", sa.Numeric(4, 1), nullable=False, server_default="0"),
        sa.Column("utility_score", sa.Numeric(4, 1), nullable=False, server_default="0"),
        sa.Column(
            "weight_packability_score", sa.Numeric(4, 1), nullable=False, server_default="0"
        ),
        sa.Column("durability_score", sa.Numeric(4, 1), nullable=False, server_default="0"),
        sa.Column("brand_fit_score", sa.Numeric(4, 1), nullable=False, server_default="0"),
        sa.Column("differentiation_score", sa.Numeric(4, 1), nullable=False, server_default="0"),
        # Weighted total 0-100 and V3.0 grade.
        sa.Column("total", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("grade", sa.String(16), nullable=True),
        sa.Column(
            "reject_reasons", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "dimension_evidence",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("rule_version", sa.String(32), nullable=False),
        sa.Column(
            "scored_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_product_nuotao_scores_workspace_id", _SCORE_TABLE, ["workspace_id"]
    )
    op.create_index("ix_product_nuotao_scores_product_id", _SCORE_TABLE, ["product_id"])

    # --- V3.0 funnel stage + latest veto snapshot on products ---------------
    op.add_column(_PRODUCTS, sa.Column("funnel_stage", sa.String(24), nullable=True))
    op.create_index("ix_products_funnel_stage", _PRODUCTS, ["funnel_stage"])
    op.add_column(
        _PRODUCTS,
        sa.Column(
            "reject_reasons",
            JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column(_PRODUCTS, "reject_reasons")
    op.drop_index("ix_products_funnel_stage", table_name=_PRODUCTS)
    op.drop_column(_PRODUCTS, "funnel_stage")
    op.drop_index("ix_product_nuotao_scores_product_id", table_name=_SCORE_TABLE)
    op.drop_index("ix_product_nuotao_scores_workspace_id", table_name=_SCORE_TABLE)
    op.drop_table(_SCORE_TABLE)
