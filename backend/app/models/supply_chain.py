"""Supply chain intelligence models (M4.1): suppliers, POs, inventory, logistics, knowledge.

Foundation for the future Supply Chain Agent. **No Supply Chain Agent, no
automatic purchasing.** Purchase orders follow an explicit lifecycle
(draft -> approved -> ordered -> partial_received -> received, cancellable
from draft/approved); inventory supports CN/US/EU warehouse locations
(``cn`` China, ``us`` United States, ``eu`` Europe); every write must emit
an event.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AI_JSON, Base, CreatedAtMixin, TimestampMixin, WorkspaceMixin

# Supply chain knowledge entry types (Phase 1 + M4.2 learning loop).
SUPPLY_CHAIN_ENTRY_TYPES: tuple[str, ...] = (
    "supplier_pattern",
    "logistics_pattern",
    "delay_pattern",
    "quality_pattern",
    "risk_pattern",
    "supplier_success_pattern",
    "supplier_failure_pattern",
    "logistics_success_pattern",
    "logistics_failure_pattern",
    "season_pattern",
    "country_pattern",
)

# Purchase order lifecycle states (M4.1).
# ordered -> partial_received -> received for split deliveries.
PO_STATUSES: tuple[str, ...] = (
    "draft",
    "approved",
    "ordered",
    "partial_received",
    "received",
    "cancelled",
)

# Warehouse locations (M4.1): cn China, us United States, eu Europe.
WAREHOUSE_LOCATIONS: tuple[str, ...] = ("cn", "us", "eu")

# Shipment lifecycle states (M4.1).
SHIPMENT_STATUSES: tuple[str, ...] = ("created", "in_transit", "delivered", "failed", "delayed")


class SupplierProfile(Base, TimestampMixin, WorkspaceMixin):
    """Supplier intelligence profile (M4.1).

    Extends the master ``suppliers`` table with quality/performance/risk data.
    One profile per supplier per workspace.
    """

    __tablename__ = "supplier_profiles"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    factory_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_order_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    on_time_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    defect_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    certifications: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "supplier_id",
            name="uq_supplier_profiles_workspace_supplier",
        ),
        Index("ix_supplier_profiles_workspace_risk", "workspace_id", "risk_level"),
    )


class PurchaseOrder(Base, TimestampMixin, WorkspaceMixin):
    """Purchase order with explicit lifecycle (M4.1).

    States: ``draft -> approved -> ordered -> partial_received -> received``;
    cancellable from draft/approved. Monetary fields use Numeric/Decimal.
    """

    __tablename__ = "purchase_orders"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    po_number: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    expected_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "po_number", name="uq_purchase_orders_workspace_po"),
        Index("ix_purchase_orders_workspace_status", "workspace_id", "status"),
    )


class PurchaseOrderItem(Base, WorkspaceMixin):
    """Line item of a purchase order."""

    __tablename__ = "purchase_order_items"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    purchase_order_id: Mapped[Uuid] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)


class InventorySnapshot(Base, TimestampMixin, WorkspaceMixin):
    """Current inventory state per product/location (M4.1).

    ``available`` is quantity minus reserved unless explicitly provided. One
    row per (workspace, product, location) - create returns 409 on duplicates,
    use update to adjust stock. Locations cover CN and overseas warehouses.
    """

    __tablename__ = "inventory_snapshots"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location: Mapped[str] = mapped_column(String(32), nullable=False, default="cn")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_transit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "product_id",
            "location",
            name="uq_inventory_workspace_product_location",
        ),
        CheckConstraint("location IN ('cn', 'us', 'eu')", name="ck_inventory_location"),
        Index("ix_inventory_workspace_location", "workspace_id", "location"),
    )


class ShipmentRecord(Base, TimestampMixin, WorkspaceMixin):
    """One shipment with carrier/tracking and delivery outcome (M4.1)."""

    __tablename__ = "shipment_records"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    purchase_order_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    carrier: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="created")
    ship_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_shipments_workspace_status", "workspace_id", "status"),
        Index("ix_shipments_workspace_carrier", "workspace_id", "carrier"),
    )


class LogisticsEvent(Base, CreatedAtMixin, WorkspaceMixin):
    """Append-only tracking event for a shipment (M4.1)."""

    __tablename__ = "logistics_events"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    shipment_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("shipment_records.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_logistics_events_workspace_shipment", "workspace_id", "shipment_id"),
    )


class SupplyChainKnowledgeEntry(Base, TimestampMixin, WorkspaceMixin):
    """Supply chain knowledge memory (M4.1).

    Entry types: ``supplier_pattern`` / ``logistics_pattern`` / ``delay_pattern`` /
    ``quality_pattern`` / ``risk_pattern``. Queryable by category, supplier or
    product for the future Supply Chain Agent.
    """

    __tablename__ = "supply_chain_knowledge_entries"

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True, default=lambda: uuid4())
    supplier_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[Uuid | None] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    tags: Mapped[list[Any]] = mapped_column(AI_JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ix_supply_chain_knowledge_workspace_cat",
            "workspace_id",
            "category",
        ),
        Index(
            "ix_supply_chain_knowledge_workspace_supplier",
            "workspace_id",
            "supplier_id",
        ),
    )
