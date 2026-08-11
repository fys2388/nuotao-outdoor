"""M2.3: learning loop - evaluation classification + calibration + knowledge

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend evaluations and add the calibration/knowledge tables."""

    # --- product_ai_evaluations: learning-loop classification columns --------
    for column in (
        sa.Column("prediction_result", sa.String(16), nullable=True),
        sa.Column("error_type", sa.String(32), nullable=True),
        sa.Column("confidence_bucket", sa.String(8), nullable=True),
        sa.Column("success_flag", sa.Boolean(), nullable=True),
        sa.Column(
            "metric_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    ):
        op.add_column("product_ai_evaluations", column)

    # --- confidence_calibration ----------------------------------------------
    op.create_table(
        "confidence_calibration",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("bucket", sa.String(8), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("avg_confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_confidence_calibration_workspace", "confidence_calibration", ["workspace_id"])
    op.execute(
        sa.text(
            "ALTER TABLE confidence_calibration ADD CONSTRAINT "
            "uq_confidence_calibration_workspace_bucket UNIQUE (workspace_id, bucket)"
        )
    )

    # --- score_calibration_runs ----------------------------------------------
    op.create_table(
        "score_calibration_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("current_weights", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("suggested_weights", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("input_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_score_calibration_runs_workspace", "score_calibration_runs", ["workspace_id"])
    op.execute(
        sa.text(
            "CREATE INDEX ix_score_calibration_runs_status "
            "ON score_calibration_runs (workspace_id, status)"
        )
    )

    # --- product_knowledge_entries -------------------------------------------
    op.create_table(
        "product_knowledge_entries",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("entry_type", sa.String(32), nullable=False, server_default="category_insight"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_knowledge_entries_workspace", "product_knowledge_entries", ["workspace_id"])
    op.create_index("ix_product_knowledge_entries_product", "product_knowledge_entries", ["product_id"])
    op.create_index("ix_product_knowledge_entries_type", "product_knowledge_entries", ["entry_type"])
    op.execute(
        sa.text(
            "CREATE INDEX ix_knowledge_entries_workspace_cat "
            "ON product_knowledge_entries (workspace_id, category)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_knowledge_entries_workspace_product "
            "ON product_knowledge_entries (workspace_id, product_id)"
        )
    )


def downgrade() -> None:
    """Drop the M2.3 tables and evaluation columns (not for production)."""
    op.drop_table("product_knowledge_entries")
    op.drop_table("score_calibration_runs")
    op.drop_table("confidence_calibration")
    for column in ("metric_snapshot", "success_flag", "confidence_bucket", "error_type", "prediction_result"):
        op.drop_column("product_ai_evaluations", column)
