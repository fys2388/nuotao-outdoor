"""Product intelligence API endpoints (M2.1).

Routes under ``/products`` extend the existing product domain; routes under
``/product-decisions`` manage the human approval workflow. No AI agent is
involved in this phase - all processing is deterministic.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.models.product import Product
from app.schemas.product import ProductOut
from app.schemas.product_intelligence import (
    DecisionApproveRequest,
    ProductAnalysisRunOut,
    ProductCostSnapshotOut,
    ProductDecisionOut,
    ProductIntakeRequest,
    ProductIntakeResult,
    ProductIntelligenceOut,
    ProductScoreOut,
    ProductSourceOut,
)
from app.services import product_intelligence as pi

product_router = APIRouter(prefix="/products", tags=["product-intelligence"])
decision_router = APIRouter(prefix="/product-decisions", tags=["product-decisions"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: pi.ProductIntelligenceError) -> HTTPException:
    """Map service errors to 400, or 404 for missing resources."""
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
            db, workspace_id=workspace_id, product_id=product_id,
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
    return ProductScoreOut.model_validate(score)


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product not found"
        )
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
    rows = await pi.list_cost_snapshots(
        db, workspace_id=workspace_id, product_id=product_id
    )
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
            db, workspace_id=workspace_id, product_id=product_id,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProductDecisionOut.model_validate(decision)


@decision_router.post(
    "/{decision_id}/approve",
    response_model=ProductDecisionOut,
    summary="Approve a pending product decision",
)
async def approve_decision(
    decision_id: UUID,
    body: DecisionApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductDecisionOut:
    """Approve the decision; test decisions advance the product lifecycle."""
    try:
        decision = await pi.approve_decision(
            db,
            workspace_id=workspace_id,
            decision_id=decision_id,
            actor=body.actor,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
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
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductDecisionOut:
    """Reject the decision (audited)."""
    try:
        decision = await pi.reject_decision(
            db,
            workspace_id=workspace_id,
            decision_id=decision_id,
            actor=body.actor,
            trace_id=get_trace_id(),
        )
    except pi.ProductIntelligenceError as exc:
        raise _http_error(exc) from exc
    return ProductDecisionOut.model_validate(decision)
