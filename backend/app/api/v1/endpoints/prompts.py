"""Prompt registry endpoints (M2.2)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.prompt import PromptCreate, PromptOut
from app.services import prompt_registry
from app.services.prompt_registry import PromptConflictError, PromptRegistryError

router = APIRouter(prefix="/prompts", tags=["prompts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: PromptRegistryError) -> HTTPException:
    """Map registry errors to HTTP responses."""
    if isinstance(exc, PromptConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("", response_model=PromptOut, status_code=201, summary="Register a prompt")
async def create_prompt(
    body: PromptCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> PromptOut:
    """Register a new versioned prompt template (never hardcoded)."""
    try:
        prompt = await prompt_registry.create_prompt(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except PromptRegistryError as exc:
        raise _http_error(exc) from exc
    return PromptOut.model_validate(prompt)


@router.get("", response_model=list[PromptOut], summary="List prompts")
async def list_prompts(
    db: DbSession,
    workspace_id: WorkspaceId,
    name: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[PromptOut]:
    """List registered prompts (optionally filtered by name)."""
    rows = await prompt_registry.list_prompts(db, workspace_id=workspace_id, name=name, limit=limit)
    return [PromptOut.model_validate(row) for row in rows]
