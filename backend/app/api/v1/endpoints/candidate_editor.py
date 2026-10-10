"""Candidate detail editor API endpoints (PHASE 3).

Provides GET and PATCH for product candidate details under
/product-candidates. These routes complement the existing lifecycle
endpoints (status/promote/drafts) and provide full detail view +
field-level editing.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.services import candidate_editor
from app.services.candidate_editor import CandidateEditorError

router = APIRouter(prefix="/product-candidates", tags=["candidate-editor"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CandidateEditRequest(BaseModel):
    """Partial update payload for a candidate.

    Only non-null fields in the request body are applied. Omitted fields
    are left unchanged. Protected fields (id, sku, status, candidate_status,
    mastered_at, etc.) are rejected.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    weight_kg: float | None = Field(default=None, gt=0)
    dimensions: dict[str, Any] | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    source_url: str | None = Field(default=None, max_length=512)
    source_offer_id: str | None = Field(default=None, max_length=64)
    meta: dict[str, Any] | None = None
    target_market: str | None = Field(default=None, max_length=16)


class CandidateEditResult(BaseModel):
    product_id: UUID
    sku: str
    name: str
    candidate_status: str | None
    updated_fields: list[str]


class CandidateDetailResponse(BaseModel):
    product: dict[str, Any]
    cost: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    sourcing_candidates: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{product_id}",
    response_model=CandidateDetailResponse,
    summary="Get full candidate detail (product + cost + score + sources)",
)
async def get_candidate_detail(
    product_id: UUID,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CandidateDetailResponse:
    """Return a complete view of a candidate product including its latest
    cost, score, sources, and sourcing candidates. Missing data is reported
    as null, never fabricated.
    """
    try:
        detail = await candidate_editor.get_candidate_detail(
            db, workspace_id=workspace_id, product_id=product_id,
        )
    except CandidateEditorError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=msg,
        ) from exc
    return CandidateDetailResponse.model_validate(detail)


@router.patch(
    "/{product_id}",
    response_model=CandidateEditResult,
    summary="Edit candidate product details (partial update)",
)
async def edit_candidate(
    product_id: UUID,
    body: CandidateEditRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CandidateEditResult:
    """Partially update a candidate product's details.

    Only candidate-status products (candidate/approved/testing) can be
    edited. Protected fields (id, sku, status, candidate_status,
    mastered_at, data_integrity_*) are never editable.

    The update is atomic: if any field fails validation, the entire
    request is rejected (400) and no changes are persisted.

    On success, an audit event (product.candidate.edited) is recorded
    in the same transaction.
    """
    from app.core.tracing import get_trace_id

    # Build the update dict: only include fields that were provided
    data: dict[str, Any] = {}
    for field_name in (
        "name", "description", "category", "brand",
        "weight_kg", "dimensions", "attributes", "tags",
        "source_url", "source_offer_id", "meta", "target_market",
    ):
        value = getattr(body, field_name, None)
        if value is not None:
            data[field_name] = value

    try:
        result = await candidate_editor.edit_candidate(
            db,
            workspace_id=workspace_id,
            product_id=product_id,
            data=data,
            trace_id=get_trace_id(),
        )
        await db.commit()
    except CandidateEditorError as exc:
        await db.rollback()
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=msg,
        ) from exc
    except Exception:
        await db.rollback()
        raise

    return CandidateEditResult.model_validate(result)
