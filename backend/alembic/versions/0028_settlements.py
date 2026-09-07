"""0028_settlements

创建 settlements 表：回款/结算台账（COD 回款、清关账单、杂费），
支撑运营闭环的资金流可见、可审计与利润核算。

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'settlements',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('order_id', sa.Uuid(), nullable=True),
        sa.Column('external_order_id', sa.String(64), nullable=True),
        sa.Column('carrier', sa.String(64), nullable=False),
        sa.Column('settlement_kind', sa.String(24), nullable=False, server_default='cod'),
        sa.Column('expected_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('received_amount', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('fees', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(8), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(24), nullable=False, server_default='expected'),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.Index('ix_settlements_carrier', 'carrier'),
        sa.Index('ix_settlements_status', 'status'),
        sa.Index('ix_settlements_external_order_id', 'external_order_id'),
        sa.Index('ix_settlements_order_id', 'order_id'),
        sa.Index('ix_settlements_workspace_id', 'workspace_id'),
    )


def downgrade() -> None:
    op.drop_table('settlements')
