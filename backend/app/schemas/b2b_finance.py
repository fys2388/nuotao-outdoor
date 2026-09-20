"""Schemas for B2B invoices, receipts, and accounts receivable."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, PlainSerializer

DecimalFloat = Annotated[
    Decimal,
    PlainSerializer(lambda value: float(value), return_type=float, when_used="json"),
]


class B2BInvoiceCreate(BaseModel):
    order_id: str
    issue_date: date | None = None
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class B2BInvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    order_id: str
    order_number: str = ""
    agent_id: str
    agent_company: str = ""
    customer_account_id: str | None = None
    status: str
    effective_status: str
    currency: str
    issue_date: date
    due_date: date
    subtotal: DecimalFloat
    discount_amount: DecimalFloat
    shipping_amount: DecimalFloat
    tax_amount: DecimalFloat
    total: DecimalFloat
    amount_paid: DecimalFloat
    amount_written_off: DecimalFloat
    balance_due: DecimalFloat
    items_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None = None
    created_by: str
    issued_at: datetime | None = None
    voided_at: datetime | None = None
    age_days: int = 0
    aging_bucket: str = "current"
    created_at: datetime
    updated_at: datetime


class B2BInvoiceListResponse(BaseModel):
    items: list[B2BInvoiceResponse]
    total: int
    page: int
    page_size: int


class B2BReceiptCreate(BaseModel):
    agent_id: str
    amount: DecimalFloat = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    idempotency_key: str = Field(min_length=1, max_length=128)
    received_at: datetime | None = None
    payment_method: str = Field(
        default="bank_transfer",
        min_length=1,
        max_length=32,
    )
    bank_reference: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=5000)


class B2BReceiptAllocationCreate(BaseModel):
    invoice_id: str
    amount: DecimalFloat = Field(gt=0)
    idempotency_key: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


class B2BReceiptAllocationResponse(BaseModel):
    id: str
    invoice_id: str
    invoice_number: str
    amount: DecimalFloat
    currency: str
    occurred_at: datetime
    description: str | None = None


class B2BReceiptResponse(BaseModel):
    id: str
    receipt_number: str
    agent_id: str
    agent_company: str = ""
    customer_account_id: str | None = None
    status: str
    amount: DecimalFloat
    unapplied_amount: DecimalFloat
    currency: str
    received_at: datetime
    payment_method: str
    bank_reference: str | None = None
    idempotency_key: str
    notes: str | None = None
    created_by: str
    allocations: list[B2BReceiptAllocationResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class B2BReceiptListResponse(BaseModel):
    items: list[B2BReceiptResponse]
    total: int
    page: int
    page_size: int


class B2BReceiptAllocationResult(BaseModel):
    receipt: B2BReceiptResponse
    invoice: B2BInvoiceResponse


class B2BWriteOffRequest(BaseModel):
    amount: DecimalFloat | None = Field(default=None, gt=0)
    idempotency_key: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=1000)


class B2BAgingBucketResponse(BaseModel):
    count: int
    amount: DecimalFloat


class B2BReceivableStatsResponse(BaseModel):
    as_of: date
    invoice_count: int
    open_invoice_count: int
    overdue_invoice_count: int
    outstanding_amount: DecimalFloat
    overdue_amount: DecimalFloat
    paid_amount: DecimalFloat
    written_off_amount: DecimalFloat
    aging: dict[str, B2BAgingBucketResponse]
