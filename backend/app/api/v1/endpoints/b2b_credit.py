"""Internal APIs for B2B credit risk, holds, and credit insurance."""

from __future__ import annotations

from typing import Annotated
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
from app.models.b2b import B2BAgent
from app.models.b2b_credit import (
    B2BCreditInsuranceClaim,
    B2BCreditInsurancePolicy,
    B2BCreditPolicy,
    B2BCreditRiskAssessment,
    B2BCreditStatusEvent,
)
from app.models.b2b_finance import B2BInvoice
from app.schemas.b2b_credit import (
    B2BCreditAgentRiskResponse,
    B2BCreditPolicyCreate,
    B2BCreditPolicyDecision,
    B2BCreditPolicyListResponse,
    B2BCreditPolicyResponse,
    B2BCreditRiskOverviewResponse,
    B2BCreditStatusEventResponse,
    B2BCreditStatusUpdate,
    B2BInsuranceClaimCreate,
    B2BInsuranceClaimDecision,
    B2BInsuranceClaimListResponse,
    B2BInsuranceClaimResponse,
    B2BInsuranceClaimSettle,
    B2BInsurancePolicyCreate,
    B2BInsurancePolicyListResponse,
    B2BInsurancePolicyResponse,
    B2BInsurancePolicyUpdate,
    B2BRiskAssessmentResponse,
)
from app.schemas.user import UserResponse
from app.services import b2b_credit_service

