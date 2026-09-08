"""0026_agent_suggestions_growth_memories

创建 agent_suggestions 和 growth_memories 表（之前用 create_all 临时创建，现在正式迁移）。

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # agent_suggestions 表
    op.create_table(
        'agent_suggestions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('agent_id', sa.String(64), nullable=False),
        sa.Column('agent_run_id', sa.BigInteger(), nullable=True),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('suggestion_type', sa.String(32), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('expected_impact', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(16), nullable=False),
        sa.Column('risk_level', sa.String(16), nullable=False),
        sa.Column('execution_params', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('execution_action', sa.String(128), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending_approval'),
        sa.Column('approved_by', sa.String(128), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approval_comment', sa.Text(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('execution_result', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('execution_error', sa.Text(), nullable=True),
        sa.Column('feedback_score', sa.Integer(), nullable=True),
        sa.Column('feedback_comment', sa.Text(), nullable=True),
        sa.Column('feedback_at', sa.DateTime(), nullable=True),
        sa.Column('learned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.String(32), nullable=False),
        sa.Index('ix_agent_suggestions_agent_id', 'agent_id'),
        sa.Index('ix_agent_suggestions_status', 'status'),
        sa.Index('ix_agent_suggestions_workspace_id', 'workspace_id'),
    )

    # growth_memories 表
    op.create_table(
        'growth_memories',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('agent_id', sa.String(64), nullable=False),
        sa.Column('memory_type', sa.String(32), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('summary', sa.String(512), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column('source', sa.String(32), nullable=False),
        sa.Column('source_id', sa.String(128), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('access_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_accessed_at', sa.DateTime(), nullable=True),
        sa.Column('useful_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.String(32), nullable=False),
        sa.Index('ix_growth_memories_agent_id', 'agent_id'),
        sa.Index('ix_growth_memories_memory_type', 'memory_type'),
        sa.Index('ix_growth_memories_status', 'status'),
        sa.Index('ix_growth_memories_workspace_id', 'workspace_id'),
    )


def downgrade() -> None:
    op.drop_table('growth_memories')
    op.drop_table('agent_suggestions')
