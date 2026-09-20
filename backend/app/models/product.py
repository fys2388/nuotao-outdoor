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
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    meta: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    # M2.1 product intelligence fields (physical + market targeting).
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    dimensions: Mapped[dict[str, Any] | None] = mapped_column(AI_JSON, nullable=True)
    target_market: Mapped[str] = mapped_column(String(16), nullable=False, default="US")
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
    )

    cost: Mapped["ProductCost | None"] = relationship(
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ProductCost(Base, WorkspaceMixin):
    """Landing cost breakdown per product, following operating rule PROFIT-001.

    ``total_cost`` is the sum of all cost components in the row currency.
    """

    __tablename__ = "product_cost"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
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

    product: Mapped[Product] = relationship(back_populates="cost")
