"""Connector and decision intelligence endpoints (M4.3).

Connectors synchronize external data (WooCommerce / logistics / marketing /
supplier) through the connector service; business recommendations are
proposals that require human approval. No automatic business actions.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.connector import CONNECTOR_NAMES, ConnectorRunOut, ConnectorSyncRequest
from app.schemas.recommendation import (
    RecommendationApproveRequest,
    RecommendationCreate,
    RecommendationOut,
)
from app.services import connector_service, recommendation_service

router = APIRouter(tags=["connectors"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _recommendation_error(exc: recommendation_service.RecommendationError) -> HTTPException:
    """Map recommendation errors: missing resources -> 404, state errors -> 400."""
    if "not found" in str(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# --------------------------------------------------------------------------- #
# Connector sync + run audit
# --------------------------------------------------------------------------- #


@router.post(
    "/connectors/{connector_name}/sync",
    response_model=ConnectorRunOut,
    summary="Run a connector synchronization (WooCommerce/logistics/marketing/supplier)",
)
async def sync_connector(
    connector_name: str,
    body: ConnectorSyncRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ConnectorRunOut:
    """Trigger one connector sync; returns the connector_runs audit record."""
    if connector_name not in CONNECTOR_NAMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown connector '{connector_name}'",
        )
    source: dict = dict(body.config or {})
    if body.data is not None:
        source["data"] = body.data
    try:
        run = await connector_service.run_connector_sync(
            db,
            workspace_id=workspace_id,
            connector_name=connector_name,
            source=source,
            trace_id=get_trace_id(),
        )
    except connector_service.ConnectorServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ConnectorRunOut.model_validate(run)


@router.get(
    "/connector-runs",
    response_model=list[ConnectorRunOut],
    summary="List connector run audit records",
)
async def list_connector_runs(
    db: DbSession,
    workspace_id: WorkspaceId,
    connector_name: Annotated[str | None, Query()] = None,
    run_status: Annotated[str | None, Query(alias="status")] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ConnectorRunOut]:
    """Return connector run audit rows, newest first, workspace-scoped."""
    runs, _total = await connector_service.list_connector_runs(
        db,
        workspace_id=workspace_id,
        connector_name=connector_name,
        status=run_status,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [ConnectorRunOut.model_validate(run) for run in runs]


# --------------------------------------------------------------------------- #
# Decision intelligence: business recommendations (human approval required)
# --------------------------------------------------------------------------- #


@router.post(
    "/business-recommendations",
    response_model=RecommendationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a business recommendation (status=proposed)",
)
async def propose_recommendation(
    body: RecommendationCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RecommendationOut:
    """Create a recommendation proposal awaiting human approval."""
    try:
        recommendation = await recommendation_service.propose_recommendation(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except recommendation_service.RecommendationError as exc:
        raise _recommendation_error(exc) from exc
    return RecommendationOut.model_validate(recommendation)


@router.get(
    "/business-recommendations",
    response_model=list[RecommendationOut],
    summary="List business recommendations",
)
async def list_recommendations(
    db: DbSession,
    workspace_id: WorkspaceId,
    rec_status: Annotated[str | None, Query(alias="status")] = None,
    domain: Annotated[str | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[RecommendationOut]:
    """Return recommendations, newest first, workspace-scoped."""
    recommendations, _total = await recommendation_service.list_recommendations(
        db,
        workspace_id=workspace_id,
        status=rec_status,
        domain=domain,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return [RecommendationOut.model_validate(item) for item in recommendations]


@router.post(
    "/business-recommendations/{recommendation_id}/approve",
    response_model=RecommendationOut,
    summary="Approve a proposed recommendation (human-in-the-loop)",
)
async def approve_recommendation(
    recommendation_id: UUID,
    body: RecommendationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RecommendationOut:
    """Approve a proposal; only ``proposed`` recommendations can be approved."""
    try:
        recommendation = await recommendation_service.approve_recommendation(
            db,
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except recommendation_service.RecommendationError as exc:
        raise _recommendation_error(exc) from exc
    return RecommendationOut.model_validate(recommendation)


@router.post(
    "/business-recommendations/{recommendation_id}/reject",
    response_model=RecommendationOut,
    summary="Reject a proposed recommendation (human-in-the-loop)",
)
async def reject_recommendation(
    recommendation_id: UUID,
    body: RecommendationApproveRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RecommendationOut:
    """Reject a proposal; only ``proposed`` recommendations can be rejected."""
    try:
        recommendation = await recommendation_service.reject_recommendation(
            db,
            workspace_id=workspace_id,
            recommendation_id=recommendation_id,
            actor=body.actor,
            note=body.note,
            trace_id=get_trace_id(),
        )
    except recommendation_service.RecommendationError as exc:
        raise _recommendation_error(exc) from exc
    return RecommendationOut.model_validate(recommendation)
