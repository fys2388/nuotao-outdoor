"""Internal APIs for B2B agent agreements, targets, and rebates."""

from __future__ import annotations

from datetime import date  # noqa: TC003 - FastAPI resolves annotations
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.models.b2b import B2BAgent
from app.models.b2b_agreements import (
    B2BAgentAgreement,
    B2BRebateAccrual,
    B2BRebateTier,
)
from app.schemas.b2b_agreements import (
    B2BAgreementCreate,
    B2BAgreementDecision,
    B2BAgreementListResponse,
    B2BAgreementResponse,
    B2BAgreementUpdate,
    B2BRebateAccrualCreate,
    B2BRebateAccrualListResponse,
    B2BRebateAccrualResponse,
    B2BRebateAccrualSettle,
    B2BRebateProgressResponse,
    B2BRebateTierCreate,
    B2BRebateTierResponse,
    B2BRebateTierUpdate,
)
from app.schemas.user import UserResponse
from app.services import b2b_agreement_service

router = APIRouter(prefix="/admin/b2b", tags=["admin-b2b-agreements"])
WorkspaceId = UUID
AgreementEditor = Annotated[UserResponse, Depends(require_role("operator"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _agreement_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_agreement_service.B2BAgreementNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, b2b_agreement_service.B2BAgreementConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_agreement_service.B2BAgreementStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_agreement_service.B2BAgreementError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="B2B agreement operation failed")


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
    return {row.id: row for row in rows}


def _tier_response(tier: B2BRebateTier) -> B2BRebateTierResponse:
    return B2BRebateTierResponse(
        id=str(tier.id),
        agreement_id=str(tier.agreement_id),
        min_sales_amount=tier.min_sales_amount,
        max_sales_amount=tier.max_sales_amount,
        rebate_percent=tier.rebate_percent,
        created_at=tier.created_at,
        updated_at=tier.updated_at,
    )


def _agreement_response(
    agreement: B2BAgentAgreement,
    *,
    agent: B2BAgent | None = None,
) -> B2BAgreementResponse:
    return B2BAgreementResponse(
        id=str(agreement.id),
        agreement_number=agreement.agreement_number,
        agent_id=str(agreement.agent_id),
        agent_company=agent.company_name if agent else "",
        agent_number=agent.agent_number if agent else "",
        name=agreement.name,
        status=agreement.status,
        effective_status=b2b_agreement_service.effective_agreement_status(
            agreement
        ),
        currency=agreement.currency,
        effective_from=agreement.effective_from,
        effective_to=agreement.effective_to,
        target_amount=agreement.target_amount,
        qualification_basis=agreement.qualification_basis,  # type: ignore[arg-type]
        calculation_method=agreement.calculation_method,  # type: ignore[arg-type]
        notes=agreement.notes,
        created_by=agreement.created_by,
        submitted_by=agreement.submitted_by,
        submitted_at=agreement.submitted_at,
        approved_by=agreement.approved_by,
        approved_at=agreement.approved_at,
        rejection_reason=agreement.rejection_reason,
        terminated_by=agreement.terminated_by,
        terminated_at=agreement.terminated_at,
        termination_reason=agreement.termination_reason,
        tiers=[_tier_response(tier) for tier in agreement.tiers],
        accrual_count=len(agreement.accruals),
        created_at=agreement.created_at,
        updated_at=agreement.updated_at,
    )


def _accrual_response(
    accrual: B2BRebateAccrual,
    *,
    agent: B2BAgent | None = None,
) -> B2BRebateAccrualResponse:
    return B2BRebateAccrualResponse(
        id=str(accrual.id),
        accrual_number=accrual.accrual_number,
        agreement_id=str(accrual.agreement_id),
        agreement_number=(
            accrual.agreement.agreement_number if accrual.agreement else ""
        ),
        agent_id=str(accrual.agent_id),
        agent_company=agent.company_name if agent else "",
        status=accrual.status,
        period_start=accrual.period_start,
        period_end=accrual.period_end,
        qualification_basis=accrual.qualification_basis,  # type: ignore[arg-type]
        calculation_method=accrual.calculation_method,  # type: ignore[arg-type]
        qualifying_sales=accrual.qualifying_sales,
        rebate_percent=accrual.rebate_percent,
        rebate_amount=accrual.rebate_amount,
        currency=accrual.currency,
        evidence=accrual.evidence or {},
        created_by=accrual.created_by,
        submitted_by=accrual.submitted_by,
        submitted_at=accrual.submitted_at,
        approved_by=accrual.approved_by,
        approved_at=accrual.approved_at,
        rejected_by=accrual.rejected_by,
        rejected_at=accrual.rejected_at,
        rejection_reason=accrual.rejection_reason,
        settled_by=accrual.settled_by,
        settled_at=accrual.settled_at,
        settlement_reference=accrual.settlement_reference,
        created_at=accrual.created_at,
        updated_at=accrual.updated_at,
    )


@router.get("/agreements", response_model=B2BAgreementListResponse)
async def list_agreements(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    agent_id: str | None = None,
    search: str | None = Query(default=None, max_length=160),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementListResponse:
    agreements, total = await b2b_agreement_service.list_agreements(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
        agent_id=agent_id,
        search=search,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={row.agent_id for row in agreements},
    )
    return B2BAgreementListResponse(
        items=[
            _agreement_response(row, agent=agents.get(row.agent_id))
            for row in agreements
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/agreements", response_model=B2BAgreementResponse, status_code=201)
async def create_agreement(
    req: B2BAgreementCreate,
    user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    try:
        agreement = await b2b_agreement_service.create_agreement(
            db,
            workspace_id=workspace_id,
            agent_id=req.agent_id,
            name=req.name,
            currency=req.currency,
            effective_from=req.effective_from,
            effective_to=req.effective_to,
            target_amount=req.target_amount,
            qualification_basis=req.qualification_basis,
            calculation_method=req.calculation_method,
            created_by=_actor(user),
            notes=req.notes,
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={agreement.agent_id},
    )
    return _agreement_response(agreement, agent=agents.get(agreement.agent_id))


@router.get("/agreements/{agreement_id}", response_model=B2BAgreementResponse)
async def get_agreement(
    agreement_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    agreement = await b2b_agreement_service.get_agreement(
        db,
        workspace_id=workspace_id,
        agreement_id=agreement_id,
    )
    if agreement is None:
        raise HTTPException(status_code=404, detail="agreement not found")
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={agreement.agent_id},
    )
    return _agreement_response(agreement, agent=agents.get(agreement.agent_id))


@router.put("/agreements/{agreement_id}", response_model=B2BAgreementResponse)
async def update_agreement(
    agreement_id: str,
    req: B2BAgreementUpdate,
    user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    try:
        agreement = await b2b_agreement_service.update_agreement(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            actor=_actor(user),
            **req.model_dump(exclude_unset=True),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={agreement.agent_id},
    )
    return _agreement_response(agreement, agent=agents.get(agreement.agent_id))


@router.post(
    "/agreements/{agreement_id}/tiers",
    response_model=B2BRebateTierResponse,
    status_code=201,
)
async def create_rebate_tier(
    agreement_id: str,
    req: B2BRebateTierCreate,
    _user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateTierResponse:
    try:
        tier = await b2b_agreement_service.create_rebate_tier(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            min_sales_amount=req.min_sales_amount,
            max_sales_amount=req.max_sales_amount,
            rebate_percent=req.rebate_percent,
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _tier_response(tier)


@router.put(
    "/agreements/{agreement_id}/tiers/{tier_id}",
    response_model=B2BRebateTierResponse,
)
async def update_rebate_tier(
    agreement_id: str,
    tier_id: str,
    req: B2BRebateTierUpdate,
    _user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateTierResponse:
    changes = req.model_dump(exclude_unset=True)
    try:
        tier = await b2b_agreement_service.update_rebate_tier(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            tier_id=tier_id,
            min_sales_amount=changes.get("min_sales_amount"),
            max_sales_amount=changes.get("max_sales_amount"),
            max_sales_amount_set="max_sales_amount" in changes,
            rebate_percent=changes.get("rebate_percent"),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _tier_response(tier)


@router.delete(
    "/agreements/{agreement_id}/tiers/{tier_id}",
    status_code=204,
    response_class=Response,
)
async def delete_rebate_tier(
    agreement_id: str,
    tier_id: str,
    _user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await b2b_agreement_service.delete_rebate_tier(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            tier_id=tier_id,
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return Response(status_code=204)


@router.post(
    "/agreements/{agreement_id}/submit",
    response_model=B2BAgreementResponse,
)
async def submit_agreement(
    agreement_id: str,
    user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    try:
        agreement = await b2b_agreement_service.submit_agreement(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            actor=_actor(user),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _agreement_response(agreement)


@router.post(
    "/agreements/{agreement_id}/approve",
    response_model=B2BAgreementResponse,
)
async def approve_agreement(
    agreement_id: str,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    try:
        agreement = await b2b_agreement_service.approve_agreement(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            actor=_actor(user),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _agreement_response(agreement)


@router.post(
    "/agreements/{agreement_id}/reject",
    response_model=B2BAgreementResponse,
)
async def reject_agreement(
    agreement_id: str,
    req: B2BAgreementDecision,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    try:
        agreement = await b2b_agreement_service.reject_agreement(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            actor=_actor(user),
            reason=req.reason or "",
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _agreement_response(agreement)


@router.post(
    "/agreements/{agreement_id}/terminate",
    response_model=B2BAgreementResponse,
)
async def terminate_agreement(
    agreement_id: str,
    req: B2BAgreementDecision,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BAgreementResponse:
    try:
        agreement = await b2b_agreement_service.terminate_agreement(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            actor=_actor(user),
            reason=req.reason or "",
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _agreement_response(agreement)


@router.get(
    "/agreements/{agreement_id}/progress",
    response_model=B2BRebateProgressResponse,
)
async def get_agreement_progress(
    agreement_id: str,
    as_of: date | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateProgressResponse:
    try:
        progress = await b2b_agreement_service.agreement_progress(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            as_of=as_of,
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return B2BRebateProgressResponse(**progress)


@router.get(
    "/rebate-accruals",
    response_model=B2BRebateAccrualListResponse,
)
async def list_rebate_accruals(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    agreement_id: str | None = None,
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateAccrualListResponse:
    accruals, total = await b2b_agreement_service.list_rebate_accruals(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
        agreement_id=agreement_id,
        agent_id=agent_id,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={row.agent_id for row in accruals},
    )
    return B2BRebateAccrualListResponse(
        items=[
            _accrual_response(row, agent=agents.get(row.agent_id))
            for row in accruals
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/agreements/{agreement_id}/rebate-accruals",
    response_model=B2BRebateAccrualResponse,
    status_code=201,
)
async def calculate_rebate_accrual(
    agreement_id: str,
    req: B2BRebateAccrualCreate,
    user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateAccrualResponse:
    try:
        accrual = await b2b_agreement_service.calculate_rebate_accrual(
            db,
            workspace_id=workspace_id,
            agreement_id=agreement_id,
            period_start=req.period_start,
            period_end=req.period_end,
            actor=_actor(user),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={accrual.agent_id},
    )
    return _accrual_response(accrual, agent=agents.get(accrual.agent_id))


@router.post(
    "/rebate-accruals/{accrual_id}/submit",
    response_model=B2BRebateAccrualResponse,
)
async def submit_rebate_accrual(
    accrual_id: str,
    user: AgreementEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateAccrualResponse:
    try:
        accrual = await b2b_agreement_service.submit_rebate_accrual(
            db,
            workspace_id=workspace_id,
            accrual_id=accrual_id,
            actor=_actor(user),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _accrual_response(accrual)


@router.post(
    "/rebate-accruals/{accrual_id}/approve",
    response_model=B2BRebateAccrualResponse,
)
async def approve_rebate_accrual(
    accrual_id: str,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateAccrualResponse:
    try:
        accrual = await b2b_agreement_service.approve_rebate_accrual(
            db,
            workspace_id=workspace_id,
            accrual_id=accrual_id,
            actor=_actor(user),
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _accrual_response(accrual)


@router.post(
    "/rebate-accruals/{accrual_id}/reject",
    response_model=B2BRebateAccrualResponse,
)
async def reject_rebate_accrual(
    accrual_id: str,
    req: B2BAgreementDecision,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateAccrualResponse:
    try:
        accrual = await b2b_agreement_service.reject_rebate_accrual(
            db,
            workspace_id=workspace_id,
            accrual_id=accrual_id,
            actor=_actor(user),
            reason=req.reason or "",
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _accrual_response(accrual)


@router.post(
    "/rebate-accruals/{accrual_id}/settle",
    response_model=B2BRebateAccrualResponse,
)
async def settle_rebate_accrual(
    accrual_id: str,
    req: B2BRebateAccrualSettle,
    user: UserResponse = Depends(require_role("admin")),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRebateAccrualResponse:
    try:
        accrual = await b2b_agreement_service.settle_rebate_accrual(
            db,
            workspace_id=workspace_id,
            accrual_id=accrual_id,
            actor=_actor(user),
            settlement_reference=req.settlement_reference,
        )
    except (b2b_agreement_service.B2BAgreementError, ValueError) as exc:
        raise _agreement_http_error(exc) from exc
    return _accrual_response(accrual)
