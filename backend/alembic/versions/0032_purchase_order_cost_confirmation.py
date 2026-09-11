"""0032_purchase_order_cost_confirmation

为 purchase_orders 表添加成本确认字段：
cost_confirmed, cost_source, cost_confidence, cost_confirmed_at,
cost_confirmed_by, cost_block_reason。

同时将 status 字段长度从 16 扩展到 24 以支持 pending_cost_confirmation。

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend status column length from 16 to 24 for pending_cost_confirmation.
    op.alter_column('purchase_orders', 'status', type_=sa.String(24), existing_type=sa.String(16), nullable=False)

    # Add cost confirmation columns.
    op.add_column('purchase_orders', sa.Column('cost_confirmed', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('purchase_orders', sa.Column('cost_source', sa.String(32), nullable=False, server_default='unknown'))
    op.add_column('purchase_orders', sa.Column('cost_confidence', sa.Numeric(4, 3), nullable=False, server_default='0'))
    op.add_column('purchase_orders', sa.Column('cost_confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('purchase_orders', sa.Column('cost_confirmed_by', sa.String(128), nullable=True))
    op.add_column('purchase_orders', sa.Column('cost_block_reason', sa.String(500), nullable=True))

    # Add index on cost_confirmed.
    op.create_index('ix_purchase_orders_cost_confirmed', 'purchase_orders', ['cost_confirmed'])


def downgrade() -> None:
    # Remove index.
    op.drop_index('ix_purchase_orders_cost_confirmed', table_name='purchase_orders')

    # Remove cost confirmation columns.
    op.drop_column('purchase_orders', 'cost_block_reason')
    op.drop_column('purchase_orders', 'cost_confirmed_by')
    op.drop_column('purchase_orders', 'cost_confirmed_at')
    op.drop_column('purchase_orders', 'cost_confidence')
    op.drop_column('purchase_orders', 'cost_source')
    op.drop_column('purchase_orders', 'cost_confirmed')

    # Revert status column length.
    op.alter_column('purchase_orders', 'status', type_=sa.String(16), existing_type=sa.String(24), nullable=False)
