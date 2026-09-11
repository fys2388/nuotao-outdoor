"""0027_strategy_versions

创建 strategy_versions 表：策略版本持久化，支撑 A/B 结论自动更新策略的可审计回滚。

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'strategy_versions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('strategy_type', sa.String(32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('old_config', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('new_config', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('changed_by', sa.String(64), nullable=False),
        sa.Column('experiment_id', sa.String(128), nullable=True),
        sa.Column('suggestion_id', sa.BigInteger(), nullable=True),
        sa.Column('change_type', sa.String(16), nullable=False, server_default='update'),
        sa.Column('rolled_back_from', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('workspace_id', sa.String(32), nullable=False),
        sa.Index('ix_strategy_versions_strategy_type', 'strategy_type'),
        sa.Index('ix_strategy_versions_experiment_id', 'experiment_id'),
        sa.Index('ix_strategy_versions_workspace_id', 'workspace_id'),
        sa.ForeignKeyConstraint(
            ['suggestion_id'], ['agent_suggestions.id'], ondelete='SET NULL'
        ),
    )


def downgrade() -> None:
    op.drop_table('strategy_versions')
