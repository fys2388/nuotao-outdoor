"""baseline: establish the migration mechanism

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """M0 baseline: no business tables yet; domain schema arrives with M1."""
    pass


def downgrade() -> None:
    """Reverse of upgrade()."""
    pass
