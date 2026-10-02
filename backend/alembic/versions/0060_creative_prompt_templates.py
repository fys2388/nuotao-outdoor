"""Creative Prompt Template Registry (v0.17 C2).

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-01

Adds the ``creative_prompt_templates`` table for storing reusable AI prompt
templates. Templates are versioned, categorized by asset type and product
category, and tracked for quality and usage.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the creative_prompt_templates table."""
    op.create_table(
        "creative_prompt_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("template_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "variables",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "default_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("quality_score", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_creative_templates_workspace_key",
        "creative_prompt_templates",
        ["workspace_id", "template_key"],
    )
    op.create_index(
        "ix_creative_templates_workspace_category",
        "creative_prompt_templates",
        ["workspace_id", "category"],
    )
    op.create_index(
        "ix_creative_templates_workspace_status",
        "creative_prompt_templates",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    """Drop the creative_prompt_templates table."""
    op.drop_index("ix_creative_templates_workspace_status", table_name="creative_prompt_templates")
    op.drop_index("ix_creative_templates_workspace_category", table_name="creative_prompt_templates")
    op.drop_index("ix_creative_templates_workspace_key", table_name="creative_prompt_templates")
    op.drop_table("creative_prompt_templates")
