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
from app.schemas.pilot import PilotOut, PilotRequest
from app.schemas.product_analyst import (
    EvaluationCreate,
    EvaluationOut,
    ProductAnalysisResultOut,
)
from app.schemas.product_intelligence import ProductAnalysisRunOut
from app.services import ai_evaluation, pilot_product_analyst

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


# --------------------------------------------------------------------------- #
# M5.6 Production pilot: task + scorecard + ROI (no auto business actions)
# --------------------------------------------------------------------------- #


@router.post(
    "/product-analyst/pilot",
    response_model=PilotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a Product Analyst pilot task (never auto-approves)",
)
async def pilot_analysis(
    body: PilotRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PilotOut:
    """Create + enqueue one product-analysis task and optionally wait.

    The output contains the task/trace ids and, when waited to completion,
    the analysis run + pending decision proposal. Approving the decision,
    proposing and starting experiments stay human-only.
    """
    trace_id = get_trace_id()
    try:
        task = await pilot_product_analyst.create_pilot_task(
            db,
            workspace_id=workspace_id,
            product_id=body.product_id,
            actor=body.actor,
            trace_id=trace_id,
        )
        await db.commit()
        waiting = False
        if body.wait_seconds:
            task = await pilot_product_analyst.wait_for_task(
                db,
                task_id=task.id,
                timeout_seconds=body.wait_seconds,
            )
            waiting = True
    except pilot_product_analyst.PilotError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    run_id = None
    decision_id = None
    decision = None
    approval_status = None
    provider = None
    model = None
    cost = None
    latency = None
    if task.status == "completed":
        # The run/decision are the audit facts of the chain; resolve them from
        # the DB (task.result holds only the structured LLM output).
        from sqlalchemy import select

        from app.models.product_intelligence import (
            ProductAnalysisRun,
            ProductDecision,
        )

        task_trace = task.trace_id
        run = (
            await db.execute(
                select(ProductAnalysisRun)
                .where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.product_id == body.product_id,
                    ProductAnalysisRun.provider != "deterministic",
                )
                .order_by(ProductAnalysisRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None and task_trace:
            run = (
                await db.execute(
                    select(ProductAnalysisRun).where(
                        ProductAnalysisRun.workspace_id == workspace_id,
                        ProductAnalysisRun.trace_id == task_trace,
                    )
                )
            ).scalar_one_or_none()
        if run is not None:
            run_id = run.id
            provider = run.provider
            model = run.model
            cost = run.estimated_cost
            latency = run.latency_ms
            decision_row = (
                await db.execute(
                    select(ProductDecision)
                    .where(
                        ProductDecision.workspace_id == workspace_id,
                        ProductDecision.product_id == body.product_id,
                    )
                    .order_by(ProductDecision.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if decision_row is not None:
                decision_id = decision_row.id
                decision = decision_row.decision
                approval_status = decision_row.approval_status
    return PilotOut(
        task_id=task.id,
        workspace_id=workspace_id,
        product_id=body.product_id,
        trace_id=task.trace_id or trace_id,
        status=task.status,
        analysis_run_id=run_id,
        decision_proposal_id=decision_id,
        decision=decision,
        approval_status=approval_status,
        provider=provider,
        model=model,
        cost=cost,
        latency_ms=latency,
        error_message=task.error_message,
        waiting=waiting,
    )


@router.get(
    "/product-analyst/scorecard",
    response_model=dict,
    summary="Product Analyst scorecard (workspace-scoped, no PII)",
)
async def product_analyst_scorecard(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return the analyst scorecard aggregates for the workspace."""
    return await pilot_product_analyst.scorecard(db, workspace_id=workspace_id)


@router.get(
    "/product-analyst/roi",
    response_model=dict,
    summary="Product Analyst ROI (real costs; impact null until attribution)",
)
async def product_analyst_roi(
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict:
    """Return ROI figures; revenue/margin/roas impacts are null (no mock)."""
    return await pilot_product_analyst.roi(db, workspace_id=workspace_id)
