"""M4.3: real data connectors + decision intelligence

Adds ``connector_runs`` (audit of every external data synchronization) and
``business_recommendations`` (proposals that require human approval).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the M4.3 connector and decision intelligence tables."""

    # --- connector_runs ------------------------------------------------------
    op.create_table(
        "connector_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("connector_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("records_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_connector_runs_workspace_name",
        "connector_runs",
        ["workspace_id", "connector_name"],
    )
    op.create_index(
        "ix_connector_runs_workspace_status",
        "connector_runs",
        ["workspace_id", "status"],
    )

    # --- business_recommendations ---------------------------------------------
    op.create_table(
        "business_recommendations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("recommendation", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=True),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
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
        "ix_recommendations_workspace_status",
        "business_recommendations",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_recommendations_workspace_domain",
        "business_recommendations",
        ["workspace_id", "domain"],
    )


def downgrade() -> None:
    """Drop the M4.3 tables (not for production)."""
    op.drop_table("business_recommendations")
    op.drop_table("connector_runs")
