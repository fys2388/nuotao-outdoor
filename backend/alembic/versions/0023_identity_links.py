"""M5.14: identity foundation - organization -> workspace mapping

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the server-side identity -> workspace mapping table.

    ``organization_id`` is the verified Clerk ``org`` claim. The mapping is
    the only accepted source of truth for the request workspace under the
    M5.14 identity chain; ``X-Workspace-Id`` stays a routing hint. No JWT,
    credential or secret is stored here.
    """
    op.create_table(
        "workspace_identity_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=True),
        sa.Column("mapping_metadata", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint(
            "workspace_id", "organization_id", name="uq_workspace_identity_links_ws_org"
        ),
    )


def downgrade() -> None:
    """Reverse the M5.14 identity mapping."""
    op.drop_table("workspace_identity_links")
