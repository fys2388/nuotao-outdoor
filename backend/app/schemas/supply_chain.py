"""Supply chain intelligence schemas (M4.1)."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SUPPLY_CHAIN_ENTRY_TYPES = (
    "supplier_pattern",
    "logistics_pattern",
    "delay_pattern",
    "quality_pattern",
    "risk_pattern",
)

# Supplier factory types (M4.1): factory / trading company / agent.
FACTORY_TYPES = ("factory", "trading", "agent")

# Warehouse locations (M4.1): cn China, us United States, eu Europe.
WAREHOUSE_LOCATIONS = ("cn", "us", "eu")


class SupplierProfileCreate(BaseModel):
    """Create a supplier intelligence profile (one per supplier)."""

    supplier_id: UUID
    category: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=128)
    factory_type: Literal["factory", "trading", "agent"] | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    minimum_order_qty: int | None = Field(default=None, ge=0)
    quality_score: Decimal | None = Field(default=None, ge=0, le=100)
    on_time_rate: Decimal | None = Field(default=None, ge=0, le=100)
    defect_rate: Decimal | None = Field(default=None, ge=0, le=100)
    certifications: list[str] = Field(default_factory=list, max_length=30)
    risk_level: Literal["low", "medium", "high"] = "low"


class SupplierProfileUpdate(BaseModel):
    """Partial supplier profile update."""

    category: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=128)
    factory_type: Literal["factory", "trading", "agent"] | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    minimum_order_qty: int | None = Field(default=None, ge=0)
    quality_score: Decimal | None = Field(default=None, ge=0, le=100)
    on_time_rate: Decimal | None = Field(default=None, ge=0, le=100)
    defect_rate: Decimal | None = Field(default=None, ge=0, le=100)
    certifications: list[str] | None = None
    risk_level: Literal["low", "medium", "high"] | None = None


class SupplierProfileOut(BaseModel):
    """A supplier profile as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID | None
    category: str | None
    location: str | None
    factory_type: str | None
    lead_time_days: int | None
    minimum_order_qty: int | None
    quality_score: Decimal | None
    on_time_rate: Decimal | None
    defect_rate: Decimal | None
    certifications: list[Any]
    risk_level: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderItemCreate(BaseModel):
    """A purchase order line item."""

    product_id: UUID | None = None
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(default=1, ge=1)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)


class PurchaseOrderItemOut(BaseModel):
    """A purchase order line item as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    purchase_order_id: UUID
    product_id: UUID | None
    sku: str
    name: str
    quantity: int
    unit_cost: Decimal
    line_total: Decimal


class PurchaseOrderCreate(BaseModel):
    """Create a purchase order in draft state with line items."""

    po_number: str = Field(min_length=1, max_length=64)
    supplier_id: UUID | None = None
    currency: str = Field(default="USD", max_length=8)
    shipping_cost: Decimal = Field(default=Decimal("0"), ge=0)
    expected_delivery_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=1000)
    items: list[PurchaseOrderItemCreate] = Field(default_factory=list, max_length=100)


class PurchaseOrderUpdate(BaseModel):
    """Partial purchase order update (draft only)."""

    notes: str | None = Field(default=None, max_length=1000)
    shipping_cost: Decimal | None = Field(default=None, ge=0)
    expected_delivery_at: datetime | None = None


class PurchaseOrderOut(BaseModel):
    """A purchase order as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    po_number: str
    supplier_id: UUID | None
    status: str
    currency: str
    subtotal: Decimal
    shipping_cost: Decimal
    total: Decimal
    expected_delivery_at: datetime | None
    received_at: datetime | None
    notes: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderDetailOut(PurchaseOrderOut):
    """Purchase order with line items."""

    items: list[PurchaseOrderItemOut] = Field(default_factory=list)


class InventoryCreate(BaseModel):
    """Create an inventory snapshot (available defaults to quantity-reserved)."""

    product_id: UUID | None = None
    location: Literal["cn", "us", "eu"] = "cn"
    quantity: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    available: int | None = Field(default=None, ge=0)
    in_transit: int = Field(default=0, ge=0)
    snapshot_time: datetime | None = None


class InventoryUpdate(BaseModel):
    """Partial inventory update (available is recomputed when omitted)."""

    quantity: int | None = Field(default=None, ge=0)
    reserved: int | None = Field(default=None, ge=0)
    available: int | None = Field(default=None, ge=0)
    in_transit: int | None = Field(default=None, ge=0)


class InventoryOut(BaseModel):
    """An inventory snapshot as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    product_id: UUID | None
    location: str
    quantity: int
    reserved: int
    available: int
    in_transit: int
    snapshot_time: datetime
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class ShipmentCreate(BaseModel):
    """Create a shipment record."""

    purchase_order_id: UUID | None = None
    carrier: str = Field(min_length=1, max_length=64)
    origin: str | None = Field(default=None, max_length=128)
    destination: str | None = Field(default=None, max_length=128)
    tracking_number: str | None = Field(default=None, max_length=128)
    status: Literal["created", "in_transit", "delivered", "failed", "delayed"] = "created"
    ship_date: datetime | None = None
    delivery_time_days: int | None = Field(default=None, ge=0)
    delay_reason: str | None = Field(default=None, max_length=500)


class ShipmentUpdate(BaseModel):
    """Partial shipment update."""

    status: Literal["created", "in_transit", "delivered", "failed", "delayed"] | None = None
    tracking_number: str | None = Field(default=None, max_length=128)
    delivery_time_days: int | None = Field(default=None, ge=0)
    delay_reason: str | None = Field(default=None, max_length=500)


class ShipmentOut(BaseModel):
    """A shipment record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    purchase_order_id: UUID | None
    carrier: str
    origin: str | None
    destination: str | None
    tracking_number: str | None
    status: str
    ship_date: datetime | None
    delivery_time_days: int | None
    delay_reason: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class LogisticsEventCreate(BaseModel):
    """Add an append-only tracking event to a shipment."""

    event_type: str = Field(min_length=1, max_length=32)
    location: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    occurred_at: datetime | None = None


class LogisticsEventOut(BaseModel):
    """A logistics event as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    shipment_id: UUID | None
    event_type: str
    location: str | None
    description: str | None
    occurred_at: datetime | None
    trace_id: str | None
    created_at: datetime


class SupplyChainKnowledgeCreate(BaseModel):
    """Create a supply chain knowledge memory entry."""

    supplier_id: UUID | None = None
    product_id: UUID | None = None
    category: str | None = Field(default=None, max_length=64)
    entry_type: Literal[
        "supplier_pattern",
        "logistics_pattern",
        "delay_pattern",
        "quality_pattern",
        "risk_pattern",
    ]
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: str = Field(default="manual", max_length=32)
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class SupplyChainKnowledgeOut(BaseModel):
    """A supply chain knowledge entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    supplier_id: UUID | None
    product_id: UUID | None
    category: str | None
    entry_type: str
    title: str
    content: str
    tags: list[Any]
    source: str
    confidence: Decimal
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
