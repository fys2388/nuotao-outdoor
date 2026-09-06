"""成长记忆模型 — Agent 经验持久化积累，跨天/跨周知识不丢失。

记忆类型：
- success_pattern: 成功模式（高评分建议的共性）
- failure_lesson: 失败教训（被拒绝/执行失败的原因）
- market_insight: 市场洞察（趋势/竞品/需求变化）
- customer_preference: 客户偏好（购买行为/反馈/分群特征）
- optimization_result: 优化结果（A/B测试结论/策略调整效果）
- product_knowledge: 产品知识（选品经验/定价规律/供应链信息）

每条记忆有置信度（confidence 0-1），低置信度记忆不自动注入 Agent 上下文，
需人工审核或积累更多证据后提升置信度。
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, BIGINT_PK, Base, TimestampMixin, WorkspaceMixin

# 记忆类型
MEMORY_TYPES = (
    "success_pattern",
    "failure_lesson",
    "market_insight",
    "customer_preference",
    "optimization_result",
    "product_knowledge",
    "other",
)

# 记忆来源
MEMORY_SOURCES = (
    "agent_suggestion",   # 从建议反馈中自动提取
    "agent_run",           # 从 Agent 运行结果中提取
    "manual",              # 人工录入
    "ab_test",             # A/B测试结论
    "data_analysis",       # 数据分析发现
    "import",              # 批量导入
)


class GrowthMemory(Base, TimestampMixin, WorkspaceMixin):
    """Agent 成长记忆。

    每条记忆是一条可被检索、可被注入 Agent 上下文的经验条目。
    """

    __tablename__ = "growth_memories"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)

    # --- 归属 ---
    agent_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="归属Agent ID（'global'表示全局共享）"
    )

    # --- 内容 ---
    memory_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="记忆类型"
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, comment="记忆标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="记忆内容（详细描述）")
    summary: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="一句话摘要（用于快速注入上下文）"
    )

    # --- 元数据 ---
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, comment="标签（用于检索过滤）"
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="agent_suggestion", comment="记忆来源"
    )
    source_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="来源记录ID（如 suggestion_id, run_id）"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, comment="置信度 0-1，低于0.3不自动注入"
    )

    # --- 使用统计 ---
    access_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="被检索/注入次数"
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后被访问时间"
    )
    useful_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="被标记为有用的次数"
    )

    # --- 状态 ---
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active",
        comment="状态: active(活跃)/archived(归档)/pending_review(待审核)"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间（None=永不过期）"
    )

    # --- 额外数据 ---
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", AI_JSON, nullable=False, default=dict, comment="额外元数据（JSON）"
    )

    __table_args__ = (
        # 按 Agent + 类型 + 状态检索
        Index(
            "ix_growth_memories_agent_type_status",
            "workspace_id", "agent_id", "memory_type", "status",
        ),
        # 按标签检索（GIN索引，PostgreSQL特有）
        Index(
            "ix_growth_memories_tags",
            "tags",
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<GrowthMemory id={self.id} agent={self.agent_id} "
            f"type={self.memory_type} confidence={self.confidence:.2f}>"
        )
