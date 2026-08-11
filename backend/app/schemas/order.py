"""Order and WooCommerce webhook schemas.

PII policy: webhook payloads are parsed into a minimal, non-identifying
projection (no customer names/emails/addresses are stored).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebhookLineItem(BaseModel):
    """Minimal line item projection from a WooCommerce order payload."""

    id: int | None = None
    product_id: int | None = None
    name: str = ""
    sku: str | None = None
    quantity: int = Field(default=1, ge=0)
    total: Decimal = Decimal("0")


class WebhookOrderPayload(BaseModel):
    """Minimal WooCommerce order payload used for ORDER_CREATED handling.

    Only the fields needed for the commercial loop are extracted; anything
    else in the raw payload (including PII blocks) is ignored and discarded.
    """

    id: int
    status: str = ""
    currency: str = "USD"
    payment_method: str | None = None
    payment_method_title: str | None = None
    total: Decimal = Decimal("0")
    subtotal: Decimal = Decimal("0")
    shipping_total: Decimal = Decimal("0")
    discount_total: Decimal = Decimal("0")
    tax_total: Decimal = Decimal("0")
    shipping: dict[str, Any] = Field(default_factory=dict)
    line_items: list[WebhookLineItem] = Field(default_factory=list)

    @property
    def country(self) -> str | None:
        """Extract a non-PII country code from the shipping block if present."""
        value = self.shipping.get("country")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @property
    def payment_status(self) -> str | None:
        """Derive a normalized payment status from the order status.

        WooCommerce ``status`` values such as ``processing``/``completed``
        mean the payment cleared; ``pending``/``on-hold``/``failed``/``refunded``
        mean it did not. ``payment_method_title`` is preferred when set because
        gateway plugins often leave ``status`` untouched.
        """
        status = self.status.lower()
        if status in {"processing", "completed"}:
            return status
        if status in {"pending", "on-hold", "failed", "refunded", "cancelled"}:
            return status
        return None


class WebhookResponse(BaseModel):
    """Webhook endpoint response: full audit trail of the ingestion.

    ``profit`` carries the contribution margin snapshot, ``rules`` the per-domain
    rule check outcomes, and ``events`` the event log entries created for the
    order. For a duplicate delivery only ``status``/``order_id`` are populated.
    """

    status: Literal["created", "duplicate"]
    order_id: str
    external_order_id: str
    trace_id: str
    profit: dict[str, Any] = Field(default_factory=dict)
    rules: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)


class OrderItemOut(BaseModel):
    """Order line item as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    order_id: UUID
    external_item_id: str | None
    product_id: UUID | None
    sku: str | None
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderOut(BaseModel):
    """Order summary as returned by the list API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    external_order_id: str
    status: str
    payment_status: str | None
    fulfillment_status: str | None
    currency: str
    country: str | None
    payment_method: str | None
    source: str
    total: Decimal
    profit_snapshot: dict[str, Any]
    rule_results: dict[str, Any]
    trace_id: str | None
    received_at: datetime
    created_at: datetime


class OrderDetailOut(OrderOut):
    """Order detail including line items."""

    items: list[OrderItemOut] = Field(default_factory=list)


class OrderListOut(BaseModel):
    """Paginated order list."""

    items: list[OrderOut]
    total: int
    limit: int
    offset: int
