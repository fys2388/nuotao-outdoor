"""AI Agent 建议模型 — 建议→审批→执行→反馈闭环的核心数据结构。

每个 Agent 生成的优化建议都入库，经人工审批后自动执行，
执行结果回流形成反馈闭环，为 Agent 持续学习提供数据。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, BIGINT_PK, Base, TimestampMixin, WorkspaceMixin

# 建议状态流转: pending_approval → approved → executing → completed
#                                    ↘ rejected
#                                    ↘ failed (执行失败)
SUGGESTION_STATUSES = (
    "pending_approval",  # 待审批
    "approved",          # 已审批，待执行
    "rejected",          # 已拒绝
    "executing",         # 执行中
    "completed",         # 执行完成
    "failed",            # 执行失败
    "skipped",           # 已跳过（人工标记不执行）
)

# 建议类型（对应五大 Agent 的职责域）
SUGGESTION_TYPES = (
    "product_optimization",    # 产品优化（选品/定价/信息）
    "marketing_optimization",  # 营销优化（文案/活动/SEO）
    "inventory_restock",       # 库存补货
    "customer_operation",      # 客户运营（分群/触达/留存）
    "pricing_adjustment",      # 价格调整
    "listing_optimization",    # 上架优化（标题/关键词/图片）
    "supply_chain",            # 供应链优化（采购/物流/供应商）
    "business_insight",        # 商业洞察（报表/趋势/建议）
    "other",                   # 其他
)

# 执行风险等级（决定是否需要人审）
RISK_LEVELS = ("low", "medium", "high")

# 反馈评分（执行后人工/自动评估）
FEEDBACK_SCORES = (1, 2, 3, 4, 5)


class AgentSuggestion(Base, TimestampMixin, WorkspaceMixin):
    """AI Agent 生成的优化建议。

    每条建议记录完整生命周期：生成 → 审批 → 执行 → 反馈。
    """

    __tablename__ = "agent_suggestions"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)

    # --- 来源 ---
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="生成建议的Agent ID")
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="SET NULL"), nullable=True, comment="关联的Agent运行记录"
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="auto", comment="来源: auto(自动生成)/manual(人工录入)/import(导入)"
    )

    # --- 建议内容 ---
    suggestion_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="建议类型"
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="建议标题")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="建议详细描述")
    expected_impact: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预期影响/效果")
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", comment="优先级: high/medium/low"
    )
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", comment="执行风险等级: low/medium/high"
    )

    # --- 执行参数（结构化，供执行路由器解析）---
    execution_params: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict, comment="执行参数（JSON），如 product_id, new_price, campaign_id 等"
    )
    execution_action: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="执行动作标识，如 update_price, restock_inventory, update_listing"
    )

    # --- 状态流转 ---
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_approval", index=True, comment="建议状态"
    )
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="审批人")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="审批意见")

    # --- 飞书集成 ---
    feishu_message_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="飞书审批卡片message_id，用于回调后更新原卡片"
    )

    # --- 执行结果 ---
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_result: Mapped[dict[str, Any]] = mapped_column(
        AI_JSON, nullable=False, default=dict, comment="执行结果（JSON）"
    )
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行错误信息")

    # --- 反馈回流 ---
    feedback_score: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="反馈评分 1-5")
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="反馈意见")
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    learned: Mapped[bool] = mapped_column(default=False, comment="是否已被Agent学习吸收")

    # --- 关联 ---
    agent_run: Mapped["AiAgentRun | None"] = relationship("AiAgentRun", backref="suggestions", lazy="selectin")

    __table_args__ = (
        # 复合索引：按 Agent + 状态 + 优先级查询
        __import__("sqlalchemy").Index(
            "ix_agent_suggestions_agent_status",
            "workspace_id", "agent_id", "status", "priority",
        ),
        # 按类型 + 状态查询
        __import__("sqlalchemy").Index(
            "ix_agent_suggestions_type_status",
            "workspace_id", "suggestion_type", "status",
        ),
    )

    def __repr__(self) -> str:
        return f"<AgentSuggestion id={self.id} agent={self.agent_id} type={self.suggestion_type} status={self.status}>"
