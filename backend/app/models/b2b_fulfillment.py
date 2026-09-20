"""B2B order fulfillment linkage to WMS inventory and TMS shipments."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, WorkspaceMixin

B2B_FULFILLMENT_STATUSES = (
    "reserved",
    "shipped",
    "delivered",
    "released",
)


class B2BFulfillment(Base, TimestampMixin, WorkspaceMixin):
    """One auditable fulfillment record for a B2B order.

    Inventory is reserved first and can only be released while unshipped.
    Shipping consumes both ``quantity`` and ``reserved`` and creates a TMS
    shipment row; the order status is driven by this record, never directly
    by a generic status update.
    """

    __tablename__ = "b2b_order_fulfillments"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    fulfillment_number: Mapped[str] = mapped_column(String(32), nullable=False)
    order_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="reserved",
        index=True,
    )
    warehouse_location: Mapped[str] = mapped_column(String(32), nullable=False)
    shipment_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("shipment_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reservation_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shipment_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    items: Mapped[list["B2BFulfillmentItem"]] = relationship(
        back_populates="fulfillment",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "fulfillment_number",
            name="uq_b2b_fulfillments_workspace_number",
        ),
        UniqueConstraint(
            "workspace_id",
            "order_id",
            name="uq_b2b_fulfillments_workspace_order",
        ),
        CheckConstraint(
            "warehouse_location IN ('cn', 'us', 'eu')",
            name="ck_b2b_fulfillment_warehouse",
        ),
        Index(
            "ix_b2b_fulfillments_workspace_status",
            "workspace_id",
            "status",
        ),
    )


class B2BFulfillmentItem(Base, WorkspaceMixin):
    """Per-order-line reservation and shipment quantities."""

    __tablename__ = "b2b_order_fulfillment_items"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    fulfillment_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_order_fulfillments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("b2b_order_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inventory_snapshot_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("inventory_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    shipped_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    released_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    fulfillment: Mapped["B2BFulfillment"] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint(
            "fulfillment_id",
            "order_item_id",
            name="uq_b2b_fulfillment_items_order_line",
        ),
        CheckConstraint("quantity > 0", name="ck_b2b_fulfillment_item_quantity"),
        CheckConstraint(
            "reserved_quantity >= 0 AND shipped_quantity >= 0 "
            "AND released_quantity >= 0",
            name="ck_b2b_fulfillment_item_nonnegative",
        ),
        CheckConstraint(
            "shipped_quantity + released_quantity <= quantity",
            name="ck_b2b_fulfillment_item_balance",
        ),
        Index(
            "ix_b2b_fulfillment_items_workspace_product",
            "workspace_id",
            "product_id",
        ),
    )
