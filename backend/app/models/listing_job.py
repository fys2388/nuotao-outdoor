"""SOP 阶段 ③「上架工单」—— ListingJob ORM model.

背景
----
PR #7 之前，pipeline 完成 I2I 生图 + 元数据编辑后，直接调用
``listing_publish.push_product_to_woocommerce_gated`` 把商品推到 WooCommerce。
这条「一次性直推」的路径不符合用户 SOP 阶段 ③「提交上架工单 → 人工终审闸门 →
WC API 推送」的语义：没有工单实体、没有 pending/processing/approved/rejected/
published 状态机、没有人工终审闸门、没有回读校验记录。

本模型落地工单实体，与已有的 ``WooCommerceDraft`` 职责分离：

* ``WooCommerceDraft``：human promote 一个 winner 之后的 **payload 快照**
  （只有一层 status = ``generated``，是给 WooCommerce admin 手填用的 hand-off）。
* ``ListingJob``：完整的 **工单生命周期** —— pipeline 组装完成 → pending →
  人工终审 approved / rejected → 触发 WC 推送 → 回读校验 → published / failed。

状态机（严格单向，除 rejected 可 re-submit）
-------------------------------------------
::

    pending ──[review.approve]──▶ approved ──[scheduler.push]──▶ processing
        │                                                              │
        │                                                         ├─[ok]──▶ published
        │                                                         └─[err]─▶ failed ──[retry]──▶ processing
        │
        └──[review.reject]──▶ rejected ──[resubmit]──▶ pending

状态列取值（``status``）
------------------------
* ``pending``    — pipeline 或前端已创建工单，等待人工终审
* ``processing`` — 已获批准，WC 推送进行中（含重试）
* ``approved``   — 人工终审通过，等待调度器抓取推 WC
* ``rejected``   — 人工终审不通过
* ``published``  — WC 已创建/更新，回读校验通过
* ``failed``     — WC 推送在重试预算内仍失败

并发与幂等
----------
* 唯一索引 ``uq_listing_jobs_ws_product_active``：同一 workspace 下每个商品
  只能有一条 status ∈ {pending, approved, processing} 的活跃工单；已终态
  （rejected/published/failed）的历史工单不受约束。这样 pipeline 重复跑
  同一 product 时不会堆积 pending。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

__all__ = [
    "LISTING_JOB_STATUSES",
    "LISTING_JOB_ACTIVE_STATUSES",
    "ListingJob",
    "LISTING_JOB_TERMINAL_STATUSES",
]

# 所有合法 status 取值（用于 API 校验和前端 UI）。
LISTING_JOB_STATUSES: tuple[str, ...] = (
    "pending",
    "approved",
    "processing",
    "rejected",
    "published",
    "failed",
)

# 处于「活跃」状态、同一商品下不允许重复的 status。
LISTING_JOB_ACTIVE_STATUSES: tuple[str, ...] = ("pending", "approved", "processing")

# 已终态、不再回退的 status。
LISTING_JOB_TERMINAL_STATUSES: tuple[str, ...] = ("rejected", "published", "failed")


class ListingJob(Base, TimestampMixin, WorkspaceMixin):
    """SOP 阶段 ③ 上架工单实体。

    一行 = 一个商品的一次上架工单尝试。payload 列冻结提交时刻的完整 WC payload
    快照（供人工终审预览 + WC 推送复用），避免终审时商品被并发编辑导致
    「看到的 ≠ 推的」。
    """

    __tablename__ = "listing_jobs"

    id: Mapped[UUID] = mapped_column("id", primary_key=True, default=uuid4)

    # 关联商品（软删保护：Product 已删除时工单保留 payload 供审计）。
    product_id: Mapped[UUID] = mapped_column(
        "product_id", nullable=False, index=True
    )

    # 提交时刻的商品元数据快照（人工终审 UI 直接展示，不再依赖 product 存在）。
    sku: Mapped[str] = mapped_column("sku", String(64), nullable=False)
    name: Mapped[str] = mapped_column("name", String(255), nullable=False)

    # 提交时刻冻结的完整 WC payload（POST /wp-json/wc/v3/products 用）。
    payload: Mapped[dict[str, Any]] = mapped_column(
        "payload", AI_JSON, nullable=False, default=dict
    )

    # 状态机列（单向状态机，见模块 docstring）。
    status: Mapped[str] = mapped_column(
        "status", String(16), nullable=False, default="pending", index=True
    )

    # 工单备注 / 终审意见 / WC 推送错误信息。
    note: Mapped[str | None] = mapped_column("note", Text, nullable=True)

    # 结构化 reject_reasons（列表，元素为字符串或 {code, message} 字典）。
    reject_reasons: Mapped[list[Any]] = mapped_column(
        "reject_reasons", AI_JSON, nullable=False, default=list
    )

    # 提交者 / 审核者 / WC 推送触发者。
    submitted_by: Mapped[str] = mapped_column(
        "submitted_by", String(128), nullable=False, default="pipeline"
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        "reviewed_by", String(128), nullable=True
    )

    # 生命周期时间戳。
    submitted_at: Mapped[datetime] = mapped_column(
        "submitted_at", DateTime(timezone=True), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        "reviewed_at", DateTime(timezone=True), nullable=True
    )
    pushed_at: Mapped[datetime | None] = mapped_column(
        "pushed_at", DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        "published_at", DateTime(timezone=True), nullable=True
    )

    # 重试计数（WC 推送每次 attempt 加 1；scheduler 层判断是否超过 retry_count >= 3）。
    retry_count: Mapped[int] = mapped_column(
        "retry_count", nullable=False, default=0
    )

    # WC 回读校验后回填。
    wc_product_id: Mapped[int | None] = mapped_column(
        "wc_product_id", nullable=True
    )
    wc_verify_status: Mapped[str | None] = mapped_column(
        "wc_verify_status", String(16), nullable=True
    )
    wc_verify_detail: Mapped[str | None] = mapped_column(
        "wc_verify_detail", Text, nullable=True
    )

    # 链路追踪 ID（贯穿 pipeline → WC → audit）。
    trace_id: Mapped[str | None] = mapped_column(
        "trace_id", String(64), nullable=True
    )

    __table_args__ = (
        Index("ix_listing_jobs_ws_status", "workspace_id", "status"),
        Index("ix_listing_jobs_ws_product_created", "workspace_id", "product_id", "created_at"),
        # 部分唯一索引：同一 workspace 下每个 product 只能有一条活跃工单
        # （status ∈ pending / approved / processing）。历史 rejected/published/failed
        # 工单不受约束，便于保留审计轨迹。
        Index(
            "uq_listing_jobs_ws_product_active",
            "workspace_id",
            "product_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved', 'processing')"),
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端 JSON；datetime 走 isoformat。"""
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "product_id": str(self.product_id),
            "sku": self.sku,
            "name": self.name,
            "payload": self.payload or {},
            "status": self.status,
            "note": self.note,
            "reject_reasons": self.reject_reasons or [],
            "submitted_by": self.submitted_by,
            "reviewed_by": self.reviewed_by,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "pushed_at": self.pushed_at.isoformat() if self.pushed_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "retry_count": self.retry_count,
            "wc_product_id": self.wc_product_id,
            "wc_verify_status": self.wc_verify_status,
            "wc_verify_detail": self.wc_verify_detail,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
