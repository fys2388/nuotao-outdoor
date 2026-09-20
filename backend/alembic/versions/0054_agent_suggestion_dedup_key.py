"""0054_agent_suggestion_dedup_key

为 agent_suggestions 增加 dedup_key 列 + 部分唯一索引，用于调度任务的幂等去重。

背景
----
``app.services.agent_scheduler`` 的 6 个间隔任务由 systemd 以 ``Restart=always``
托管，状态此前只保存在进程内存的 ``last_run`` dict 中。任何重启（发布、OOM、
维护）都会让所有间隔任务在首轮全部触发，而 ``daily_agents.py`` 的建议生成
没有幂等键，结果就是重复建议被批量灌入 ``pending_approval`` 审批队列。

本次变更
--------
1. 新增可空列 ``dedup_key``（``VARCHAR(191)``）；历史行不回填，保持 NULL；
2. 新增**部分唯一索引** ``uq_agent_suggestions_dedup``，仅约束
   ``dedup_key IS NOT NULL`` 的行 —— 因此历史数据与无键调用完全不受影响；
3. 键格式 ``{agent_id}:{suggestion_type}:{dedup_window}``，
   ``dedup_window`` 由调度任务按自身频率给出（如 30 分钟窗口的
   ``20260920-1030``），窗口内重复调用会命中唯一约束而被跳过。

Revision ID: 0054
Revises: 0053
Create Date: 2026-09-20
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'agent_suggestions',
        sa.Column(
            'dedup_key',
            sa.String(191),
            nullable=True,
            comment='幂等键 {agent_id}:{suggestion_type}:{window}；NULL 表示非调度路径产生',
        ),
    )
    # 部分唯一索引：只在 dedup_key 非空时生效，历史行不受约束。
    op.create_index(
        'uq_agent_suggestions_dedup',
        'agent_suggestions',
        ['workspace_id', 'dedup_key'],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_agent_suggestions_dedup',
        table_name='agent_suggestions',
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
    )
    op.drop_column('agent_suggestions', 'dedup_key')
