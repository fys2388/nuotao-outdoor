"""Knowledge memory endpoints (M2.3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.knowledge import KnowledgeEntryCreate, KnowledgeEntryOut
from app.services import knowledge

router = APIRouter(prefix="/knowledge-entries", tags=["knowledge-memory"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


@router.post(
    "",
    response_model=KnowledgeEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product knowledge entry",
)
async def create_knowledge_entry(
    body: KnowledgeEntryCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> KnowledgeEntryOut:
    """Record a success/failure pattern or category insight."""
    try:
        entry = await knowledge.create_knowledge_entry(
            db, workspace_id=workspace_id, data=body, trace_id=get_trace_id()
        )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return KnowledgeEntryOut.model_validate(entry)


@router.get(
    "",
    response_model=list[KnowledgeEntryOut],
    summary="Query knowledge entries by category/product/type",
)
async def list_knowledge_entries(
    db: DbSession,
    workspace_id: WorkspaceId,
    category: str | None = None,
    product_id: UUID | None = None,
    entry_type: str | None = None,
    limit: int = 100,
) -> list[KnowledgeEntryOut]:
    """Return matching entries, newest first."""
    rows = await knowledge.list_knowledge_entries(
        db,
        workspace_id=workspace_id,
        category=category,
        product_id=product_id,
        entry_type=entry_type,
        limit=limit,
    )
    return [KnowledgeEntryOut.model_validate(row) for row in rows]
