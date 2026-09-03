"""Product intelligence API endpoints (M2.1).

Routes under ``/products`` extend the existing product domain; routes under
``/product-decisions`` manage the human approval workflow. No AI agent is
involved in this phase - all processing is deterministic.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import resolve_actor
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.models.product import Product
from app.schemas.agent_operations import ApprovalOut
from app.schemas.product import ProductOut
from app.schemas.product_intelligence import (
    CandidateCsvIntakeResult,
    CandidateStatusUpdateRequest,
    DecisionApproveRequest,
    ExperimentCompleteRequest,
    ExperimentProposeFromDecisionRequest,
    ExperimentStartRequest,
    ProductAnalysisRunOut,
    ProductCostSnapshotOut,
    ProductDecisionOut,
    ProductExperimentOut,
    ProductIntakeRequest,
    ProductIntakeResult,
    ProductIntelligenceOut,
    ProductScoreEvidenceOut,
    ProductScoreOut,
    ProductSourceOut,
    PromoteCandidateRequest,
    SourcingCandidateCreate,
    SourcingCandidateOut,
    WooCommerceDraftOut,
)
from app.services import (
    approval_service,
    product_intelligence as pi,
    task_queue,
)
from app.services.approval_rbac import ApprovalRBACError, check_actor_permission
from app.services.product_intelligence import ProductDecisionActorError

product_router = APIRouter(prefix="/products", tags=["product-intelligence"])
decision_router = APIRouter(prefix="/product-decisions", tags=["product-decisions"])
candidate_router = APIRouter(prefix="/product-candidates", tags=["product-candidates"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]

MAX_CSV_INTAKE_BYTES = 5 * 1024 * 1024  # 5 MiB


def _http_error(exc: Exception) -> HTTPException:
    """Map service errors: RBAC/actor -> 403, missing -> 404, state -> 400."""
    if isinstance(exc, (ApprovalRBACError, ProductDecisionActorError)):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@product_router.post(
    "/intake",
    response_model=ProductIntakeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Manual product intake (1688 URL, supplier, cost, weight)",
)
async def intake_product(
    body: ProductIntakeRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductIntakeResult:
    """Ingest a product manually; creates source + cost snapshot + score."""
    try:
        return await pi.intake_product(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc


@product_router.post(
    "/intake/csv",
    response_model=CandidateCsvIntakeResult,
    status_code=status.HTTP_200_OK,
    summary="Bulk Product Candidate intake from UTF-8 CSV (1688/MANUAL/CSV rows)",
)
async def intake_candidates_csv(
    file: UploadFile,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CandidateCsvIntakeResult:
    """Parse a UTF-8/BOM CSV (<=5 MiB) and run every row through the candidate
    intake (source + cost snapshot + score + audit). Bad rows are isolated and
    reported; nothing is guessed and no product table is duplicated.
    """
    content = await file.read(MAX_CSV_INTAKE_BYTES + 1)
    if len(content) > MAX_CSV_INTAKE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV file exceeds the 5 MiB limit",
        )
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must be UTF-8 encoded",
        ) from exc
    return await pi.intake_products_csv(
        db,
        workspace_id=workspace_id,
        csv_content=csv_text,
        trace_id=get_trace_id(),
    )


@product_router.post(
    "/{product_id}/analyze",
    response_model=ProductScoreOut,
    summary="Run deterministic product analysis",
)
async def analyze_product(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductScoreOut:
    """Run Cost -> Logistics -> Profit -> Rules -> Score; persists audit rows."""
    try:
        await pi.analyze_product(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    score = await pi.latest_score(db, workspace_id=workspace_id, product_id=product_id)
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="analysis completed but score not found",
        )
    evidence = await pi.list_score_evidences(db, workspace_id=workspace_id, score_id=score.id)
    out = ProductScoreOut.model_validate(score)
    out.evidence = [ProductScoreEvidenceOut.model_validate(row) for row in evidence]
    return out


@product_router.get(
    "/{product_id}/intelligence",
    response_model=ProductIntelligenceOut,
    summary="Aggregated product intelligence view",
)
async def get_intelligence(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductIntelligenceOut:
    """Return product + latest score + analysis + decision."""
    product = (
        await db.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    score = await pi.latest_score(db, workspace_id=workspace_id, product_id=product_id)
    analysis = await pi.latest_analysis(db, workspace_id=workspace_id, product_id=product_id)
    decision = await pi.latest_decision(db, workspace_id=workspace_id, product_id=product_id)
    return ProductIntelligenceOut(
        product=ProductOut.model_validate(product),
        score=ProductScoreOut.model_validate(score) if score else None,
        analysis=ProductAnalysisRunOut.model_validate(analysis) if analysis else None,
        decision=ProductDecisionOut.model_validate(decision) if decision else None,
    )


@product_router.get(
    "/{product_id}/sources",
    response_model=list[ProductSourceOut],
    summary="List product sources",
)
async def list_sources(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[ProductSourceOut]:
    """Return captured sources for a product, newest first."""
    rows = await pi.list_sources(db, workspace_id=workspace_id, product_id=product_id)
    return [ProductSourceOut.model_validate(row) for row in rows]


@product_router.get(
    "/{product_id}/cost-snapshots",
    response_model=list[ProductCostSnapshotOut],
    summary="List product cost history (append-only)",
)
async def list_cost_snapshots(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[ProductCostSnapshotOut]:
    """Return the immutable cost history of a product, newest first."""
    rows = await pi.list_cost_snapshots(db, workspace_id=workspace_id, product_id=product_id)
    return [ProductCostSnapshotOut.model_validate(row) for row in rows]


@product_router.post(
    "/{product_id}/decisions",
    response_model=ProductDecisionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a product decision (pending approval)",
)
async def propose_decision(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductDecisionOut:
    """Propose test/hold/reject from the latest score (deterministic)."""
    try:
        decision = await pi.propose_decision(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProductDecisionOut.model_validate(decision)


@decision_router.post(
    "/{decision_id}/approve",
    response_model=ProductDecisionOut,
    summary="Approve a pending product decision (Approval Center + RBAC)",
)
async def approve_decision(
    decision_id: UUID,
    body: DecisionApproveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductDecisionOut:
    """Approve the decision through the unified Approval Center.

    The actor must hold ``product.decision.approve`` (403 otherwise); agents
    can never decide their own proposals; a second decision is 400. Test
    decisions advance the product lifecycle after approval.
    """
    try:
        approval = await _resolve_product_decision_approval(
            db, workspace_id=workspace_id, decision_id=decision_id
        )
        backend = task_queue.get_queue_backend()
        await approval_service.approve_approval(
            db,
            backend,
            workspace_id=workspace_id,
            approval_id=approval.id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
        decision = await pi.get_decision(db, workspace_id=workspace_id, decision_id=decision_id)
        if decision is None:
            raise pi.ProductIntelligenceError("decision not found")
    except (approval_service.ApprovalError, pi.ProductIntelligenceError) as exc:
        raise _http_error(exc) from exc
    except ApprovalRBACError as exc:
        raise _http_error(exc) from exc
    except ProductDecisionActorError as exc:
        raise _http_error(exc) from exc
    return ProductDecisionOut.model_validate(decision)


@decision_router.post(
    "/{decision_id}/reject",
    response_model=ProductDecisionOut,
    summary="Reject a pending product decision",
)
async def reject_decision(
    decision_id: UUID,
    body: DecisionApproveRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductDecisionOut:
    """Reject the decision through the Approval Center (RBAC + audit)."""
    try:
        approval = await _resolve_product_decision_approval(
            db, workspace_id=workspace_id, decision_id=decision_id
        )
        backend = task_queue.get_queue_backend()
        await approval_service.reject_approval(
            db,
            backend,
            workspace_id=workspace_id,
            approval_id=approval.id,
            actor=resolve_actor(request, body.actor),
            note=body.note,
            trace_id=get_trace_id(),
        )
        decision = await pi.get_decision(db, workspace_id=workspace_id, decision_id=decision_id)
        if decision is None:
            raise pi.ProductIntelligenceError("decision not found")
    except (approval_service.ApprovalError, pi.ProductIntelligenceError) as exc:
        raise _http_error(exc) from exc
    except ApprovalRBACError as exc:
        raise _http_error(exc) from exc
    except ProductDecisionActorError as exc:
        raise _http_error(exc) from exc
    return ProductDecisionOut.model_validate(decision)


async def _resolve_product_decision_approval(
    db: AsyncSession,
    *,
    workspace_id: WorkspaceId,
    decision_id: UUID,
) -> Any:
    """Return (creating if needed) the PRODUCT_DECISION approval row."""
    from sqlalchemy import select

    from app.models.agent_operations import AgentApproval

    approval = (
        await db.execute(
            select(AgentApproval).where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.approval_type == "PRODUCT_DECISION",
                AgentApproval.entity_id == str(decision_id),
            )
        )
    ).scalar_one_or_none()
    if approval is not None:
        return approval
    decision = await pi.get_decision(db, workspace_id=workspace_id, decision_id=decision_id)
    if decision is None:
        raise pi.ProductIntelligenceError("decision not found")
    return await approval_service.ensure_approval(
        db,
        workspace_id=workspace_id,
        approval_type="PRODUCT_DECISION",
        entity_type="product_decision",
        entity_id=str(decision.id),
        metadata_={"product_id": str(decision.product_id), "decision": decision.decision},
        trace_id=get_trace_id(),
    )


@decision_router.post(
    "/{decision_id}/experiment",
    response_model=ProductExperimentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an experiment proposal from an approved decision",
)
async def propose_decision_experiment(
    decision_id: UUID,
    body: ExperimentProposeFromDecisionRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductExperimentOut:
    """Propose a market test for an APPROVED decision (never auto-started).

    The experiment starts in ``proposed``; starting it is a second human
    control point (``started_by``) - the agent can never do it.
    """
    try:
        experiment = await pi.propose_experiment_for_decision(
            db,
            workspace_id=workspace_id,
            decision_id=decision_id,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProductExperimentOut.model_validate(experiment)


# --------------------------------------------------------------------------- #
# M2.1.5: sourcing candidates, score evidence, product experiments
# --------------------------------------------------------------------------- #


@product_router.post(
    "/{product_id}/candidates",
    response_model=SourcingCandidateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a supplier candidate for a product",
)
async def create_sourcing_candidate(
    product_id: UUID,
    body: SourcingCandidateCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SourcingCandidateOut:
    """Add one supplier candidate (one product, many quotes)."""
    try:
        candidate = await pi.create_sourcing_candidate(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return SourcingCandidateOut.model_validate(candidate)


@product_router.get(
    "/{product_id}/candidates",
    response_model=list[SourcingCandidateOut],
    summary="List supplier candidates for a product",
)
async def list_sourcing_candidates(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[SourcingCandidateOut]:
    """Return supplier candidates, newest first."""
    rows = await pi.list_sourcing_candidates(db, workspace_id=workspace_id, product_id=product_id)
    return [SourcingCandidateOut.model_validate(row) for row in rows]


@product_router.post(
    "/{product_id}/experiments",
    response_model=ProductExperimentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a product testing experiment",
)
async def propose_experiment(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductExperimentOut:
    """Propose a testing loop; prediction is captured from the latest score."""
    try:
        experiment = await pi.propose_experiment(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProductExperimentOut.model_validate(experiment)


@product_router.get(
    "/{product_id}/experiments",
    response_model=list[ProductExperimentOut],
    summary="List experiments for a product",
)
async def list_experiments(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[ProductExperimentOut]:
    """Return experiments, newest first."""
    rows = await pi.list_experiments(db, workspace_id=workspace_id, product_id=product_id)
    return [ProductExperimentOut.model_validate(row) for row in rows]


@decision_router.post(
    "/experiments/{experiment_id}/start",
    response_model=ProductExperimentOut,
    summary="Start an experiment with the executed test plan",
)
async def start_experiment(
    experiment_id: UUID,
    body: ExperimentStartRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductExperimentOut:
    """Activate the experiment (proposed -> active)."""
    if body.started_by:
        body.started_by = resolve_actor(request, body.started_by)
    try:
        experiment = await pi.start_experiment(
            db,
            workspace_id=workspace_id,
            experiment_id=experiment_id,
            data=body,
            trace_id=get_trace_id(),
        )
    except (pi.ProductIntelligenceError, ProductDecisionActorError) as exc:
        raise _http_error(exc) from exc
    return ProductExperimentOut.model_validate(experiment)


@decision_router.post(
    "/experiments/{experiment_id}/complete",
    response_model=ProductExperimentOut,
    summary="Complete an experiment with measured results",
)
async def complete_experiment(
    experiment_id: UUID,
    body: ExperimentCompleteRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductExperimentOut:
    """Complete the experiment and backfill actuals into the learning loop.

    The measured outcome flows through the unified evaluation bridge
    (``product_ai_evaluations`` + agent evaluation mirror) so M2.3
    calibration consumes real results. Append-only; no rule is changed.
    """
    if body.actor:
        body.actor = resolve_actor(request, body.actor)
    try:
        from app.services import pilot_product_analyst

        experiment = await pilot_product_analyst.complete_experiment_with_evaluation(
            db,
            workspace_id=workspace_id,
            experiment_id=experiment_id,
            data=body,
            trace_id=body.trace_id or get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProductExperimentOut.model_validate(experiment)


@decision_router.get(
    "/experiments/{experiment_id}",
    response_model=ProductExperimentOut,
    summary="Get one product experiment",
)
async def get_experiment(
    experiment_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductExperimentOut:
    """Return one experiment (workspace-scoped)."""
    from app.services.product_intelligence import _load_experiment

    experiment = await _load_experiment(db, workspace_id=workspace_id, experiment_id=experiment_id)
    if experiment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="experiment not found")
    return ProductExperimentOut.model_validate(experiment)


@decision_router.get(
    "/scores/{score_id}/evidence",
    response_model=list[ProductScoreEvidenceOut],
    summary="Return per-dimension evidence of a score",
)
async def score_evidence(
    score_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[ProductScoreEvidenceOut]:
    """Return the six per-dimension evidence rows of a product score."""
    rows = await pi.list_score_evidences(db, workspace_id=workspace_id, score_id=score_id)
    return [ProductScoreEvidenceOut.model_validate(row) for row in rows]


# --------------------------------------------------------------------------- #
# M5.13 Product Candidate lifecycle + commerce boundary
# --------------------------------------------------------------------------- #


@candidate_router.post(
    "/{product_id}/status",
    response_model=ProductOut,
    summary="Move a Product Candidate through the lifecycle (human-judged)",
)
async def set_candidate_status(
    product_id: UUID,
    body: CandidateStatusUpdateRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductOut:
    """Update ``candidate_status`` with the M5.13 state machine.

    Agent actors are rejected (403); the actor must hold
    ``product.candidate.manage`` when RBAC roles are configured.
    """
    try:
        actor = resolve_actor(request, body.actor)
        await pi._assert_human_actor(
            db, workspace_id=workspace_id, actor=actor
        )
        await check_actor_permission(
            db,
            workspace_id=workspace_id,
            actor=actor,
            permission="product.candidate.manage",
        )
        product = await pi.update_candidate_status(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            new_status=body.status,
            actor=actor,
            trace_id=get_trace_id(),
        )
    except (pi.ProductIntelligenceError, ProductDecisionActorError, ApprovalRBACError) as exc:
        raise _http_error(exc) from exc
    return ProductOut.model_validate(product)


@candidate_router.post(
    "/{product_id}/promote",
    response_model=ApprovalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request human approval to promote a winner to a WooCommerce draft",
)
async def promote_candidate(
    product_id: UUID,
    body: PromoteCandidateRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ApprovalOut:
    """Create the ``PRODUCT_CANDIDATE`` approval proposal for a winner.

    Phase 1: nothing is written to WooCommerce. After human approval the
    draft payload is generated for a human operator to use in the admin.
    """
    try:
        actor = resolve_actor(request, body.actor)
        await pi._assert_human_actor(
            db, workspace_id=workspace_id, actor=actor
        )
        await check_actor_permission(
            db,
            workspace_id=workspace_id,
            actor=actor,
            permission="product.candidate.promote",
        )
        approval = await pi.request_promote(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            actor=actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except (pi.ProductIntelligenceError, ProductDecisionActorError, ApprovalRBACError) as exc:
        raise _http_error(exc) from exc
    return ApprovalOut.model_validate(approval)


@candidate_router.get(
    "/{product_id}/drafts",
    response_model=list[WooCommerceDraftOut],
    summary="List generated WooCommerce draft payloads (read-only)",
)
async def list_woocommerce_drafts(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> list[WooCommerceDraftOut]:
    """Return the generated draft payloads of a product (newest first)."""
    rows = await pi.list_woocommerce_drafts(db, workspace_id=workspace_id, product_id=product_id)
    return [WooCommerceDraftOut.model_validate(row) for row in rows]
