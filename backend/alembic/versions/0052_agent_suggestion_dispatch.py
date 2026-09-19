"""Add approval dispatch columns to agent_suggestions.

QA 2026-09-16: AI 建议应先自动分发给对应审核 Agent/负责人审批，只有分发失败
或无人可分发时才回落到中央审批页（/ai/suggestions）人工处理。此前分发结果
不落库，回退原因只留在日志里，导致中央页面把全部待审批建议（含本应被自动
处理的）堆在一起，运营无法区分。

新增列:
- dispatch_status: pending(待分发) / dispatched(已分发审核) / fallback_manual(回退人工)
- dispatch_reviewer: 分发的审核 Agent ID
- dispatch_fallback_reason: 回退人工的原因

历史数据回填:
- 仍停在 pending_approval 的建议 -> fallback_manual（当时即未走完自动审批）
- 其余（已被 Agent 或人工处理过） -> dispatched
"""

from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0050"  # 生产 head 为 0050；V3.1 的 0051 已顺延为 0053（依赖本迁移）
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_suggestions",
        sa.Column(
            "dispatch_status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
            comment="审批分发状态: pending(待分发)/dispatched(已分发审核)/fallback_manual(回退人工审批)",
        ),
    )
    op.add_column(
        "agent_suggestions",
        sa.Column(
            "dispatch_reviewer",
            sa.String(length=64),
            nullable=True,
            comment="分发的审核 Agent/负责人 ID",
        ),
    )
    op.add_column(
        "agent_suggestions",
        sa.Column(
            "dispatch_fallback_reason",
            sa.String(length=256),
            nullable=True,
            comment="回退到人工审批的原因（审核失败/禁用自动审批/需业务确认等）",
        ),
    )
    op.create_index(
        "ix_agent_suggestions_dispatch_status",
        "agent_suggestions",
        ["dispatch_status"],
    )

    # 历史回填：仍待审批的视为当时回退人工；已处理过的视为已完成分发。
    op.execute(
        sa.text(
            """
            UPDATE agent_suggestions
               SET dispatch_status = 'fallback_manual',
                   dispatch_fallback_reason = '历史数据回填：创建时未记录分发结果，默认回退人工审批'
             WHERE status = 'pending_approval'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_suggestions
               SET dispatch_status = 'dispatched'
             WHERE status <> 'pending_approval'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_agent_suggestions_dispatch_status", table_name="agent_suggestions")
    op.drop_column("agent_suggestions", "dispatch_fallback_reason")
    op.drop_column("agent_suggestions", "dispatch_reviewer")
    op.drop_column("agent_suggestions", "dispatch_status")
