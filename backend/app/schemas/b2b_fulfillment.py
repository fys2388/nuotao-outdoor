"""Schemas for B2B order fulfillment across WMS and TMS."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class B2BFulfillmentReserveRequest(BaseModel):
    """Reserve every order line from one warehouse."""

    warehouse_location: Literal["cn", "us", "eu"]
    reservation_key: str | None = Field(default=None, max_length=128)


class B2BFulfillmentShipRequest(BaseModel):
    """Consume reserved stock and create the outbound TMS shipment."""

    carrier: str = Field(min_length=1, max_length=64)
    tracking_number: str = Field(min_length=1, max_length=128)
    origin: str | None = Field(default=None, max_length=128)
    destination: str | None = Field(default=None, max_length=128)
    ship_date: datetime | None = None
    shipment_key: str | None = Field(default=None, max_length=128)


class B2BFulfillmentReleaseRequest(BaseModel):
    """Release unshipped reserved stock."""

    reason: str = Field(min_length=1, max_length=1000)


class B2BFulfillmentDeliverRequest(BaseModel):
    """Record proof of delivery for the linked shipment."""

    occurred_at: datetime | None = None


class B2BFulfillmentItemResponse(BaseModel):
    id: str
    order_item_id: str
    product_id: str
    inventory_snapshot_id: str
    quantity: int
    reserved_quantity: int
    shipped_quantity: int
    released_quantity: int


class B2BFulfillmentResponse(BaseModel):
    id: str
    fulfillment_number: str
    order_id: str
    status: str
    warehouse_location: str
    shipment_id: str | None = None
    reserved_at: datetime
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    released_at: datetime | None = None
    release_reason: str | None = None
    created_by: str
    items: list[B2BFulfillmentItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class B2BFulfillmentLookupResponse(BaseModel):
    """Nullable wrapper so a missing fulfillment is not an error."""

    fulfillment: B2BFulfillmentResponse | None = None


class B2BFulfillmentShipmentResponse(BaseModel):
    id: UUID
    carrier: str
    origin: str | None
    destination: str | None
    tracking_number: str | None
    status: str
    ship_date: datetime | None
    delivery_time_days: int | None
