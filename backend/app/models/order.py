"""Order domain models: orders and order_items."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AI_JSON, Base, TimestampMixin, WorkspaceMixin


class Order(Base, TimestampMixin, WorkspaceMixin):
    """E-commerce order mapped from an external system (e.g. WooCommerce).

    PII policy: only non-identifying fields (country, no names/emails/addresses)
    are stored. Monetary fields use Numeric/Decimal. Idempotency is enforced by
    a unique (workspace_id, external_order_id) constraint.
    """

    __tablename__ = "orders"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    external_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")
    payment_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fulfillment_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="woocommerce")
    # Non-PII link to customer_profiles.customer_reference_id (M3.4).
    customer_reference_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    payment_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    advertising_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # Profit engine outputs and rule evaluation results (auditable snapshots).
    profit_snapshot: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)
    rule_results: Mapped[dict[str, Any]] = mapped_column(AI_JSON, nullable=False, default=dict)

    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "external_order_id",
            name="uq_orders_workspace_external",
        ),
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base, TimestampMixin, WorkspaceMixin):
    """Line item of an order."""

    __tablename__ = "order_items"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    order_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    order: Mapped[Order] = relationship(back_populates="items")