router = APIRouter(prefix="/admin/b2b/credit", tags=["admin-b2b-credit"])
WorkspaceId = UUID
CreditEditor = Annotated[UserResponse, Depends(require_role("operator"))]
CreditAdmin = Annotated[UserResponse, Depends(require_role("admin"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_credit_service.B2BCreditNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, b2b_credit_service.B2BCreditConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_credit_service.B2BCreditStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_credit_service.B2BCreditError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="B2B credit operation failed")


def _policy_response(policy: B2BCreditPolicy) -> B2BCreditPolicyResponse:
    return B2BCreditPolicyResponse(
        id=str(policy.id),
        version_number=policy.version_number,
        status=policy.status,
        watch_score=policy.watch_score,
        hold_score=policy.hold_score,
        freeze_score=policy.freeze_score,
        max_utilization_percent=policy.max_utilization_percent,
        max_overdue_days=policy.max_overdue_days,
        auto_hold_enabled=policy.auto_hold_enabled,
        auto_freeze_enabled=policy.auto_freeze_enabled,
        insurance_required_above=policy.insurance_required_above,
        notes=policy.notes,
        created_by=policy.created_by,
        submitted_by=policy.submitted_by,
        submitted_at=policy.submitted_at,
        approved_by=policy.approved_by,
        approved_at=policy.approved_at,
        rejected_by=policy.rejected_by,
        rejected_at=policy.rejected_at,
        rejection_reason=policy.rejection_reason,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _assessment_response(
    assessment: B2BCreditRiskAssessment,
) -> B2BRiskAssessmentResponse:
    return B2BRiskAssessmentResponse(
        id=str(assessment.id),
        agent_id=str(assessment.agent_id),
        policy_id=str(assessment.policy_id),
        score=assessment.score,
        risk_level=assessment.risk_level,
        recommended_action=assessment.recommended_action,  # type: ignore[arg-type]
        applied_action=assessment.applied_action,  # type: ignore[arg-type]
        credit_status_before=assessment.credit_status_before,  # type: ignore[arg-type]
        credit_status_after=assessment.credit_status_after,  # type: ignore[arg-type]
        exposure_amount=assessment.exposure_amount,
        overdue_amount=assessment.overdue_amount,
        utilization_percent=assessment.utilization_percent,
        overdue_ratio_percent=assessment.overdue_ratio_percent,
        max_days_overdue=assessment.max_days_overdue,
        past_due_invoice_count=assessment.past_due_invoice_count,
        written_off_amount=assessment.written_off_amount,
        insurance_coverage_amount=assessment.insurance_coverage_amount,
        insurance_coverage_percent=assessment.insurance_coverage_percent,
        net_exposure_amount=assessment.net_exposure_amount,
        factors=assessment.factors or {},
        message=assessment.message,
        assessed_by=assessment.assessed_by,
        assessed_at=assessment.assessed_at,
        created_at=assessment.created_at,
    )


def _agent_risk_response(
    agent: B2BAgent,
    assessment: B2BCreditRiskAssessment | None,
) -> B2BCreditAgentRiskResponse:
    return B2BCreditAgentRiskResponse(
        id=str(agent.id),
        agent_number=agent.agent_number,
        company_name=agent.company_name,
        contact_name=agent.contact_name,
        email=agent.email,
        country=agent.country,
        status=agent.status,
        credit_status=agent.credit_status,  # type: ignore[arg-type]
        credit_status_reason=agent.credit_status_reason,
        credit_status_updated_by=agent.credit_status_updated_by,
        credit_status_updated_at=agent.credit_status_updated_at,
        credit_limit=agent.credit_limit,
        current_balance=agent.current_balance,
        currency=agent.currency,
        latest_assessment=(
            _assessment_response(assessment) if assessment is not None else None
        ),
    )


def _status_event_response(
    event: B2BCreditStatusEvent,
) -> B2BCreditStatusEventResponse:
    return B2BCreditStatusEventResponse(
        id=str(event.id),
        agent_id=str(event.agent_id),
        assessment_id=str(event.assessment_id) if event.assessment_id else None,
        previous_status=event.previous_status,  # type: ignore[arg-type]
        new_status=event.new_status,  # type: ignore[arg-type]
        action=event.action,
        reason=event.reason,
        actor=event.actor,
        evidence=event.evidence or {},
        created_at=event.created_at,
    )


def _insurance_response(
    policy: B2BCreditInsurancePolicy,
    *,
    agent: B2BAgent | None = None,
) -> B2BInsurancePolicyResponse:
    return B2BInsurancePolicyResponse(
        id=str(policy.id),
        agent_id=str(policy.agent_id),
        agent_company=agent.company_name if agent else "",
        policy_number=policy.policy_number,
        provider=policy.provider,
        status=policy.status,
        currency=policy.currency,
        coverage_limit=policy.coverage_limit,
        coverage_percent=policy.coverage_percent,
        effective_from=policy.effective_from,
        effective_to=policy.effective_to,
        notes=policy.notes,
        created_by=policy.created_by,
        updated_by=policy.updated_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def _claim_response(
    claim: B2BCreditInsuranceClaim,
    *,
    policy: B2BCreditInsurancePolicy | None = None,
    invoice: B2BInvoice | None = None,
    agent: B2BAgent | None = None,
) -> B2BInsuranceClaimResponse:
    return B2BInsuranceClaimResponse(
        id=str(claim.id),
        claim_number=claim.claim_number,
        policy_id=str(claim.policy_id),
        policy_number=policy.policy_number if policy else "",
        invoice_id=str(claim.invoice_id),
        invoice_number=invoice.invoice_number if invoice else "",
        agent_id=str(claim.agent_id),
        agent_company=agent.company_name if agent else "",
        status=claim.status,
        claimed_amount=claim.claimed_amount,
        recovered_amount=claim.recovered_amount,
        currency=claim.currency,
        reason=claim.reason,
        evidence=claim.evidence or {},
        created_by=claim.created_by,
        submitted_by=claim.submitted_by,
        submitted_at=claim.submitted_at,
        decided_by=claim.decided_by,
        decided_at=claim.decided_at,
        rejection_reason=claim.rejection_reason,
        settled_by=claim.settled_by,
        settled_at=claim.settled_at,
        settlement_reference=claim.settlement_reference,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


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


@router.get("/policies", response_model=B2BCreditPolicyListResponse)
async def list_credit_policies(
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditPolicyListResponse:
    policies = await b2b_credit_service.list_policies(
        db,
        workspace_id=workspace_id,
    )
    active = next((policy for policy in policies if policy.status == "active"), None)
    return B2BCreditPolicyListResponse(
        items=[_policy_response(policy) for policy in policies],
        active_policy=_policy_response(active) if active else None,
    )


@router.post("/policies", response_model=B2BCreditPolicyResponse, status_code=201)
async def create_credit_policy(
    req: B2BCreditPolicyCreate,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditPolicyResponse:
    try:
        policy = await b2b_credit_service.create_policy(
            db,
            workspace_id=workspace_id,
            actor=_actor(user),
            **req.model_dump(),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _policy_response(policy)


@router.post(
    "/policies/{policy_id}/submit",
    response_model=B2BCreditPolicyResponse,
)
async def submit_credit_policy(
    policy_id: str,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditPolicyResponse:
    try:
        policy = await b2b_credit_service.submit_policy(
            db,
            workspace_id=workspace_id,
            policy_id=policy_id,
            actor=_actor(user),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _policy_response(policy)


@router.post(
    "/policies/{policy_id}/approve",
    response_model=B2BCreditPolicyResponse,
)
async def approve_credit_policy(
    policy_id: str,
    user: CreditAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditPolicyResponse:
    try:
        policy = await b2b_credit_service.approve_policy(
            db,
            workspace_id=workspace_id,
            policy_id=policy_id,
            actor=_actor(user),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _policy_response(policy)


@router.post(
    "/policies/{policy_id}/reject",
    response_model=B2BCreditPolicyResponse,
)
async def reject_credit_policy(
    policy_id: str,
    req: B2BCreditPolicyDecision,
    user: CreditAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditPolicyResponse:
    try:
        policy = await b2b_credit_service.reject_policy(
            db,
            workspace_id=workspace_id,
            policy_id=policy_id,
            actor=_actor(user),
            reason=req.reason or "",
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _policy_response(policy)


@router.get("/risks", response_model=B2BCreditRiskOverviewResponse)
async def list_credit_risks(
    limit: int = Query(default=200, ge=1, le=1000),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditRiskOverviewResponse:
    rows, active_policy = await b2b_credit_service.list_risk_overview(
        db,
        workspace_id=workspace_id,
        limit=limit,
    )
    return B2BCreditRiskOverviewResponse(
        items=[_agent_risk_response(agent, assessment) for agent, assessment in rows],
        total=len(rows),
        active_policy=_policy_response(active_policy) if active_policy else None,
    )


@router.get(
    "/agents/{agent_id}",
    response_model=B2BCreditAgentRiskResponse,
)
async def get_credit_agent(
    agent_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditAgentRiskResponse:
    try:
        agent, assessment, _insurance = (
            await b2b_credit_service.get_agent_risk_detail(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
            )
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _agent_risk_response(agent, assessment)


@router.post(
    "/agents/{agent_id}/assess",
    response_model=B2BRiskAssessmentResponse,
)
async def assess_credit_agent(
    agent_id: str,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRiskAssessmentResponse:
    try:
        assessment = await b2b_credit_service.assess_agent(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
            actor=_actor(user),
            trace_id=get_trace_id(),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _assessment_response(assessment)


@router.post(
    "/agents/{agent_id}/status",
    response_model=B2BCreditAgentRiskResponse,
)
async def update_credit_agent_status(
    agent_id: str,
    req: B2BCreditStatusUpdate,
    user: CreditAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BCreditAgentRiskResponse:
    try:
        await b2b_credit_service.manual_update_status(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
            new_status=req.status,
            actor=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
        agent, assessment, _insurance = (
            await b2b_credit_service.get_agent_risk_detail(
                db,
                workspace_id=workspace_id,
                agent_id=agent_id,
            )
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _agent_risk_response(agent, assessment)


@router.get(
    "/agents/{agent_id}/history",
    response_model=list[B2BCreditStatusEventResponse],
)
async def get_credit_agent_history(
    agent_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[B2BCreditStatusEventResponse]:
    try:
        events = await b2b_credit_service.list_status_events(
            db,
            workspace_id=workspace_id,
            agent_id=agent_id,
            limit=limit,
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return [_status_event_response(event) for event in events]


@router.get("/insurance", response_model=B2BInsurancePolicyListResponse)
async def list_credit_insurance(
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsurancePolicyListResponse:
    policies = await b2b_credit_service.list_insurance_policies(
        db,
        workspace_id=workspace_id,
        agent_id=agent_id,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={row.agent_id for row in policies},
    )
    return B2BInsurancePolicyListResponse(
        items=[
            _insurance_response(row, agent=agents.get(row.agent_id))
            for row in policies
        ],
        total=len(policies),
    )


@router.post(
    "/insurance",
    response_model=B2BInsurancePolicyResponse,
    status_code=201,
)
async def create_credit_insurance(
    req: B2BInsurancePolicyCreate,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsurancePolicyResponse:
    try:
        policy = await b2b_credit_service.create_insurance_policy(
            db,
            workspace_id=workspace_id,
            actor=_actor(user),
            **req.model_dump(),
            trace_id=get_trace_id(),
        )
        agent = (await _agent_map(
            db,
            workspace_id=workspace_id,
            agent_ids={policy.agent_id},
        )).get(policy.agent_id)
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _insurance_response(policy, agent=agent)


@router.put(
    "/insurance/{policy_id}",
    response_model=B2BInsurancePolicyResponse,
)
async def update_credit_insurance(
    policy_id: str,
    req: B2BInsurancePolicyUpdate,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsurancePolicyResponse:
    try:
        policy = await b2b_credit_service.update_insurance_policy(
            db,
            workspace_id=workspace_id,
            policy_id=policy_id,
            actor=_actor(user),
            **req.model_dump(exclude_unset=True),
            trace_id=get_trace_id(),
        )
        agent = (await _agent_map(
            db,
            workspace_id=workspace_id,
            agent_ids={policy.agent_id},
        )).get(policy.agent_id)
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _insurance_response(policy, agent=agent)


@router.get("/claims", response_model=B2BInsuranceClaimListResponse)
async def list_credit_claims(
    status: str | None = Query(default=None, max_length=24),
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsuranceClaimListResponse:
    claims = await b2b_credit_service.list_insurance_claims(
        db,
        workspace_id=workspace_id,
        status=status,
        agent_id=agent_id,
    )
    policy_ids = {row.policy_id for row in claims}
    invoice_ids = {row.invoice_id for row in claims}
    agent_ids = {row.agent_id for row in claims}
    policies = (
        await db.execute(
            select(B2BCreditInsurancePolicy).where(
                B2BCreditInsurancePolicy.workspace_id == workspace_id,
                B2BCreditInsurancePolicy.id.in_(policy_ids),
            )
        )
    ).scalars().all() if policy_ids else []
    invoices = (
        await db.execute(
            select(B2BInvoice).where(
                B2BInvoice.workspace_id == workspace_id,
                B2BInvoice.id.in_(invoice_ids),
            )
        )
    ).scalars().all() if invoice_ids else []
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids=agent_ids,
    )
    policy_map = {row.id: row for row in policies}
    invoice_map = {row.id: row for row in invoices}
    return B2BInsuranceClaimListResponse(
        items=[
            _claim_response(
                claim,
                policy=policy_map.get(claim.policy_id),
                invoice=invoice_map.get(claim.invoice_id),
                agent=agents.get(claim.agent_id),
            )
            for claim in claims
        ],
        total=len(claims),
    )


@router.post(
    "/claims",
    response_model=B2BInsuranceClaimResponse,
    status_code=201,
)
async def create_credit_claim(
    req: B2BInsuranceClaimCreate,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsuranceClaimResponse:
    try:
        claim = await b2b_credit_service.create_insurance_claim(
            db,
            workspace_id=workspace_id,
            actor=_actor(user),
            **req.model_dump(),
            trace_id=get_trace_id(),
        )
        policy = (
            await db.execute(
                select(B2BCreditInsurancePolicy).where(
                    B2BCreditInsurancePolicy.id == claim.policy_id
                )
            )
        ).scalar_one()
        invoice = (
            await db.execute(
                select(B2BInvoice).where(B2BInvoice.id == claim.invoice_id)
            )
        ).scalar_one()
        agent = (await _agent_map(
            db,
            workspace_id=workspace_id,
            agent_ids={claim.agent_id},
        )).get(claim.agent_id)
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _claim_response(
        claim,
        policy=policy,
        invoice=invoice,
        agent=agent,
    )


@router.post(
    "/claims/{claim_id}/submit",
    response_model=B2BInsuranceClaimResponse,
)
async def submit_credit_claim(
    claim_id: str,
    user: CreditEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsuranceClaimResponse:
    try:
        claim = await b2b_credit_service.transition_insurance_claim(
            db,
            workspace_id=workspace_id,
            claim_id=claim_id,
            new_status="submitted",
            actor=_actor(user),
            trace_id=get_trace_id(),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _claim_response(claim)


@router.post(
    "/claims/{claim_id}/approve",
    response_model=B2BInsuranceClaimResponse,
)
async def approve_credit_claim(
    claim_id: str,
    user: CreditAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsuranceClaimResponse:
    try:
        claim = await b2b_credit_service.transition_insurance_claim(
            db,
            workspace_id=workspace_id,
            claim_id=claim_id,
            new_status="approved",
            actor=_actor(user),
            trace_id=get_trace_id(),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _claim_response(claim)


@router.post(
    "/claims/{claim_id}/reject",
    response_model=B2BInsuranceClaimResponse,
)
async def reject_credit_claim(
    claim_id: str,
    req: B2BInsuranceClaimDecision,
    user: CreditAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsuranceClaimResponse:
    try:
        claim = await b2b_credit_service.transition_insurance_claim(
            db,
            workspace_id=workspace_id,
            claim_id=claim_id,
            new_status="rejected",
            actor=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _claim_response(claim)


@router.post(
    "/claims/{claim_id}/settle",
    response_model=B2BInsuranceClaimResponse,
)
async def settle_credit_claim(
    claim_id: str,
    req: B2BInsuranceClaimSettle,
    user: CreditAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BInsuranceClaimResponse:
    try:
        claim = await b2b_credit_service.transition_insurance_claim(
            db,
            workspace_id=workspace_id,
            claim_id=claim_id,
            new_status="settled",
            actor=_actor(user),
            recovered_amount=req.recovered_amount,
            settlement_reference=req.settlement_reference,
            trace_id=get_trace_id(),
        )
    except (b2b_credit_service.B2BCreditError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _claim_response(claim)
