"""0034_business_alerts

新增 business_alerts 表（持久化业务告警，支持去重、恢复、重启后状态保留）。

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'business_alerts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('alert_type', sa.String(32), nullable=False),
        sa.Column('resource_type', sa.String(32), nullable=False, server_default='global'),
        sa.Column('resource_id', sa.String(128), nullable=True),
        sa.Column('severity', sa.String(16), nullable=False, server_default='warning'),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('metric_value', sa.Numeric(18, 4), nullable=True),
        sa.Column('threshold_value', sa.Numeric(18, 4), nullable=True),
        sa.Column('metric_name', sa.String(64), nullable=True),
        sa.Column('comparison', sa.String(16), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(128), nullable=True),
        sa.Column('detection_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('trace_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'workspace_id', 'alert_type', 'resource_type', 'resource_id', 'status',
            name='uq_business_alerts_active_dedup',
        ),
    )
    op.create_index('ix_business_alerts_alert_type', 'business_alerts', ['alert_type'])
    op.create_index('ix_business_alerts_resource_id', 'business_alerts', ['resource_id'])
    op.create_index('ix_business_alerts_status', 'business_alerts', ['status'])
    op.create_index('ix_business_alerts_workspace_type_status', 'business_alerts', ['workspace_id', 'alert_type', 'status'])
    op.create_index('ix_business_alerts_workspace_severity', 'business_alerts', ['workspace_id', 'severity'])
    op.create_index('ix_business_alerts_workspace_resource', 'business_alerts', ['workspace_id', 'resource_type', 'resource_id'])


def downgrade() -> None:
    op.drop_index('ix_business_alerts_workspace_resource', table_name='business_alerts')
    op.drop_index('ix_business_alerts_workspace_severity', table_name='business_alerts')
    op.drop_index('ix_business_alerts_workspace_type_status', table_name='business_alerts')
    op.drop_index('ix_business_alerts_status', table_name='business_alerts')
    op.drop_index('ix_business_alerts_resource_id', table_name='business_alerts')
    op.drop_index('ix_business_alerts_alert_type', table_name='business_alerts')
    op.drop_table('business_alerts')
