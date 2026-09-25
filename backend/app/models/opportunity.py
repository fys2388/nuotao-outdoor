"""Opportunity data domain: market signals aggregation + candidate attribution.

ADR IDENTITY-002 阶段①② 的归属实体。设计依据见
``docs/OPPORTUNITY_DATA_DOMAIN_DESIGN.md``。

边界（刻意不做，见设计文档 §2）：
- 不做 Opportunity 评分 —— 评分唯一载体是 ``product_scores``
- 不写入 ``products.candidate_status`` —— 归属关系不等于状态推进
- 不读写 ``product_scores`` / ``product_decisions``

所有行 workspace 隔离。``market_signals`` / ``evidence`` 为追加式 JSON，
信号形态异构，不做规范化外键（否则得到一张全是 NULL 的宽表）。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# 机会状态：本域唯一状态轴（不新增第二条生命周期列，见设计文档 §3.1）
OPPORTUNITY_STATUSES: tuple[str, ...] = (
    "open",
    "evaluating",
    "converting",
    "closed",
    "discarded",
)

# 信号类型：来源形态完全不同的六类，字段集互不兼容，故只记录类型不做子表
SIGNAL_TYPES: tuple[str, ...] = (
    "search_trend",
    "competitor_gap",
    "review_pain",
    "social",
    "manual",
    "other",
)


class Opportunity(Base, TimestampMixin, WorkspaceMixin):
    """一个市场机会：把异构市场信号聚合为可查询、可引用、可追溯的实体。"""

    __tablename__ = "opportunities"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    keywords: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    signal_type: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    signal_source: Mapped[dict[str, Any] | None] = mapped_column(AI_JSON, nullable=True)
    market_signals: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    evidence: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    # 人工填写的置信度。禁止后端推断（AGENTS.md §1.2 禁止凭感觉）。
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, default=None
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_opportunities_ws_status_created", "workspace_id", "status", "created_at"),
        Index("ix_opportunities_category", "workspace_id", "category"),
    )


class OpportunityCandidate(Base, WorkspaceMixin):
    """机会 ↔ 产品候选 的连接表。

    删除任一端级联删除；**不级联改写 ``products.candidate_status``**——
    候选生命周期状态机归 M5.13 所有，本表只回答「为什么选」。
    """

    __tablename__ = "opportunity_candidates"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    opportunity_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    link_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "opportunity_id",
            "product_id",
            name="uq_opportunity_candidates_ws_opp_product",
        ),
        Index(
            "ix_opportunity_candidates_product",
            "workspace_id",
            "product_id",
        ),
    )
