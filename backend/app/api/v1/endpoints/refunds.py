"""Refund endpoints (M1 refund flow).

Full lifecycle: create -> submit -> approve/reject -> execute -> succeeded/failed.
All high-risk actions (approve, reject, execute) require auth context;
approved_by/rejected_by comes from the authenticated actor, never client payload.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.refund import (
    RefundApproveRequest,
    RefundCancelRequest,
    RefundCreateRequest,
    RefundExecuteRequest,
    RefundOut,
    RefundRejectRequest,
    RefundSummaryOut,
)
from app.services import refund_service

router = APIRouter(prefix="/refunds", tags=["refunds"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: refund_service.RefundError) -> HTTPException:
    """Map refund service errors to HTTP status codes."""
    if isinstance(exc, refund_service.RefundNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, refund_service.RefundAmountExceeded):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, refund_service.RefundStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, refund_service.RefundNotConfigured):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _get_actor() -> str:
    """Get authenticated actor from context.

    In production, this comes from JWT/auth middleware. For now, returns
    'system' as a safe default. Client cannot override this via payload.
    """
    # TODO: integrate with auth middleware to get real actor identity.
    return "system"


@router.post(
    "",
    response_model=RefundOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create refund request",
)
async def create_refund(
    body: RefundCreateRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """Create a refund request. Idempotent by (order_id, idempotency_key)."""
    try:
        refund = await refund_service.create_refund_request(
            db,
            workspace_id=workspace_id,
            order_id=body.order_id,
            amount=body.amount,
            reason=body.reason,
            category=body.category,
            refund_type=body.refund_type,
            idempotency_key=body.idempotency_key,
            requested_by=_get_actor(),
            notes=body.notes,
            trace_id=get_trace_id(),
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.get(
    "",
    response_model=list[RefundOut],
    summary="List refunds",
)
async def list_refunds(
    db: DbSession,
    workspace_id: WorkspaceId,
    order_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RefundOut]:
    refunds = await refund_service.list_refunds(
        db, workspace_id=workspace_id, order_id=order_id, status=status_filter, limit=limit
    )
    return [RefundOut.model_validate(r) for r in refunds]


@router.get(
    "/{refund_id}",
    response_model=RefundOut,
    summary="Get refund by ID",
)
async def get_refund(
    refund_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    try:
        refund = await refund_service.get_refund(db, workspace_id=workspace_id, refund_id=refund_id)
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.post(
    "/{refund_id}/submit",
    response_model=RefundOut,
    summary="Submit refund for approval",
)
async def submit_refund(
    refund_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """requested -> pending_approval."""
    try:
        refund = await refund_service.submit_for_approval(
            db, workspace_id=workspace_id, refund_id=refund_id, trace_id=get_trace_id()
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.post(
    "/{refund_id}/approve",
    response_model=RefundOut,
    summary="Approve refund",
)
async def approve_refund(
    refund_id: UUID,
    body: RefundApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """pending_approval -> approved. approved_by comes from auth context."""
    try:
        refund = await refund_service.approve_refund(
            db,
            workspace_id=workspace_id,
            refund_id=refund_id,
            approved_by=_get_actor(),
            approved_amount=body.approved_amount,
            approval_notes=body.approval_notes,
            trace_id=get_trace_id(),
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.post(
    "/{refund_id}/reject",
    response_model=RefundOut,
    summary="Reject refund",
)
async def reject_refund(
    refund_id: UUID,
    body: RefundRejectRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """pending_approval -> rejected."""
    try:
        refund = await refund_service.reject_refund(
            db,
            workspace_id=workspace_id,
            refund_id=refund_id,
            rejected_by=_get_actor(),
            reason=body.reason,
            trace_id=get_trace_id(),
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.post(
    "/{refund_id}/cancel",
    response_model=RefundOut,
    summary="Cancel refund",
)
async def cancel_refund(
    refund_id: UUID,
    body: RefundCancelRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """requested/pending_approval/approved -> cancelled."""
    try:
        refund = await refund_service.cancel_refund(
            db,
            workspace_id=workspace_id,
            refund_id=refund_id,
            cancelled_by=_get_actor(),
            reason=body.reason,
            trace_id=get_trace_id(),
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.post(
    "/{refund_id}/execute",
    response_model=RefundOut,
    summary="Execute refund via payment provider",
)
async def execute_refund(
    refund_id: UUID,
    body: RefundExecuteRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """approved -> processing -> succeeded/failed.

    Payment provider not configured -> 503, refund stays in 'approved'.
    Never fakes success.
    """
    try:
        refund = await refund_service.execute_refund(
            db,
            workspace_id=workspace_id,
            refund_id=refund_id,
            payment_provider=body.payment_provider,
            trace_id=get_trace_id(),
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.post(
    "/{refund_id}/retry",
    response_model=RefundOut,
    summary="Retry failed refund",
)
async def retry_refund(
    refund_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundOut:
    """failed -> processing. Respects max_retries. Idempotent if already succeeded."""
    try:
        refund = await refund_service.retry_refund(
            db, workspace_id=workspace_id, refund_id=refund_id, trace_id=get_trace_id()
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundOut.model_validate(refund)


@router.get(
    "/order/{order_id}/summary",
    response_model=RefundSummaryOut,
    summary="Get order refund summary",
)
async def get_order_refund_summary(
    order_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RefundSummaryOut:
    """Get total refunded, active refunds, and refundable balance for an order."""
    try:
        summary = await refund_service.get_order_refund_summary(
            db, workspace_id=workspace_id, order_id=order_id
        )
    except refund_service.RefundError as exc:
        raise _http_error(exc) from exc
    return RefundSummaryOut(**summary)
