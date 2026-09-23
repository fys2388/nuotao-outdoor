"""0056_listing_job

SOP 阶段 ③「上架工单」实体表 —— 补齐 pipeline 直推 WC 缺失的
pending/processing/approved/rejected/published 状态机 + 人工终审闸门 + WC 回读校验记录。

背景
----
PR #7 之前 pipeline 组装完 WC payload 后直接 POST 到 WooCommerce，
没有工单实体、没有人工终审闸门、没有回读校验记录，也不符合用户
SOP 阶段 ③ 的语义要求。

本次变更
--------
1. 新增 ``listing_jobs`` 表：
   - 生命周期状态列 ``status`` (pending/approved/processing/rejected/published/failed)
   - 提交时刻冻结的完整 WC ``payload`` 快照（JSONB）
   - 结构化 ``reject_reasons`` / ``note`` / ``wc_verify_detail``
   - 生命周期时间戳：submitted_at / reviewed_at / pushed_at / published_at
   - WC 回读回填：wc_product_id / wc_verify_status / wc_verify_detail
   - ``retry_count``：WC 推送每次 attempt 加 1
   - ``trace_id``：贯穿 pipeline → WC → audit 的链路追踪
2. 唯一索引 ``uq_listing_jobs_ws_product_active``：同一 workspace 下每个
   product 只能有一条 status ∈ {pending, approved, processing} 的活跃工单；
   已终态（rejected/published/failed）的历史工单不受约束。

数据回填：不回填。生产库第一次跑此迁移后，所有现有 WC 已发布的商品
不会自动补建工单 —— 这是有意的，避免把历史数据塞进工单表污染审计轨迹。
新流程从 PR #7 起强制走工单。

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'listing_jobs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'payload',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='pending'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column(
            'reject_reasons',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column('submitted_by', sa.String(length=128), nullable=False, server_default='pipeline'),
        sa.Column('reviewed_by', sa.String(length=128), nullable=True),
        sa.Column(
            'submitted_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pushed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('wc_product_id', sa.Integer(), nullable=True),
        sa.Column('wc_verify_status', sa.String(length=16), nullable=True),
        sa.Column('wc_verify_detail', sa.Text(), nullable=True),
        sa.Column('trace_id', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_listing_jobs_workspace_id', 'listing_jobs', ['workspace_id']
    )
    op.create_index('ix_listing_jobs_product_id', 'listing_jobs', ['product_id'])
    op.create_index('ix_listing_jobs_status', 'listing_jobs', ['status'])
    op.create_index(
        'ix_listing_jobs_ws_status', 'listing_jobs', ['workspace_id', 'status']
    )
    op.create_index(
        'ix_listing_jobs_ws_product_created',
        'listing_jobs',
        ['workspace_id', 'product_id', 'created_at'],
    )
    # 部分唯一索引：只约束 status ∈ {pending, approved, processing} 的活跃行。
    op.create_index(
        'uq_listing_jobs_ws_product_active',
        'listing_jobs',
        ['workspace_id', 'product_id'],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending', 'approved', 'processing')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_listing_jobs_ws_product_active',
        table_name='listing_jobs',
        postgresql_where=sa.text(
            "status IN ('pending', 'approved', 'processing')"
        ),
    )
    op.drop_index('ix_listing_jobs_ws_product_created', table_name='listing_jobs')
    op.drop_index('ix_listing_jobs_ws_status', table_name='listing_jobs')
    op.drop_index('ix_listing_jobs_status', table_name='listing_jobs')
    op.drop_index('ix_listing_jobs_product_id', table_name='listing_jobs')
    op.drop_index('ix_listing_jobs_workspace_id', table_name='listing_jobs')
    op.drop_table('listing_jobs')
