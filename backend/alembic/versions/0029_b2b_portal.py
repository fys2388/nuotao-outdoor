"""0029_b2b_portal

创建 B2B 代理商门户相关表：b2b_agents、b2b_product_prices、b2b_orders、b2b_order_items。
支撑独立 B2B 端子（b2b.nuotaooutdoor.com）的代理商认证、分级定价、批量下单。

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 代理商账号表
    op.create_table(
        'b2b_agents',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('agent_number', sa.String(32), nullable=False),
        sa.Column('company_name', sa.String(200), nullable=False),
        sa.Column('contact_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('country', sa.String(64), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('tier', sa.String(16), nullable=False, server_default='bronze'),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('commission_rate', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('discount_percent', sa.Numeric(5, 2), nullable=False, server_default='0'),
        sa.Column('credit_limit', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('current_balance', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('currency', sa.String(8), nullable=False, server_default='USD'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('agent_number', name='uq_b2b_agents_agent_number'),
        sa.UniqueConstraint('email', name='uq_b2b_agents_email'),
        sa.Index('ix_b2b_agents_agent_number', 'agent_number'),
        sa.Index('ix_b2b_agents_email', 'email'),
        sa.Index('ix_b2b_agents_status', 'status'),
    )

    # 分级定价表
    op.create_table(
        'b2b_product_prices',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('tier', sa.String(16), nullable=True),
        sa.Column('agent_id', sa.Uuid(), nullable=True),
        sa.Column('wholesale_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('moq', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('currency', sa.String(8), nullable=False, server_default='USD'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['b2b_agents.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('product_id', 'tier', name='uq_b2b_price_product_tier'),
        sa.UniqueConstraint('product_id', 'agent_id', name='uq_b2b_price_product_agent'),
        sa.Index('ix_b2b_product_prices_product_id', 'product_id'),
        sa.Index('ix_b2b_product_prices_tier', 'tier'),
        sa.Index('ix_b2b_product_prices_agent_id', 'agent_id'),
    )

    # B2B 订单表
    op.create_table(
        'b2b_orders',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('order_number', sa.String(32), nullable=False),
        sa.Column('agent_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('payment_status', sa.String(16), nullable=False, server_default='unpaid'),
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('discount_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('shipping_cost', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(8), nullable=False, server_default='USD'),
        sa.Column('shipping_address', postgresql.JSONB(), nullable=False),
        sa.Column('payment_due_date', sa.Date(), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('tracking_carrier', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['agent_id'], ['b2b_agents.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('order_number', name='uq_b2b_orders_order_number'),
        sa.Index('ix_b2b_orders_order_number', 'order_number'),
        sa.Index('ix_b2b_orders_agent_id', 'agent_id'),
        sa.Index('ix_b2b_orders_status', 'status'),
        sa.Index('ix_b2b_orders_payment_status', 'payment_status'),
    )

    # B2B 订单明细表
    op.create_table(
        'b2b_order_items',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('sku', sa.String(64), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['order_id'], ['b2b_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='RESTRICT'),
        sa.Index('ix_b2b_order_items_order_id', 'order_id'),
    )


def downgrade() -> None:
    op.drop_table('b2b_order_items')
    op.drop_table('b2b_orders')
    op.drop_table('b2b_product_prices')
    op.drop_table('b2b_agents')
