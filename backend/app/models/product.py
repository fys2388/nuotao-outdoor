"""Product and product cost models."""

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
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin


class Product(Base, TimestampMixin, WorkspaceMixin):
    """Core product master data. JSON columns leave room for AI extensions."""

    __tablename__ = "products"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    # M5.13 Product Candidate lifecycle (candidate|approved|testing|winner|
    # rejected). NULL means the row is a downstream commerce product (e.g.
    # WooCommerce-synced), not a candidate. Decoupled from `status` which
    # stays the commerce/execution status.
    candidate_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # V3.0 selection funnel (docs/nuotao_product_score_v3.0.md §4); independent
    # of candidate_status. NULL means the row is not in a V3 selection funnel.
    funnel_stage: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    # Latest V1-V12 veto snapshot (list of rule ids / notes); history in
    # product_nuotao_scores. Defaults to an empty list for new rows.
    reject_reasons: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 1688 来源的唯一标识：从链接中提取并规范化后的数字 offer id。
    # NULL 表示该行不是 1688 来源（手工录入、CSV 导入、WooCommerce 反向同步等）。
    # 见 ``uq_products_workspace_source_offer``：同一 workspace 内同一个 1688
    # 链接只允许存在一条活行，这是「同一链接被重复选品」的根本防线。
    source_offer_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    meta: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    # M2.1 product intelligence fields (physical + market targeting).
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    dimensions: Mapped[dict[str, Any] | None] = mapped_column(AI_JSON, nullable=True)
    target_market: Mapped[str] = mapped_column(String(16), nullable=False, default="US")
    # Product Master creation timestamp (Phase 3A).
    # NULL while the product is a candidate; set when the product is
    # approved and promoted to Product Master. Never fabricated.
    mastered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Who approved the Product Master promotion (Phase 3A).
    mastered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Trace ID for the approval that created the Product Master (Phase 3A).
    mastered_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # V3.0 data integrity tracking (Phase 1 of V3 evaluation fix).
    # These fields are populated by the data integrity checker and are used
    # by the V3 selection pipeline to decide whether a candidate has enough
    # structured data to be scored — replacing the silent NEUTRAL=5.0 default
    # that masked missing data. All fields are NULL until the first check runs,
    # so rows created before this migration are not falsely marked incomplete.
    data_integrity_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data_integrity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    data_integrity_missing: Mapped[list[Any]] = mapped_column(
        AI_JSON, nullable=False, default=list
    )
    data_integrity_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_integrity_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_integrity_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    # Soft delete: NULL means the product is live; a timestamp hides it from all
    # business reads while keeping the row for audit and later re-creation.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        # SKU is unique only among live rows within a workspace, so a soft-deleted
        # SKU can be re-imported/re-created without a uniqueness conflict.
        Index(
            "uq_products_workspace_sku",
            "workspace_id",
            "sku",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        # 同一 workspace 内同一个 1688 offer 只允许一条活行。
        # 应用层「先 SELECT 再 INSERT」的查重会被并发绕过（两个请求都查不到、
        # 都插入），数据库约束不会；这是「同一链接被重复选品」的根本防线。
        # 条件里的 IS NOT NULL 让非 1688 来源（手工/CSV/WC 反向同步）不受约束。
        Index(
            "uq_products_workspace_source_offer",
            "workspace_id",
            "source_offer_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND source_offer_id IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND source_offer_id IS NOT NULL"),
        ),
    )

    cost: Mapped["ProductCost | None"] = relationship(
        back_populates="product",
        uselist=False,
        # 不带 delete-orphan：产品删除不得销毁成本数据。
        # ProductCost 是 PROFIT-001 落地成本主数据，属于业务资产
        # （AGENTS.md 1.2 第 4 条「数据是资产」），产品下线、替换、清理都
        # 不该连带抹掉它的采购价与成本明细 —— 下一版产品或复盘分析还要用它。
        # 外键已改为 ondelete="SET NULL"，product_id 保留以便溯源。
        cascade="save-update, merge",
    )


class ProductCost(Base, WorkspaceMixin):
    """Landing cost breakdown per product, following operating rule PROFIT-001.

    ``total_cost`` is the sum of all cost components in the row currency.
    """

    __tablename__ = "product_cost"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    domestic_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    first_leg_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    last_leg_shipping: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # M2.1.5 landed cost model (authoritative breakdown).
    international_shipping: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    packaging: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    handling: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_landed_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    payment_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    marketing_amortization: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    after_sales_loss: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    # Legacy sum of the original components; kept for backward compatibility.
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    notes: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)

    product: Mapped[Product | None] = relationship(back_populates="cost")
