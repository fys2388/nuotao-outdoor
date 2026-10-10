"""0036_opportunity_domain

新增 Opportunity 数据域（ADR IDENTITY-002 阶段①②）：
``opportunities`` + ``opportunity_candidates``。

设计依据
--------
``docs/OPPORTUNITY_DATA_DOMAIN_DESIGN.md``（设计先行，符合 AGENTS.md §5）。
`market_trend_service` / `competitor_analysis_service` 采集到的市场信号此前没有归属实体，
候选只能凭人工记忆回答「你为什么选这个」。本迁移给信号一个可查询、可引用、可追溯的归属物，
并把它与候选连接起来。

本次变更
--------
1. ``opportunities`` — 一个机会一行。``status`` 是唯一状态轴（刻意不加第二条生命周期列，
   M5.13 的教训是候选与商务状态一旦焊在一个枚举上就会互相污染）；
   ``confidence`` 仅接受人工填写，后端不做推断（AGENTS.md §1.2 禁止凭感觉）；
   ``market_signals`` / ``evidence`` 为追加式 JSONB（信号来源字段集互不兼容，
   强行拉平会得到一张全是 NULL 的宽表）。
2. ``opportunity_candidates`` — 机会 ↔ 产品候选连接表，唯一约束
   ``(workspace_id, opportunity_id, product_id)``；任一端删除级联删除。
   **不级联改写 ``products.candidate_status``** —— 归属关系不等于状态推进，
   候选生命周期状态机归 M5.13 所有。
3. ``opportunities.id`` 复用 0001 的 UUID PK 约定；两表均 ``workspace_id`` 隔离。

非破坏性：无存量数据、无 backfill、不涉及 ``products`` 表任何 DDL。

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# JSON column that stores as JSONB on PostgreSQL (对齐 app.models.base.AI_JSON)。
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

# revision identifiers, used by Alembic.
revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'opportunities',
        op.column('id', sa.Uuid(), nullable=False),
        op.column('workspace_id', sa.Uuid(), nullable=False),
        op.column('title', sa.String(length=128), nullable=False),
        op.column('description', sa.Text(), nullable=True),
        op.column('category', sa.String(length=128), nullable=True),
        op.column('keywords', JSON_TYPE, nullable=False),
        op.column('signal_type', sa.String(length=24), nullable=False, server_default='manual'),
        op.column('signal_source', JSON_TYPE, nullable=True),
        op.column('market_signals', JSON_TYPE, nullable=False),
        op.column('evidence', JSON_TYPE, nullable=False),
        op.column('status', sa.String(length=16), nullable=False, server_default='open'),
        op.column('confidence', sa.Numeric(5, 2), nullable=True),
        op.column('closed_at', sa.DateTime(timezone=True), nullable=True),
        op.column('closed_reason', sa.String(length=256), nullable=True),
        op.column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        op.column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_opportunities_workspace_id', 'opportunities', ['workspace_id'])
    op.create_index('ix_opportunities_status', 'opportunities', ['status'])
    op.create_index(
        'ix_opportunities_ws_status_created',
        'opportunities',
        ['workspace_id', 'status', 'created_at'],
    )
    op.create_index(
        'ix_opportunities_category',
        'opportunities',
        ['workspace_id', 'category'],
    )

    op.create_table(
        'opportunity_candidates',
        op.column('id', sa.Uuid(), nullable=False),
        op.column('workspace_id', sa.Uuid(), nullable=False),
        op.column('opportunity_id', sa.Uuid(), nullable=False),
        op.column('product_id', sa.Uuid(), nullable=False),
        op.column('linked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        op.column('link_reason', sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['opportunity_id'],
            ['opportunities.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['product_id'],
            ['products.id'],
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'workspace_id',
            'opportunity_id',
            'product_id',
            name='uq_opportunity_candidates_ws_opp_product',
        ),
    )
    op.create_index('ix_opportunity_candidates_workspace_id', 'opportunity_candidates', ['workspace_id'])
    op.create_index('ix_opportunity_candidates_opportunity_id', 'opportunity_candidates', ['opportunity_id'])
    op.create_index('ix_opportunity_candidates_product_id', 'opportunity_candidates', ['product_id'])
    op.create_index(
        'ix_opportunity_candidates_product',
        'opportunity_candidates',
        ['workspace_id', 'product_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_opportunity_candidates_product', table_name='opportunity_candidates')
    op.drop_index('ix_opportunity_candidates_product_id', table_name='opportunity_candidates')
    op.drop_index('ix_opportunity_candidates_opportunity_id', table_name='opportunity_candidates')
    op.drop_index('ix_opportunity_candidates_workspace_id', table_name='opportunity_candidates')
    op.drop_table('opportunity_candidates')

    op.drop_index('ix_opportunities_category', table_name='opportunities')
    op.drop_index('ix_opportunities_ws_status_created', table_name='opportunities')
    op.drop_index('ix_opportunities_status', table_name='opportunities')
    op.drop_index('ix_opportunities_workspace_id', table_name='opportunities')
    op.drop_table('opportunities')
