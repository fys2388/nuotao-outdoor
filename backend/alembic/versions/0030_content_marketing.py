"""0030_content_marketing

创建内容营销三表：content_items（内容生成+审核流）、edm_campaigns（EDM营销活动）、
seo_records（SEO关键词与排名），替代原 JSON 文件存储，支撑 M3 营销与内容系统的
数据持久化、审核工作流和可查询性。

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # content_items: AI生成内容（卖点/SEO文章/EDM草稿/广告文案）+ 审核工作流
    op.create_table(
        'content_items',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('content_type', sa.String(32), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('content_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='draft'),
        sa.Column('language', sa.String(8), nullable=False, server_default='en'),
        sa.Column('keywords', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column('quality_score', sa.Numeric(5, 2), nullable=True),
        sa.Column('approved_by', sa.String(128), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(500), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('source', sa.String(32), nullable=False, server_default='ai_generated'),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.Index('ix_content_workspace_type_status', 'workspace_id', 'content_type', 'status'),
        sa.Index('ix_content_workspace_product', 'workspace_id', 'product_id'),
    )

    # edm_campaigns: EDM营销活动 + 发送指标 + 自动化流程配置
    op.create_table(
        'edm_campaigns',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('campaign_type', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='draft'),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('from_name', sa.String(128), nullable=False, server_default='Nuotao Outdoor'),
        sa.Column('from_email', sa.String(255), nullable=False, server_default='noreply@nuotaooutdoor.com'),
        sa.Column('template_id', sa.String(128), nullable=True),
        sa.Column('content_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('flow_config', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('segment_filter', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('total_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_delivered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_opened', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_clicked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_converted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_unsubscribed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('revenue_attributed', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(8), nullable=False, server_default='USD'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Index('ix_edm_workspace_type_status', 'workspace_id', 'campaign_type', 'status'),
    )

    # seo_records: SEO关键词策略 + 排名快照 + Meta信息
    op.create_table(
        'seo_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('keyword', sa.String(255), nullable=False),
        sa.Column('target_url', sa.String(1024), nullable=True),
        sa.Column('target_page_type', sa.String(32), nullable=False, server_default='product'),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('language', sa.String(8), nullable=False, server_default='en'),
        sa.Column('country', sa.String(8), nullable=False, server_default='US'),
        sa.Column('search_volume', sa.Integer(), nullable=True),
        sa.Column('keyword_difficulty', sa.Numeric(5, 2), nullable=True),
        sa.Column('current_position', sa.Integer(), nullable=True),
        sa.Column('best_position', sa.Integer(), nullable=True),
        sa.Column('ranking_history', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column('meta_title', sa.String(300), nullable=True),
        sa.Column('meta_description', sa.String(500), nullable=True),
        sa.Column('structured_data_type', sa.String(64), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('notes', sa.String(1000), nullable=True),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.Index('ix_seo_workspace_keyword', 'workspace_id', 'keyword'),
        sa.Index('ix_seo_workspace_status', 'workspace_id', 'status'),
        sa.Index('ix_seo_workspace_product', 'workspace_id', 'product_id'),
    )


def downgrade() -> None:
    op.drop_table('seo_records')
    op.drop_table('edm_campaigns')
    op.drop_table('content_items')
