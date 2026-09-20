"""Internal APIs for B2B invoices, receipts, and accounts receivable."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_finance import B2BInvoice, B2BReceipt
from app.schemas.b2b_finance import (
    B2BInvoiceCreate,
    B2BInvoiceListResponse,
    B2BInvoiceResponse,
    B2BReceiptAllocationCreate,
    B2BReceiptAllocationResponse,
    B2BReceiptAllocationResult,
    B2BReceiptCreate,
    B2BReceiptListResponse,
    B2BReceiptResponse,
    B2BReceivableStatsResponse,
    B2BWriteOffRequest,
)
from app.schemas.user import UserResponse
from app.services import b2b_finance_service

router = APIRouter(prefix="/admin/b2b", tags=["admin-b2b-finance"])
WorkspaceId = UUID


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _finance_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_finance_service.B2BFinanceNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, b2b_finance_service.B2BFinanceConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_finance_service.B2BFinanceStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_finance_service.B2BFinanceError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="B2B finance operation failed")


async def _agent_map(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_ids: set[UUID],
) -> dict[UUID, B2BAgent]:
    if not agent_ids:
        return {}
    rows = (
        await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id.in_(agent_ids),
            )
        )
    ).scalars().all()
    return {agent.id: agent for agent in rows}


async def _order_map(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    order_ids: set[UUID],
) -> dict[UUID, B2BOrder]:
    if not order_ids:
        return {}
    rows = (
        await db.execute(
            select(B2BOrder).where(
                B2BOrder.workspace_id == workspace_id,
                B2BOrder.id.in_(order_ids),
            )
        )
    ).scalars().all()
    return {order.id: order for order in rows}


async def _invoice_number_map(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    invoice_ids: set[UUID],
) -> dict[UUID, str]:
    if not invoice_ids:
        return {}
    rows = (
        await db.execute(
            select(B2BInvoice.id, B2BInvoice.invoice_number).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id.in_(invoice_ids),
            )
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def _invoice_response(
    invoice: B2BInvoice,
    *,
    order: B2BOrder | None = None,
    agent: B2BAgent | None = None,
) -> B2BInvoiceResponse:
    return B2BInvoiceResponse(
        id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        order_id=str(invoice.order_id),
        order_number=order.order_number if order else "",
        agent_id=str(invoice.agent_id),
        agent_company=agent.company_name if agent else "",
        customer_account_id=(
            str(invoice.customer_account_id) if invoice.customer_account_id else None
        ),
        status=invoice.status,
        effective_status=b2b_finance_service.effective_invoice_status(invoice),
        currency=invoice.currency,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        discount_amount=invoice.discount_amount,
        shipping_amount=invoice.shipping_amount,
        tax_amount=invoice.tax_amount,
        total=invoice.total,
        amount_paid=invoice.amount_paid,
        amount_written_off=invoice.amount_written_off,
        balance_due=invoice.balance_due,
        items_snapshot=invoice.items_snapshot or [],
        notes=invoice.notes,
        created_by=invoice.created_by,
        issued_at=invoice.issued_at,
        voided_at=invoice.voided_at,
        age_days=b2b_finance_service.receivable_age_days(invoice),
        aging_bucket=b2b_finance_service.receivable_aging_bucket(invoice),
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


def _receipt_response(
    receipt: B2BReceipt,
    *,
    agent: B2BAgent | None = None,
    invoice_numbers: dict[UUID, str] | None = None,
) -> B2BReceiptResponse:
    numbers = invoice_numbers or {}
    allocations = [
        B2BReceiptAllocationResponse(
            id=str(entry.id),
            invoice_id=str(entry.invoice_id),
            invoice_number=numbers.get(entry.invoice_id, ""),
            amount=abs(entry.amount),
            currency=entry.currency,
            occurred_at=entry.occurred_at,
            description=entry.description,
        )
        for entry in receipt.entries
        if entry.entry_type == "payment"
    ]
    return B2BReceiptResponse(
        id=str(receipt.id),
        receipt_number=receipt.receipt_number,
        agent_id=str(receipt.agent_id),
        agent_company=agent.company_name if agent else "",
        customer_account_id=(
            str(receipt.customer_account_id) if receipt.customer_account_id else None
        ),
        status=receipt.status,
        amount=receipt.amount,
        unapplied_amount=receipt.unapplied_amount,
        currency=receipt.currency,
        received_at=receipt.received_at,
        payment_method=receipt.payment_method,
        bank_reference=receipt.bank_reference,
        idempotency_key=receipt.idempotency_key,
        notes=receipt.notes,
        created_by=receipt.created_by,
        allocations=allocations,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
    )


@router.get("/invoices", response_model=B2BInvoiceListResponse)
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInvoiceListResponse:
    invoices, total = await b2b_finance_service.list_invoices(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
        agent_id=agent_id,
    )
    orders = await _order_map(
        db,
        workspace_id=workspace_id,
        order_ids={invoice.order_id for invoice in invoices},
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={invoice.agent_id for invoice in invoices},
    )
    return B2BInvoiceListResponse(
        items=[
            _invoice_response(
                invoice,
                order=orders.get(invoice.order_id),
                agent=agents.get(invoice.agent_id),
            )
            for invoice in invoices
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/invoices", response_model=B2BInvoiceResponse, status_code=201)
async def create_invoice(
    req: B2BInvoiceCreate,
    user: UserResponse = Depends(require_role("operator")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInvoiceResponse:
    try:
        invoice = await b2b_finance_service.create_invoice_from_order(
            db,
            workspace_id=workspace_id,
            order_id=req.order_id,
            created_by=_actor(user),
            issue_date=req.issue_date,
            due_date=req.due_date,
            notes=req.notes,
        )
    except (b2b_finance_service.B2BFinanceError, ValueError) as exc:
        raise _finance_http_error(exc) from exc
    orders = await _order_map(
        db,
        workspace_id=workspace_id,
        order_ids={invoice.order_id},
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={invoice.agent_id},
    )
    return _invoice_response(
        invoice,
        order=orders.get(invoice.order_id),
        agent=agents.get(invoice.agent_id),
    )


@router.get("/invoices/{invoice_id}", response_model=B2BInvoiceResponse)
async def get_invoice(
    invoice_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInvoiceResponse:
    invoice = await b2b_finance_service.get_invoice(
        db,
        workspace_id=workspace_id,
        invoice_id=invoice_id,
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    orders = await _order_map(
        db,
        workspace_id=workspace_id,
        order_ids={invoice.order_id},
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={invoice.agent_id},
    )
    return _invoice_response(
        invoice,
        order=orders.get(invoice.order_id),
        agent=agents.get(invoice.agent_id),
    )


@router.post("/invoices/{invoice_id}/issue", response_model=B2BInvoiceResponse)
async def issue_invoice(
    invoice_id: str,
    user: UserResponse = Depends(require_role("operator")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInvoiceResponse:
    try:
        invoice = await b2b_finance_service.issue_invoice(
            db,
            workspace_id=workspace_id,
            invoice_id=invoice_id,
            actor=_actor(user),
            trace_id=get_trace_id(),
        )
    except (b2b_finance_service.B2BFinanceError, ValueError) as exc:
        raise _finance_http_error(exc) from exc
    orders = await _order_map(
        db,
        workspace_id=workspace_id,
        order_ids={invoice.order_id},
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={invoice.agent_id},
    )
    return _invoice_response(
        invoice,
        order=orders.get(invoice.order_id),
        agent=agents.get(invoice.agent_id),
    )


@router.post(
    "/invoices/{invoice_id}/write-off",
    response_model=B2BInvoiceResponse,
)
async def write_off_invoice(
    invoice_id: str,
    req: B2BWriteOffRequest,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInvoiceResponse:
    try:
        invoice, _receipt = await b2b_finance_service.write_off_invoice(
            db,
            workspace_id=workspace_id,
            invoice_id=invoice_id,
            actor=_actor(user),
            amount=Decimal(str(req.amount)) if req.amount is not None else None,
            idempotency_key=req.idempotency_key,
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except (b2b_finance_service.B2BFinanceError, ValueError) as exc:
        raise _finance_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={invoice.agent_id},
    )
    return _invoice_response(invoice, agent=agents.get(invoice.agent_id))


@router.get("/receipts", response_model=B2BReceiptListResponse)
async def list_receipts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BReceiptListResponse:
    receipts, total = await b2b_finance_service.list_receipts(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
        agent_id=agent_id,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={receipt.agent_id for receipt in receipts},
    )
    invoice_ids = {
        entry.invoice_id
        for receipt in receipts
        for entry in receipt.entries
        if entry.entry_type == "payment"
    }
    invoice_numbers = await _invoice_number_map(
        db,
        workspace_id=workspace_id,
        invoice_ids=invoice_ids,
    )
    return B2BReceiptListResponse(
        items=[
            _receipt_response(
                receipt,
                agent=agents.get(receipt.agent_id),
                invoice_numbers=invoice_numbers,
            )
            for receipt in receipts
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/receipts", response_model=B2BReceiptResponse, status_code=201)
async def create_receipt(
    req: B2BReceiptCreate,
    user: UserResponse = Depends(require_role("operator")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BReceiptResponse:
    try:
        receipt = await b2b_finance_service.create_receipt(
            db,
            workspace_id=workspace_id,
            agent_id=req.agent_id,
            amount=Decimal(str(req.amount)),
            currency=req.currency,
            idempotency_key=req.idempotency_key,
            created_by=_actor(user),
            received_at=req.received_at,
            payment_method=req.payment_method,
            bank_reference=req.bank_reference,
            notes=req.notes,
            trace_id=get_trace_id(),
        )
    except (b2b_finance_service.B2BFinanceError, ValueError) as exc:
        raise _finance_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={receipt.agent_id},
    )
    return _receipt_response(receipt, agent=agents.get(receipt.agent_id))


@router.post(
    "/receipts/{receipt_id}/allocate",
    response_model=B2BReceiptAllocationResult,
)
async def allocate_receipt(
    receipt_id: str,
    req: B2BReceiptAllocationCreate,
    user: UserResponse = Depends(require_role("operator")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BReceiptAllocationResult:
    try:
        receipt, invoice = await b2b_finance_service.allocate_receipt(
            db,
            workspace_id=workspace_id,
            receipt_id=receipt_id,
            invoice_id=req.invoice_id,
            amount=Decimal(str(req.amount)),
            actor=_actor(user),
            idempotency_key=req.idempotency_key,
            notes=req.notes,
            trace_id=get_trace_id(),
        )
    except (b2b_finance_service.B2BFinanceError, ValueError) as exc:
        raise _finance_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={receipt.agent_id, invoice.agent_id},
    )
    orders = await _order_map(
        db,
        workspace_id=workspace_id,
        order_ids={invoice.order_id},
    )
    invoice_numbers = {invoice.id: invoice.invoice_number}
    return B2BReceiptAllocationResult(
        receipt=_receipt_response(
            receipt,
            agent=agents.get(receipt.agent_id),
            invoice_numbers=invoice_numbers,
        ),
        invoice=_invoice_response(
            invoice,
            order=orders.get(invoice.order_id),
            agent=agents.get(invoice.agent_id),
        ),
    )


@router.get("/receivables", response_model=B2BInvoiceListResponse)
async def list_receivables(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    agent_id: str | None = None,
    overdue_only: bool = False,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInvoiceListResponse:
    invoices, total = await b2b_finance_service.list_receivables(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        agent_id=agent_id,
        overdue_only=overdue_only,
    )
    orders = await _order_map(
        db,
        workspace_id=workspace_id,
        order_ids={invoice.order_id for invoice in invoices},
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={invoice.agent_id for invoice in invoices},
    )
    return B2BInvoiceListResponse(
        items=[
            _invoice_response(
                invoice,
                order=orders.get(invoice.order_id),
                agent=agents.get(invoice.agent_id),
            )
            for invoice in invoices
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/receivables/stats", response_model=B2BReceivableStatsResponse)
async def receivable_stats(
    as_of: date | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BReceivableStatsResponse:
    return B2BReceivableStatsResponse(
        **await b2b_finance_service.receivable_stats(
            db,
            workspace_id=workspace_id,
            as_of=as_of,
        )
    )
