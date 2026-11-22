"""0090: supplier_profiles risk score + product_cost source/confidence (M4.2.0 T0.5).

Adds the numeric risk score for M4.2.1 supplier intelligence and the cost
source/confidence columns for M4.2.2 costing. All new columns are nullable with
no default, so existing rows stay NULL (meaning "not yet quantified / unlabeled")
and no historical data is fabricated.

supplier_profiles new columns:
- risk_score: numeric risk score (Numeric(5,2), 0-100, higher = riskier),
  alongside the qualitative risk_level.
- risk_score_model_version: model version that produced the score.
- risk_score_calibrated_at: calibration timestamp (UTC).

product_cost new columns:
- source: cost source category (manual/1688/quote/verified etc.).
- confidence: source confidence (Numeric(3,2), 0-1); unverified sources score
  low, feeding the M4.2.2 costing gate (UNKNOWN downgrade).

Revision: 0090
Create Date: 2026-11-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_profiles",
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "supplier_profiles",
        sa.Column("risk_score_model_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "supplier_profiles",
        sa.Column("risk_score_calibrated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("product_cost", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column(
        "product_cost",
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_cost", "confidence")
    op.drop_column("product_cost", "source")
    op.drop_column("supplier_profiles", "risk_score_calibrated_at")
    op.drop_column("supplier_profiles", "risk_score_model_version")
    op.drop_column("supplier_profiles", "risk_score")
