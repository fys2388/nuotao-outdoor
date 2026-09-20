"""Admin APIs for customer identity, consent, merge, and privacy requests."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.models.customer import CustomerAccount
from app.models.customer_identity import (
    CustomerAccountMerge,
    CustomerConsentEvent,
    CustomerIdentityLink,
    DataSubjectRequest,
    DataSubjectRequestAction,
)
from app.schemas.customer_privacy import (
    AccountMergeCreate,
    AccountMergeDecision,
    AccountMergeListResponse,
    AccountMergeResponse,
    ConsentEventCreate,
    ConsentEventResponse,
    ConsentHistoryResponse,
    ConsentSummaryResponse,
    CustomerAccountResponse,
    CustomerDataStatsResponse,
    DataSubjectRequestActionResponse,
    DataSubjectRequestCreate,
    DataSubjectRequestDecision,
    DataSubjectRequestDetailResponse,
    DataSubjectRequestExecute,
    DataSubjectRequestListResponse,
    DataSubjectRequestReject,
    DataSubjectRequestResponse,
    DataSubjectRequestVerify,
    IdentityLinkCreate,
    IdentityLinkListResponse,
    IdentityLinkResponse,
    IdentityResolveRequest,
    IdentityResolveResponse,
)
from app.schemas.user import UserResponse
from app.services import (
    customer_consent_service,
    customer_identity_service,
    customer_privacy_service,
)

router = APIRouter(prefix="/admin/customer-data", tags=["admin-customer-data"])
WorkspaceId = UUID
DataEditor = Annotated[UserResponse, Depends(require_role("operator"))]
DataAdmin = Annotated[UserResponse, Depends(require_role("admin"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(
        exc,
        (
            customer_identity_service.CustomerIdentityNotFoundError,
            customer_consent_service.CustomerConsentNotFoundError,
            customer_privacy_service.CustomerPrivacyNotFoundError,
        ),
    ):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc,
        (
            customer_identity_service.CustomerIdentityConflictError,
            customer_identity_service.CustomerIdentityStateError,
            customer_consent_service.CustomerConsentError,
            customer_privacy_service.CustomerPrivacyStateError,
        ),
    ):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(
        exc,
        (
            customer_identity_service.CustomerIdentityError,
            customer_privacy_service.CustomerPrivacyError,
            ValueError,
        ),
    ):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="customer data operation failed")


def _account_response(account: CustomerAccount) -> CustomerAccountResponse:
    return CustomerAccountResponse(
        id=account.id,
        customer_number=account.customer_number,
        customer_type=account.customer_type,
        business_model=account.business_model,
        display_name=account.display_name,
        status=account.status,
        country=account.country,
        default_currency=account.default_currency,
        merged_into_account_id=account.merged_into_account_id,
        merged_at=account.merged_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _link_response(link: CustomerIdentityLink) -> IdentityLinkResponse:
    return IdentityLinkResponse(
        id=link.id,
        customer_account_id=link.customer_account_id,
        channel=link.channel,
        external_system=link.external_system,
        identity_type=link.identity_type,
        fingerprint=link.fingerprint,
        hash_key_version=link.hash_key_version,
        verification_status=link.verification_status,
        source=link.source,
        verified_at=link.verified_at,
        last_seen_at=link.last_seen_at,
        disabled_at=link.disabled_at,
        metadata=link.metadata_json or {},
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _merge_response(merge: CustomerAccountMerge) -> AccountMergeResponse:
    return AccountMergeResponse(
        id=merge.id,
        source_account_id=merge.source_account_id,
        target_account_id=merge.target_account_id,
        status=merge.status,
        match_type=merge.match_type,
        match_hash_prefix=merge.match_hash[:16],
        evidence=merge.evidence_json or {},
        reason=merge.reason,
        requested_by=merge.requested_by,
        reviewed_by=merge.reviewed_by,
        reviewed_at=merge.reviewed_at,
        rejection_reason=merge.rejection_reason,
        completed_by=merge.completed_by,
        completed_at=merge.completed_at,
        result_summary=merge.result_summary or {},
        created_at=merge.created_at,
        updated_at=merge.updated_at,
    )


def _consent_response(event: CustomerConsentEvent) -> ConsentEventResponse:
    return ConsentEventResponse(
        id=event.id,
        customer_account_id=event.customer_account_id,
        purpose=event.purpose,
        channel=event.channel,
        status=event.status,
        policy_version=event.policy_version,
        source=event.source,
        occurred_at=event.occurred_at,
        recorded_by=event.recorded_by,
        evidence=event.evidence_json or {},
        created_at=event.created_at,
    )


def _request_response(request: DataSubjectRequest) -> DataSubjectRequestResponse:
    return DataSubjectRequestResponse(
        id=request.id,
        request_number=request.request_number,
        customer_account_id=request.customer_account_id,
        request_type=request.request_type,
        status=request.status,
        identity_hash_prefix=(
            request.identity_hash[:16] if request.identity_hash else None
        ),
        verification_method=request.verification_method,
        verified_by=request.verified_by,
        verified_at=request.verified_at,
        due_at=request.due_at,
        handled_by=request.handled_by,
        decided_at=request.decided_at,
        completed_at=request.completed_at,
        rejection_reason=request.rejection_reason,
        request_details=request.request_details,
        result_summary=request.result_summary or {},
        evidence=request.evidence_json or {},
        requested_by=request.requested_by,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _action_response(
    action: DataSubjectRequestAction,
) -> DataSubjectRequestActionResponse:
    return DataSubjectRequestActionResponse(
        id=action.id,
        action_type=action.action_type,
        actor=action.actor,
        note=action.note,
        result=action.result_json or {},
        created_at=action.created_at,
    )


@router.get("/stats", response_model=CustomerDataStatsResponse)
async def customer_data_stats(
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> CustomerDataStatsResponse:
    identity_stats = await customer_identity_service.identity_governance_stats(
        db,
        workspace_id=workspace_id,
    )
    request_stats = await customer_privacy_service.privacy_stats(
        db,
        workspace_id=workspace_id,
    )
    return CustomerDataStatsResponse(
        **identity_stats,
        requests=request_stats,
    )


@router.get("/accounts", response_model=list[CustomerAccountResponse])
async def list_customer_accounts(
    status: str | None = Query(default=None, max_length=24),
    business_model: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> list[CustomerAccountResponse]:
    rows = await customer_identity_service.list_accounts(
        db,
        workspace_id=workspace_id,
        status=status,
        business_model=business_model,
        limit=limit,
    )
    return [_account_response(row) for row in rows]


@router.post("/identities/resolve", response_model=IdentityResolveResponse)
async def resolve_customer_identity(
    req: IdentityResolveRequest,
    user: DataEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> IdentityResolveResponse:
    try:
        if req.create_if_missing:
            account = await customer_identity_service.ensure_account_for_identity(
                db,
                workspace_id=workspace_id,
                identity_type=req.identity_type,
                identity_value=req.identity_value,
                channel=req.channel,
                external_system=req.external_system,
                customer_type=req.customer_type,
                business_model=req.business_model,
                display_name=req.display_name,
                country=req.country,
                default_currency=req.default_currency,
                source="admin_resolve",
                trace_id=get_trace_id(),
            )
        else:
            account = await customer_identity_service.resolve_identity(
                db,
                workspace_id=workspace_id,
                identity_type=req.identity_type,
                identity_value=req.identity_value,
            )
        await db.commit()
    except (
        customer_identity_service.CustomerIdentityError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    return IdentityResolveResponse(
        resolved=account is not None,
        account=_account_response(account) if account else None,
    )


@router.post("/identities", response_model=IdentityLinkResponse, status_code=201)
async def link_customer_identity(
    req: IdentityLinkCreate,
    user: DataEditor,
    response: Response,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> IdentityLinkResponse:
    try:
        link, conflict_account_id = (
            await customer_identity_service.link_identity_to_account(
                db,
                workspace_id=workspace_id,
                account_id=req.customer_account_id,
                identity_type=req.identity_type,
                identity_value=req.identity_value,
                channel=req.channel,
                external_system=req.external_system,
                source=req.source,
                metadata=req.metadata,
                trace_id=get_trace_id(),
            )
        )
        await db.commit()
        await db.refresh(link)
    except (
        customer_identity_service.CustomerIdentityError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    if conflict_account_id is not None:
        response.headers["X-Identity-Conflict-Account-Id"] = str(
            conflict_account_id
        )
    return _link_response(link)


@router.get("/identities", response_model=IdentityLinkListResponse)
async def list_customer_identities(
    status: str | None = Query(default=None, max_length=24),
    customer_account_id: UUID | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> IdentityLinkListResponse:
    rows = await customer_identity_service.list_identity_links(
        db,
        workspace_id=workspace_id,
        status=status,
        account_id=customer_account_id,
        limit=limit,
    )
    return IdentityLinkListResponse(
        items=[_link_response(row) for row in rows],
        total=len(rows),
    )


@router.post("/merges", response_model=AccountMergeResponse, status_code=201)
async def create_account_merge(
    req: AccountMergeCreate,
    user: DataEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AccountMergeResponse:
    try:
        merge = await customer_identity_service.create_merge_request(
            db,
            workspace_id=workspace_id,
            source_account_id=req.source_account_id,
            target_account_id=req.target_account_id,
            requested_by=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except (
        customer_identity_service.CustomerIdentityError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    return _merge_response(merge)


@router.get("/merges", response_model=AccountMergeListResponse)
async def list_account_merges(
    status: str | None = Query(default=None, max_length=24),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AccountMergeListResponse:
    rows = await customer_identity_service.list_merge_requests(
        db,
        workspace_id=workspace_id,
        status=status,
        limit=limit,
    )
    return AccountMergeListResponse(
        items=[_merge_response(row) for row in rows],
        total=len(rows),
    )


async def _transition_merge(
    *,
    merge_id: UUID,
    new_status: str,
    req: AccountMergeDecision | None,
    user: UserResponse,
    workspace_id: UUID,
    db: AsyncSession,
) -> AccountMergeResponse:
    try:
        merge = await customer_identity_service.transition_merge_request(
            db,
            workspace_id=workspace_id,
            merge_id=merge_id,
            new_status=new_status,
            actor=_actor(user),
            reason=req.reason if req else None,
            trace_id=get_trace_id(),
        )
    except (
        customer_identity_service.CustomerIdentityError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    return _merge_response(merge)


@router.post("/merges/{merge_id}/approve", response_model=AccountMergeResponse)
async def approve_account_merge(
    merge_id: UUID,
    req: AccountMergeDecision,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AccountMergeResponse:
    return await _transition_merge(
        merge_id=merge_id,
        new_status="approved",
        req=req,
        user=user,
        workspace_id=workspace_id,
        db=db,
    )


@router.post("/merges/{merge_id}/reject", response_model=AccountMergeResponse)
async def reject_account_merge(
    merge_id: UUID,
    req: AccountMergeDecision,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AccountMergeResponse:
    if not req.reason or len(req.reason.strip()) < 2:
        raise HTTPException(status_code=422, detail="rejection reason is required")
    return await _transition_merge(
        merge_id=merge_id,
        new_status="rejected",
        req=req,
        user=user,
        workspace_id=workspace_id,
        db=db,
    )


@router.post("/merges/{merge_id}/complete", response_model=AccountMergeResponse)
async def complete_account_merge(
    merge_id: UUID,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> AccountMergeResponse:
    return await _transition_merge(
        merge_id=merge_id,
        new_status="completed",
        req=None,
        user=user,
        workspace_id=workspace_id,
        db=db,
    )


@router.get("/consent", response_model=ConsentSummaryResponse)
async def get_customer_consent_summary(
    customer_account_id: UUID,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ConsentSummaryResponse:
    try:
        items = await customer_consent_service.consent_summary(
            db,
            workspace_id=workspace_id,
            customer_account_id=customer_account_id,
        )
    except (customer_consent_service.CustomerConsentError, ValueError) as exc:
        raise _http_error(exc) from exc
    return ConsentSummaryResponse(
        customer_account_id=customer_account_id,
        items=items,
    )


@router.get("/consent/history", response_model=ConsentHistoryResponse)
async def get_customer_consent_history(
    customer_account_id: UUID,
    purpose: str | None = Query(default=None, max_length=32),
    channel: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=500, ge=1, le=2000),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ConsentHistoryResponse:
    rows = await customer_consent_service.list_consent_history(
        db,
        workspace_id=workspace_id,
        customer_account_id=customer_account_id,
        purpose=purpose,
        channel=channel,
        limit=limit,
    )
    return ConsentHistoryResponse(
        items=[_consent_response(row) for row in rows],
        total=len(rows),
    )


@router.post("/consent/events", response_model=ConsentEventResponse, status_code=201)
async def append_customer_consent(
    req: ConsentEventCreate,
    user: DataEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> ConsentEventResponse:
    try:
        event = await customer_consent_service.append_consent_event(
            db,
            workspace_id=workspace_id,
            customer_account_id=req.customer_account_id,
            purpose=req.purpose,
            channel=req.channel,
            status=req.status,
            policy_version=req.policy_version,
            source=req.source,
            recorded_by=_actor(user),
            idempotency_key=req.idempotency_key,
            evidence=req.evidence,
            occurred_at=req.occurred_at,
            trace_id=get_trace_id(),
        )
    except (customer_consent_service.CustomerConsentError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _consent_response(event)


@router.get("/requests", response_model=DataSubjectRequestListResponse)
async def list_data_subject_requests(
    status: str | None = Query(default=None, max_length=24),
    request_type: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestListResponse:
    rows = await customer_privacy_service.list_requests(
        db,
        workspace_id=workspace_id,
        status=status,
        request_type=request_type,
        limit=limit,
    )
    return DataSubjectRequestListResponse(
        items=[_request_response(row) for row in rows],
        total=len(rows),
    )


@router.post(
    "/requests",
    response_model=DataSubjectRequestResponse,
    status_code=201,
)
async def create_data_subject_request(
    req: DataSubjectRequestCreate,
    user: DataEditor,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestResponse:
    try:
        request = await customer_privacy_service.create_request(
            db,
            workspace_id=workspace_id,
            request_type=req.request_type,
            requested_by=_actor(user),
            customer_account_id=req.customer_account_id,
            identity_type=req.identity_type,
            identity_value=req.identity_value,
            request_details=req.request_details,
            verification_method=req.verification_method,
            evidence=req.evidence,
            trace_id=get_trace_id(),
        )
    except (
        customer_privacy_service.CustomerPrivacyError,
        customer_identity_service.CustomerIdentityError,
        ValueError,
    ) as exc:
        raise _http_error(exc) from exc
    return _request_response(request)


@router.get(
    "/requests/{request_id}",
    response_model=DataSubjectRequestDetailResponse,
)
async def get_data_subject_request(
    request_id: UUID,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestDetailResponse:
    try:
        request, actions = await customer_privacy_service.request_detail(
            db,
            workspace_id=workspace_id,
            request_id=request_id,
        )
    except customer_privacy_service.CustomerPrivacyError as exc:
        raise _http_error(exc) from exc
    base = _request_response(request).model_dump()
    return DataSubjectRequestDetailResponse(
        **base,
        actions=[_action_response(action) for action in actions],
    )


@router.post(
    "/requests/{request_id}/verify",
    response_model=DataSubjectRequestResponse,
)
async def verify_data_subject_request(
    request_id: UUID,
    req: DataSubjectRequestVerify,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestResponse:
    try:
        request = await customer_privacy_service.verify_request(
            db,
            workspace_id=workspace_id,
            request_id=request_id,
            actor=_actor(user),
            verification_method=req.verification_method,
            note=req.note,
            trace_id=get_trace_id(),
        )
    except (customer_privacy_service.CustomerPrivacyError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _request_response(request)


@router.post(
    "/requests/{request_id}/approve",
    response_model=DataSubjectRequestResponse,
)
async def approve_data_subject_request(
    request_id: UUID,
    req: DataSubjectRequestDecision,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestResponse:
    try:
        request = await customer_privacy_service.approve_request(
            db,
            workspace_id=workspace_id,
            request_id=request_id,
            actor=_actor(user),
            note=req.note,
            trace_id=get_trace_id(),
        )
    except (customer_privacy_service.CustomerPrivacyError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _request_response(request)


@router.post(
    "/requests/{request_id}/reject",
    response_model=DataSubjectRequestResponse,
)
async def reject_data_subject_request(
    request_id: UUID,
    req: DataSubjectRequestReject,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestResponse:
    try:
        request = await customer_privacy_service.reject_request(
            db,
            workspace_id=workspace_id,
            request_id=request_id,
            actor=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except (customer_privacy_service.CustomerPrivacyError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _request_response(request)


@router.post(
    "/requests/{request_id}/cancel",
    response_model=DataSubjectRequestResponse,
)
async def cancel_data_subject_request(
    request_id: UUID,
    req: DataSubjectRequestDecision,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestResponse:
    try:
        request = await customer_privacy_service.cancel_request(
            db,
            workspace_id=workspace_id,
            request_id=request_id,
            actor=_actor(user),
            reason=req.note,
            trace_id=get_trace_id(),
        )
    except (customer_privacy_service.CustomerPrivacyError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _request_response(request)


@router.post(
    "/requests/{request_id}/execute",
    response_model=DataSubjectRequestResponse,
)
async def execute_data_subject_request(
    request_id: UUID,
    req: DataSubjectRequestExecute,
    user: DataAdmin,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> DataSubjectRequestResponse:
    try:
        request = await customer_privacy_service.execute_request(
            db,
            workspace_id=workspace_id,
            request_id=request_id,
            actor=_actor(user),
            note=req.note,
            trace_id=get_trace_id(),
        )
    except (customer_privacy_service.CustomerPrivacyError, ValueError) as exc:
        raise _http_error(exc) from exc
    return _request_response(request)
