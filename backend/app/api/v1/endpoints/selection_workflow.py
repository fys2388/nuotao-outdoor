"""API endpoints for the LangGraph selection workflow.

Provides endpoints to:
- Trigger a selection workflow run for a product
- Get the latest workflow run for a product
- Get system status
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.selection_workflow import (
    SelectionWorkflowRunOut,
    SelectionWorkflowTriggerRequest,
)
from app.services.selection_pipeline import (
    get_latest_workflow_run,
    get_selection_workflow_status,
    run_selection_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/selection-workflow", tags=["selection-workflow"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Default workspace ID (matches selection_manager_service.py)
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")


@router.get(
    "/status",
    summary="Get selection workflow system status",
)
async def get_status() -> dict[str, Any]:
    """Get the selection workflow system status and configuration."""
    return get_selection_workflow_status()


@router.post(
    "/run",
    response_model=SelectionWorkflowRunOut,
    summary="Trigger a selection workflow run",
)
async def trigger_workflow(
    request: SelectionWorkflowTriggerRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    Trigger the LangGraph selection workflow for a product.

    The workflow executes:
    1. Market data collection (Google Trends, Amazon, TikTok, seasonality)
    2. Initial screening (6 hard gates)
    3. V3 scoring (11-dimension operational + 6-dimension Nuotao Score)
    4. Veto check (V1-V12 proactive rejection)
    5. Decision recommendation (test/hold/reject)

    The result is persisted as a pending ProductDecision that requires
    human approval before any action is taken (Human-in-the-loop).
    """
    try:
        product_id = UUID(request.product_id)
        workspace_id = (
            UUID(request.workspace_id)
            if request.workspace_id
            else DEFAULT_WORKSPACE_ID
        )

        result_state = await run_selection_workflow(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            target_market=request.target_market,
            dry_run=request.dry_run,
            trace_id=f"api-{uuid4().hex[:12]}",
        )
        await db.commit()

        if result_state.error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Workflow failed: {result_state.error}",
            )

        return SelectionWorkflowRunOut(
            run_id=result_state.run_id or "",
            product_id=result_state.product_id,
            workspace_id=result_state.workspace_id,
            status=result_state.status,
            current_stage=result_state.current_stage,
            recommended_decision=result_state.recommended_decision,
            nuotao_score_total=result_state.nuotao_score_total,
            nuotao_grade=result_state.nuotao_grade,
            veto_passed=result_state.veto_passed,
            confidence=result_state.confidence,
            reasons=result_state.reasons,
            risks=result_state.risks,
            trace_id=result_state.trace_id,
            error=result_state.error,
        ).model_dump()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Trigger selection workflow failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trigger selection workflow failed: {e!s}",
        )


@router.get(
    "/products/{product_id}/latest",
    response_model=SelectionWorkflowRunOut,
    summary="Get the latest selection workflow run for a product",
)
async def get_product_latest_run(
    product_id: str,
    db: DbSession,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Get the most recent selection workflow run for a product."""
    try:
        pid = UUID(product_id)
        ws_id = UUID(workspace_id) if workspace_id else DEFAULT_WORKSPACE_ID

        result = await get_latest_workflow_run(
            db,
            workspace_id=ws_id,
            product_id=pid,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No selection workflow run found for product {product_id}",
            )

        return result.model_dump()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
