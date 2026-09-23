"""WooCommerce clickback events — SOP 阶段 ⑤「数据回流」数据底座.

背景
----
BUG #18: 商品上架后，WC 前台的曝光、点击、加购、购买等事件没有回流到系统。
这导致选品评分模型无法利用真实市场反馈做迭代优化。

本模型记录 WC 前台的用户行为事件，按产品和事件类型聚合，供选品评分、
运营看板和复盘分析使用。

数据来源
--------
1. WooCommerce Analytics API (REST) — 定时拉取聚合数据
2. 自定义 webhook — WC 插件推送事件（如 product_viewed, add_to_cart）
3. 手动录入 — 运营手动输入已知的曝光/点击数据

事件类型
--------
- impression  — 商品被展示（搜索结果页、分类页等）
- click       — 用户点击商品进入详情页
- view        — 商品详情页被查看（完整加载）
- add_to_cart — 加入购物车
- purchase    — 下单购买

去重与幂等
----------
同一 source + product_id + event_type + window_start 的记录视为重复，
UPSERT 更新 count 和 window_end。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

__all__ = [
    "CLICKBACK_EVENT_TYPES",
    "WcClickbackEvent",
]

# 合法的事件类型取值。
CLICKBACK_EVENT_TYPES: tuple[str, ...] = (
    "impression",
    "click",
    "view",
    "add_to_cart",
    "purchase",
)


class WcClickbackEvent(Base, TimestampMixin, WorkspaceMixin):
    """WooCommerce 前台用户行为事件记录。

    每行 = 一个产品在一个时间窗口内的某类事件的聚合计数。
    同一 product + event_type + window 只有一条记录（UPSERT 更新）。
    """

    __tablename__ = "wc_clickback_events"

    id: Mapped[UUID] = mapped_column("id", primary_key=True, default=uuid4)

    # 关联产品。
    product_id: Mapped[UUID] = mapped_column(
        "product_id", nullable=False, index=True
    )

    # 事件类型。
    event_type: Mapped[str] = mapped_column(
        "event_type", String(32), nullable=False, index=True
    )

    # 事件计数。
    count: Mapped[int] = mapped_column(
        "count", Integer, nullable=False, default=0
    )

    # 数据时间窗口（UTC）。
    window_start: Mapped[datetime] = mapped_column(
        "window_start", DateTime(timezone=True), nullable=False, index=True
    )
    window_end: Mapped[datetime | None] = mapped_column(
        "window_end", DateTime(timezone=True), nullable=True
    )

    # 数据来源: woocommerce_analytics | custom_webhook | manual。
    source: Mapped[str] = mapped_column(
        "source", String(64), nullable=False, default="woocommerce_analytics"
    )

    # 原始载荷快照（调试/审计用）。
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(
        "raw_payload", AI_JSON, nullable=True
    )

    # 链路追踪 ID。
    trace_id: Mapped[str | None] = mapped_column(
        "trace_id", String(64), nullable=True
    )

    __table_args__ = (
        Index("ix_wc_clickback_ws_product_type", "workspace_id", "product_id", "event_type"),
        Index("ix_wc_clickback_ws_product_window", "workspace_id", "product_id", "window_start"),
        # 部分唯一索引：同一 workspace + product + event_type + window_start 只允许一条记录
        # 用于 UPSERT 去重。
        UniqueConstraint(
            "workspace_id", "product_id", "event_type", "window_start",
            name="uq_wc_clickback_ws_product_type_window",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端 JSON。"""
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "product_id": str(self.product_id),
            "event_type": self.event_type,
            "count": self.count,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "source": self.source,
            "raw_payload": self.raw_payload,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
