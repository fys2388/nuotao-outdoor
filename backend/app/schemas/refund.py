"""Refund schemas (M1 refund flow)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RefundCreateRequest(BaseModel):
    """Create a refund request."""

    order_id: UUID
    amount: Decimal = Field(..., gt=0, description="Refund amount, must be positive")
    reason: str = Field(..., min_length=1, max_length=500)
    category: str = Field(default="other", max_length=32)
    refund_type: str = Field(default="partial", pattern="^(full|partial)$")
    idempotency_key: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=1000)


class RefundApproveRequest(BaseModel):
    """Approve a refund. approved_by comes from auth context, not payload."""

    approved_amount: Decimal | None = Field(default=None, gt=0)
    approval_notes: str | None = Field(default=None, max_length=500)


class RefundRejectRequest(BaseModel):
    """Reject a refund."""

    reason: str = Field(..., min_length=1, max_length=500)


class RefundCancelRequest(BaseModel):
    """Cancel a refund."""

    reason: str | None = Field(default=None, max_length=500)


class RefundExecuteRequest(BaseModel):
    """Execute a refund via payment provider."""

    payment_provider: str | None = Field(default=None, pattern="^(stripe|paypal|woocommerce|manual)$")


class RefundOut(BaseModel):
    """Refund case output."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID | None
    customer_id: UUID | None
    product_id: UUID | None
    reason: str
    category: str
    refund_type: str
    requested_amount: Decimal
    amount: Decimal
    status: str
    resolution: str | None
    approved_amount: Decimal | None
    approved_by: str | None
    approved_at: datetime | None
    rejection_reason: str | None
    executed_amount: Decimal | None
    executed_at: datetime | None
    payment_provider: str
    payment_refund_id: str | None
    woocommerce_refund_id: str | None
    retry_count: int
    max_retries: int
    error_message: str | None
    last_failed_at: datetime | None
    idempotency_key: str
    notes: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime


class RefundSummaryOut(BaseModel):
    """Order refund summary."""

    order_id: UUID
    order_total: str
    refunded_amount: str
    total_refunded_via_cases: str
    active_refund_count: int
    refundable_balance: str
    currency: str
