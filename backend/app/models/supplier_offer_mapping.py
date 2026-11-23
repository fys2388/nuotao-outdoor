"""Supplier / 1688 Offer independent mapping model (M4 V2.6).

**独立实体,多对多**:一个 WooCommerce 变体(或商品)可对应多个供应商、多个 1688
Offer;同一供应商不同规格与不同 Offer;Offer 更换、失效、历史报价保留。

设计要点:
- 不把 ``source_offer_id`` 设计成变体的一对一属性,而是独立映射实体。
- ``mapping_status``: ``mapped`` / ``unconfirmed`` / ``archived``。
  Offer 失效 ⇒ ``mapping_status='archived'``(保留历史报价,不删除)。
- 冲突策略(服务层实现):同一 (workspace, supplier, offer, variation) 冲突 ⇒
  保留最新 ``effective_at``,旧版本 ``archived``。
- 唯一性(变体级): **仅活跃行**(``mapping_status='mapped'``)唯一
  ``(workspace_id, supplier_id, source_offer_id, wc_variation_id)``
  由部分唯一索引 ``ux_supplier_offer_mapping_variation`` 保证;
  archived 历史行不参与唯一(允许同键历史与当前共存,历史报价保留)。
  商品级(``wc_variation_id IS NULL`` 且 ``mapping_status='mapped'``)
  由部分唯一索引 ``ux_supplier_offer_mapping_product`` 兜底。
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - SQLAlchemy 运行时解析 Mapped[datetime] 注解
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin

# 映射状态(M4 V2.6):mapped 已确认 / unconfirmed 规格不确定 / archived 失效保留.
MAPPING_STATUS_MAPPED = "mapped"
MAPPING_STATUS_UNCONFIRMED = "unconfirmed"
MAPPING_STATUS_ARCHIVED = "archived"
MAPPING_STATUSES = (MAPPING_STATUS_MAPPED, MAPPING_STATUS_UNCONFIRMED, MAPPING_STATUS_ARCHIVED)


class SupplierOfferMapping(Base, TimestampMixin, WorkspaceMixin):
    """Independent supplier<->1688 offer<->WC product/variation mapping.

    One WC variation can map to many suppliers and many offers; a supplier's
    offer can be replaced / invalidated without losing historical quotes
    (rows are archived, never deleted).
    """

    __tablename__ = "supplier_offer_mappings"

    id: Mapped[Any] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    # 供应商维度.可空:映射来源尚无法确定具体供应商时保持 unconfirmed.
    supplier_id: Mapped[Any | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # 1688 Offer 唯一标识(规范化数字 offer id),非空.
    source_offer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # WooCommerce 商品/变体维度.
    wc_product_id: Mapped[int] = mapped_column(Integer, nullable=False)
    wc_variation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 规格映射:供应商规格 -> WC 变体规格的映射证据.不确定时保持未确认.
    specification_mapping: Mapped[dict[str, Any] | None] = mapped_column(AI_JSON, nullable=True, default=dict)
    # 映射状态:mapped / unconfirmed / archived.
    mapping_status: Mapped[str] = mapped_column(String(16), nullable=False, default=MAPPING_STATUS_MAPPED)
    # 证据来源(如 1688 抓取 / 人工确认 / 历史导入).
    evidence_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 报价生效时间(用于冲突时保留最新).
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 外部系统时间戳(报价/来源时间,区别于本地 created_at).
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 写入链路 trace_id(审计).
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        # 变体级唯一(仅活跃行):同一 (workspace, supplier, offer, variation) 仅一条
        # 活跃(mapped)映射;archived 历史不参与唯一,允许同键历史与当前共存.
        Index(
            "ux_supplier_offer_mapping_variation",
            "workspace_id",
            "supplier_id",
            "source_offer_id",
            "wc_variation_id",
            unique=True,
            postgresql_where=text("mapping_status = 'mapped'"),
            sqlite_where=text("mapping_status = 'mapped'"),
        ),
        # 商品级唯一兜底(仅活跃行):同一 (workspace, supplier, offer) 商品级映射仅一条.
        Index(
            "ux_supplier_offer_mapping_product",
            "workspace_id",
            "supplier_id",
            "source_offer_id",
            unique=True,
            postgresql_where=text("wc_variation_id IS NULL AND mapping_status = 'mapped'"),
            sqlite_where=text("wc_variation_id IS NULL AND mapping_status = 'mapped'"),
        ),
        # 查询辅助:按变体/商品检索映射.
        Index("ix_supplier_offer_mapping_wc", "workspace_id", "wc_product_id", "wc_variation_id"),
        Index("ix_supplier_offer_mapping_status", "workspace_id", "mapping_status"),
    )

    def to_summary(self) -> dict[str, Any]:
        """稳定摘要(用于审计/日志)."""
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "supplier_id": str(self.supplier_id) if self.supplier_id else None,
            "source_offer_id": self.source_offer_id,
            "wc_product_id": self.wc_product_id,
            "wc_variation_id": self.wc_variation_id,
            "mapping_status": self.mapping_status,
            "effective_at": self.effective_at.isoformat() if self.effective_at else None,
        }
