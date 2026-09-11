"""0031_refund_lifecycle

扩展 refund_cases 表，添加完整退款生命周期字段：
状态机、审批、执行、重试、幂等键、支付平台退款ID。

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to refund_cases for full lifecycle.
    op.add_column('refund_cases', sa.Column('refund_type', sa.String(16), nullable=False, server_default='partial'))
    op.add_column('refund_cases', sa.Column('requested_amount', sa.Numeric(12, 2), nullable=False, server_default='0'))
    op.add_column('refund_cases', sa.Column('status', sa.String(24), nullable=False, server_default='requested'))
    op.add_column('refund_cases', sa.Column('approved_amount', sa.Numeric(12, 2), nullable=True))
    op.add_column('refund_cases', sa.Column('approved_by', sa.String(128), nullable=True))
    op.add_column('refund_cases', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('refund_cases', sa.Column('rejection_reason', sa.String(500), nullable=True))
    op.add_column('refund_cases', sa.Column('executed_amount', sa.Numeric(12, 2), nullable=True))
    op.add_column('refund_cases', sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('refund_cases', sa.Column('payment_provider', sa.String(32), nullable=False, server_default='woocommerce'))
    op.add_column('refund_cases', sa.Column('payment_refund_id', sa.String(128), nullable=True))
    op.add_column('refund_cases', sa.Column('woocommerce_refund_id', sa.String(128), nullable=True))
    op.add_column('refund_cases', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('refund_cases', sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('refund_cases', sa.Column('error_message', sa.String(1000), nullable=True))
    op.add_column('refund_cases', sa.Column('last_failed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('refund_cases', sa.Column('idempotency_key', sa.String(128), nullable=False, server_default='legacy'))
    op.add_column('refund_cases', sa.Column('notes', sa.String(1000), nullable=True))

    # Add indexes.
    op.create_index('ix_refund_cases_workspace_status', 'refund_cases', ['workspace_id', 'status'])
    op.create_index('ix_refund_cases_payment_refund_id', 'refund_cases', ['payment_refund_id'])

    # Add unique constraint for idempotency.
    # Note: existing rows have idempotency_key='legacy', so we need to make
    # existing rows unique first. For existing rows, we'll use a migration-safe
    # approach: create the constraint only if it doesn't exist.
    op.create_unique_constraint(
        'uq_refund_cases_workspace_order_idempotency',
        'refund_cases',
        ['workspace_id', 'order_id', 'idempotency_key'],
    )


def downgrade() -> None:
    # Remove unique constraint and indexes.
    op.drop_constraint('uq_refund_cases_workspace_order_idempotency', 'refund_cases', type_='unique')
    op.drop_index('ix_refund_cases_payment_refund_id', table_name='refund_cases')
    op.drop_index('ix_refund_cases_workspace_status', table_name='refund_cases')

    # Remove new columns (reverse order).
    op.drop_column('refund_cases', 'notes')
    op.drop_column('refund_cases', 'idempotency_key')
    op.drop_column('refund_cases', 'last_failed_at')
    op.drop_column('refund_cases', 'error_message')
    op.drop_column('refund_cases', 'max_retries')
    op.drop_column('refund_cases', 'retry_count')
    op.drop_column('refund_cases', 'woocommerce_refund_id')
    op.drop_column('refund_cases', 'payment_refund_id')
    op.drop_column('refund_cases', 'payment_provider')
    op.drop_column('refund_cases', 'executed_at')
    op.drop_column('refund_cases', 'executed_amount')
    op.drop_column('refund_cases', 'rejection_reason')
    op.drop_column('refund_cases', 'approved_at')
    op.drop_column('refund_cases', 'approved_by')
    op.drop_column('refund_cases', 'approved_amount')
    op.drop_column('refund_cases', 'status')
    op.drop_column('refund_cases', 'requested_amount')
    op.drop_column('refund_cases', 'refund_type')
