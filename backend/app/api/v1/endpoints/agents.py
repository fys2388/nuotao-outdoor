"""Product Analyst Agent + AI evaluation endpoints (M2.2).

The agent endpoint only produces analysis + proposals; approval endpoints
remain the human-only workflow under ``/product-decisions``.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import product_analyst
from app.agents.product_analyst import ProductAnalystError
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.product_analyst import (
    EvaluationCreate,
    EvaluationOut,
    ProductAnalysisResultOut,
)
from app.schemas.product_intelligence import ProductAnalysisRunOut
from app.services import ai_evaluation

router = APIRouter(prefix="/agents", tags=["agents"])
evaluation_router = APIRouter(prefix="/ai-evaluations", tags=["ai-evaluations"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _analyst_error(exc: ProductAnalystError) -> HTTPException:
    """Map agent errors: missing resources -> 404, everything else -> 422."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post(
    "/product-analyst/analyze/{product_id}",
    response_model=ProductAnalysisResultOut,
    summary="Run the Product Analyst Agent (analysis + proposal only)",
)
async def analyze_product(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ProductAnalysisResultOut:
    """Analyze a product via LLM; persists audit + pending decision proposal."""
    try:
        result = await product_analyst.analyze_product(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            trace_id=get_trace_id(),
        )
    except ProductAnalystError as exc:
        raise _analyst_error(exc) from exc
    return product_analyst.to_result_out(result)


@router.get(
    "/product-analyst/runs/{product_id}",
    response_model=list[ProductAnalysisRunOut],
    summary="List AI analysis runs for a product",
)
async def list_analysis_runs(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
    limit: int = 20,
) -> list[ProductAnalysisRunOut]:
    """Return the most recent LLM analysis runs (newest first)."""
    rows = await product_analyst.latest_runs(
        db, workspace_id=workspace_id, product_id=product_id, limit=limit
    )
    return [ProductAnalysisRunOut.model_validate(row) for row in rows]


@evaluation_router.post(
    "",
    response_model=EvaluationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record an AI prediction evaluation",
)
async def create_evaluation(
    body: EvaluationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> EvaluationOut:
    """Record prediction vs actual (with optional human rating)."""
    try:
        evaluation = await ai_evaluation.record_evaluation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except ai_evaluation.EvaluationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return EvaluationOut.model_validate(evaluation)


@evaluation_router.get(
    "",
    response_model=list[EvaluationOut],
    summary="List AI evaluations",
)
async def list_evaluations(
    db: DbSession,
    workspace_id: WorkspaceId,
    product_id: UUID | None = None,
    limit: int = 50,
) -> list[EvaluationOut]:
    """Return evaluations, newest first, optionally for one product."""
    rows = await ai_evaluation.list_evaluations(
        db, workspace_id=workspace_id, product_id=product_id, limit=limit
    )
    return [EvaluationOut.model_validate(row) for row in rows]
