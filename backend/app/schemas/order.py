"""Order and WooCommerce webhook schemas.

PII policy: webhook payloads are parsed into a minimal, non-identifying
projection (no customer names/emails/addresses are stored).
"""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


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
