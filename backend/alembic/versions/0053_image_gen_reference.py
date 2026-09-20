"""Add reference_image to image_generation_tasks for I2I generation.

Revision ID: 0053
Revises: 0052
Create Date: 2026-09-19

Adds the optional source-image URL used by Seedream image-to-image calls so
generated listing images stay faithful to the 1688 original. Null means
text-to-image.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_TABLE = "image_generation_tasks"
_COLUMN = "reference_image"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(length=2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, _COLUMN)
