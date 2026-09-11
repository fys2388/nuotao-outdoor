"""M3.2: marketing learning loop - evaluations, creative analysis, knowledge, calibration

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M3.2 marketing learning loop tables."""

    # --- campaign_ai_evaluations --------------------------------------------
    op.create_table(
        "campaign_ai_evaluations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "campaign_id", UUID(), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("accuracy", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prediction_result", sa.String(16), nullable=True),
        sa.Column("error_type", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=True),
        sa.Column("confidence_bucket", sa.String(8), nullable=True),
        sa.Column("success_flag", sa.Boolean(), nullable=True),
        sa.Column(
            "metric_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("human_rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_campaign_evaluations_workspace_campaign",
        "campaign_ai_evaluations",
        ["workspace_id", "campaign_id"],
    )
    op.create_index(
        "ix_campaign_evaluations_workspace_bucket",
        "campaign_ai_evaluations",
        ["workspace_id", "confidence_bucket"],
    )
    op.create_index(
        "ix_campaign_evaluations_campaign_id", "campaign_ai_evaluations", ["campaign_id"]
    )

    # --- creative_analysis_runs ---------------------------------------------
    op.create_table(
        "creative_analysis_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "creative_id",
            UUID(),
            sa.ForeignKey("creative_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "analysis_output", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "performance_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_creative_analysis_workspace_creative",
        "creative_analysis_runs",
        ["workspace_id", "creative_id"],
    )
    op.create_index(
        "ix_creative_analysis_runs_creative_id", "creative_analysis_runs", ["creative_id"]
    )

    # --- marketing_knowledge_entries ----------------------------------------
    op.create_table(
        "marketing_knowledge_entries",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column(
            "campaign_id", UUID(), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "creative_id",
            UUID(),
            sa.ForeignKey("creative_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("entry_type", sa.String(32), nullable=False, server_default="creative_pattern"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_marketing_knowledge_workspace_cat",
        "marketing_knowledge_entries",
        ["workspace_id", "category"],
    )
    op.create_index(
        "ix_marketing_knowledge_workspace_campaign",
        "marketing_knowledge_entries",
        ["workspace_id", "campaign_id"],
    )
    op.create_index(
        "ix_marketing_knowledge_workspace_creative",
        "marketing_knowledge_entries",
        ["workspace_id", "creative_id"],
    )
    op.create_index(
        "ix_marketing_knowledge_campaign_id", "marketing_knowledge_entries", ["campaign_id"]
    )
    op.create_index(
        "ix_marketing_knowledge_creative_id", "marketing_knowledge_entries", ["creative_id"]
    )
    op.create_index(
        "ix_marketing_knowledge_entry_type", "marketing_knowledge_entries", ["entry_type"]
    )

    # --- marketing_calibration_runs -----------------------------------------
    op.create_table(
        "marketing_calibration_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("input_snapshot", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "successful_patterns", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "failure_patterns", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("metrics", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.String(2000), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_marketing_calibration_workspace_status",
        "marketing_calibration_runs",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop the M3.2 marketing learning tables (not for production)."""
    op.drop_table("marketing_calibration_runs")
    op.drop_table("marketing_knowledge_entries")
    op.drop_table("creative_analysis_runs")
    op.drop_table("campaign_ai_evaluations")
