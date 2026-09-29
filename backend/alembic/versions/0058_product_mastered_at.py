"""Add Product.mastered_at, mastered_by, mastered_trace_id for Phase 3A.

Product Master creation timestamp: NULL while the product is a candidate;
set when the product is approved and promoted to Product Master. Never
fabricated. Adds audit trail (who + trace) for the promotion action.

Revision: 0058
Revises: 0057
"""

from alembic import op
import sqlalchemy as sa

revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # mastered_at: timezone-aware datetime, nullable, indexed for workbench queries.
    op.add_column(
        'products',
        sa.Column(
            'mastered_at',
            sa.DateTime(timezone=True),
            nullable=True,
            index=True,
        ),
        postgresql_using='mastered_at',
        sqlite_using='mastered_at',
    )
    # mastered_by: who approved the Product Master promotion.
    op.add_column(
        'products',
        sa.Column('mastered_by', sa.String(length=128), nullable=True),
        postgresql_using='mastered_by',
        sqlite_using='mastered_by',
    )
    # mastered_trace_id: trace ID for the approval that created the Product Master.
    op.add_column(
        'products',
        sa.Column('mastered_trace_id', sa.String(length=64), nullable=True),
        postgresql_using='mastered_trace_id',
        sqlite_using='mastered_trace_id',
    )


def downgrade() -> None:
    op.drop_column('products', 'mastered_trace_id')
    op.drop_column('products', 'mastered_by')
    op.drop_column('products', 'mastered_at')
