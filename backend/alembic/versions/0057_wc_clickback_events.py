"""Add wc_clickback_events table for SOP 阶段 ⑤ 数据回流 (BUG #18).

Records WooCommerce front-end user behavior events (impressions, clicks,
views, add-to-cart, purchases) so the selection scoring model can iterate
on real market feedback.

Revision: 0057
Revises: 0056
"""

from alembic import op
import sqlalchemy as sa

revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'wc_clickback_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False, server_default='woocommerce_analytics'),
        sa.Column('raw_payload', sa.JSON(), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_wc_clickback_ws_product_type',
        'wc_clickback_events',
        ['workspace_id', 'product_id', 'event_type'],
    )
    op.create_index(
        'ix_wc_clickback_ws_product_window',
        'wc_clickback_events',
        ['workspace_id', 'product_id', 'window_start'],
    )
    op.create_index(
        'uq_wc_clickback_ws_product_type_window',
        'wc_clickback_events',
        ['workspace_id', 'product_id', 'event_type', 'window_start'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        'uq_wc_clickback_ws_product_type_window',
        table_name='wc_clickback_events',
    )
    op.drop_index(
        'ix_wc_clickback_ws_product_window',
        table_name='wc_clickback_events',
    )
    op.drop_index(
        'ix_wc_clickback_ws_product_type',
        table_name='wc_clickback_events',
    )
    op.drop_table('wc_clickback_events')
