"""API v1 — Product Factory Workflow endpoints.

Exposes:
- POST /workflow/trigger    — start a workflow for a product
- POST /workflow/resume     — resume a WAITING_APPROVAL workflow
- GET  /workflow/status     — get workflow run status
- GET  /workflow/runs       — list workflow runs
- GET  /workflow/exceptions — get exception queue
- POST /workflow/exceptions/{id}/resolve — resolve an exception
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.workspace import get_workspace_id

router = APIRouter(prefix="/workflow", tags=["workflow"])

WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


# ── Request schemas ─────────────────────────────────────────────────


class TriggerWorkflowRequest(BaseModel):
    product_id: UUID
    workflow_type: str = "product_factory"


class ResumeWorkflowRequest(BaseModel):
    run_id: UUID
    actor: str


class ResolveExceptionRequest(BaseModel):
    note: str | None = None


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/trigger")
async def trigger_workflow(body: TriggerWorkflowRequest, workspace_id: WorkspaceId):
    """Start (or resume existing) product factory workflow for a product."""
    from app.core.database import async_session_factory
    from app.services.product_factory_orchestrator import (
        execute_workflow,
        trigger_workflow as _trigger,
    )

    async with async_session_factory() as session:
        try:
            run = await _trigger(
                session,
                workspace_id=workspace_id,
                product_id=body.product_id,
                workflow_type=body.workflow_type,
            )
            # Auto-execute the first stage
            run = await execute_workflow(
                session,
                run_id=run.id,
                workspace_id=workspace_id,
            )
            await session.commit()
            await session.refresh(run)
            return {"success": True, "data": run.to_dict()}
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=500, detail=str(exc))


@router.post("/resume")
async def resume_workflow(body: ResumeWorkflowRequest, workspace_id: WorkspaceId):
    """Resume a WAITING_APPROVAL workflow."""
    from app.core.database import async_session_factory
    from app.services.product_factory_orchestrator import resume_workflow as _resume

    async with async_session_factory() as session:
        try:
            run = await _resume(
                session,
                run_id=body.run_id,
                workspace_id=workspace_id,
                actor=body.actor,
            )
            await session.commit()
            await session.refresh(run)
            return {"success": True, "data": run.to_dict()}
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/status")
async def get_workflow_status(
    run_id: UUID = Query(..., description="Workflow run ID"),
    workspace_id: WorkspaceId = None,
):
    """Get full status of a workflow run including exceptions and events."""
    from app.core.database import async_session_factory
    from app.services.product_factory_orchestrator import get_workflow_status as _get_status

    async with async_session_factory() as session:
        result = await _get_status(
            session,
            run_id=run_id,
            workspace_id=workspace_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        return {"success": True, "data": result}


@router.get("/runs")
async def list_workflow_runs(
    status: str | None = Query(None),
    product_id: UUID | None = Query(None),
    stage: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    workspace_id: WorkspaceId = None,
):
    """List workflow runs with optional filters."""
    from app.core.database import async_session_factory
    from app.services.product_factory_orchestrator import list_workflow_runs as _list

    async with async_session_factory() as session:
        runs = await _list(
            session,
            workspace_id=workspace_id,
            status=status,
            product_id=product_id,
            stage=stage,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": runs, "total": len(runs)}


@router.get("/exceptions")
async def get_exception_queue(
    unresolved_only: bool = Query(True),
    stage: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    workspace_id: WorkspaceId = None,
):
    """Get the workflow exception queue."""
    from app.core.database import async_session_factory
    from app.services.product_factory_orchestrator import get_exception_queue as _get_exc

    async with async_session_factory() as session:
        exceptions = await _get_exc(
            session,
            workspace_id=workspace_id,
            unresolved_only=unresolved_only,
            stage=stage,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": exceptions, "total": len(exceptions)}


@router.post("/exceptions/{exception_id}/resolve")
async def resolve_exception(
    exception_id: int,
    body: ResolveExceptionRequest,
    workspace_id: WorkspaceId = None,
):
    """Mark an exception as resolved."""
    from app.core.database import async_session_factory
    from app.services.product_factory_orchestrator import resolve_exception as _resolve

    async with async_session_factory() as session:
        try:
            result = await _resolve(
                session,
                workspace_id=workspace_id,
                exception_id=exception_id,
                actor="api_resolve",
                note=body.note,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="Exception not found")
            await session.commit()
            return {"success": True, "data": result}
        except HTTPException:
            raise
        except Exception as exc:
            await session.rollback()
            raise HTTPException(status_code=500, detail=str(exc))
