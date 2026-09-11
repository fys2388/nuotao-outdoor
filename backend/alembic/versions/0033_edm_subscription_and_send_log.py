"""0033_edm_subscription_and_send_log

新增 email_subscriptions 表（GDPR订阅同意、退订、发送历史）
和 edm_send_logs 表（发送日志、幂等键、重试、审计）。

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # email_subscriptions table
    op.create_table(
        'email_subscriptions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('email_hash', sa.String(128), nullable=False),
        sa.Column('email_domain', sa.String(255), nullable=True),
        sa.Column('subscription_status', sa.String(32), nullable=False, server_default='pending_confirmation'),
        sa.Column('consent_given', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('consent_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consent_source', sa.String(32), nullable=False, server_default='manual'),
        sa.Column('consent_ip', sa.String(64), nullable=True),
        sa.Column('consent_user_agent', sa.String(500), nullable=True),
        sa.Column('unsubscribe_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unsubscribe_reason', sa.String(500), nullable=True),
        sa.Column('last_email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_emails_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_opened', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_clicked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tags', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'email_hash', name='uq_email_subscriptions_workspace_hash'),
    )
    op.create_index('ix_email_subscriptions_email_hash', 'email_subscriptions', ['email_hash'])
    op.create_index('ix_email_subscriptions_workspace_status', 'email_subscriptions', ['workspace_id', 'subscription_status'])
    op.create_index('ix_email_subscriptions_workspace_consent', 'email_subscriptions', ['workspace_id', 'consent_given'])

    # edm_send_logs table
    op.create_table(
        'edm_send_logs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('campaign_id', sa.Uuid(), nullable=True),
        sa.Column('subscription_id', sa.Uuid(), nullable=True),
        sa.Column('email_hash', sa.String(128), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('skip_reason', sa.String(64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_message_id', sa.String(255), nullable=True),
        sa.Column('provider_response', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('from_email', sa.String(255), nullable=True),
        sa.Column('is_dry_run', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['edm_campaigns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['subscription_id'], ['email_subscriptions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'idempotency_key', name='uq_edm_send_logs_workspace_idempotency'),
    )
    op.create_index('ix_edm_send_logs_email_hash', 'edm_send_logs', ['email_hash'])
    op.create_index('ix_edm_send_logs_workspace_status', 'edm_send_logs', ['workspace_id', 'status'])
    op.create_index('ix_edm_send_logs_workspace_campaign', 'edm_send_logs', ['workspace_id', 'campaign_id'])
    op.create_index('ix_edm_send_logs_workspace_email', 'edm_send_logs', ['workspace_id', 'email_hash'])


def downgrade() -> None:
    op.drop_index('ix_edm_send_logs_workspace_email', table_name='edm_send_logs')
    op.drop_index('ix_edm_send_logs_workspace_campaign', table_name='edm_send_logs')
    op.drop_index('ix_edm_send_logs_workspace_status', table_name='edm_send_logs')
    op.drop_index('ix_edm_send_logs_email_hash', table_name='edm_send_logs')
    op.drop_table('edm_send_logs')

    op.drop_index('ix_email_subscriptions_workspace_consent', table_name='email_subscriptions')
    op.drop_index('ix_email_subscriptions_workspace_status', table_name='email_subscriptions')
    op.drop_index('ix_email_subscriptions_email_hash', table_name='email_subscriptions')
    op.drop_table('email_subscriptions')
