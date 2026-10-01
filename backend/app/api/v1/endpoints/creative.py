"""Creative Studio API endpoints (v0.17 C0).

Routes:
- GET  /api/v1/creative/status              — service status + capabilities
- GET  /api/v1/creative/models              — list available image models
- GET  /api/v1/creative/operations          — list available operations

Briefs:
- POST   /api/v1/creative/briefs              — create brief
- GET    /api/v1/creative/briefs              — list briefs
- GET    /api/v1/creative/briefs/{id}        — get brief detail
- PATCH  /api/v1/creative/briefs/{id}/status — update brief status

Generation Runs:
- POST   /api/v1/creative/runs               — create generation run
- POST   /api/v1/creative/runs/{id}/execute  — execute run (generate image)
- GET    /api/v1/creative/runs               — list runs
- GET    /api/v1/creative/runs/{id}          — get run detail

Assets:
- POST   /api/v1/creative/assets             — create/import asset
- GET    /api/v1/creative/assets             — list assets
- GET    /api/v1/creative/assets/{id}        — get asset detail
- GET    /api/v1/creative/assets/{id}/image  — serve asset image
- POST   /api/v1/creative/assets/{id}/qc     — run quality check
- POST   /api/v1/creative/assets/{id}/review — human review (approve/reject)

Reviews:
- GET    /api/v1/creative/reviews            — list reviews

Cost:
- GET    /api/v1/creative/cost/monthly       — monthly cost summary
- GET    /api/v1/creative/cost/budget        — budget check

Prompt Templates (C2):
- POST   /api/v1/creative/templates          — create template
- GET    /api/v1/creative/templates          — list templates
- GET    /api/v1/creative/templates/{id}     — get template detail
- PATCH  /api/v1/creative/templates/{id}     — update template
- POST   /api/v1/creative/templates/{id}/archive — archive template
- POST   /api/v1/creative/templates/{id}/render — render prompt with variables

Batch Generation (C3):
- POST   /api/v1/creative/briefs/{id}/generate — batch generate all brief assets

WooCommerce Integration (C4):
- POST   /api/v1/creative/assets/{id}/push-to-wc — push approved asset to WooCommerce

AI Quality Check (C6):
- POST   /api/v1/creative/assets/{id}/ai-qc — AI-based quality assessment

Creative Knowledge Learning (C7):
- POST   /api/v1/creative/knowledge/entries — create knowledge entry
- GET    /api/v1/creative/knowledge/entries — list knowledge entries
- POST   /api/v1/creative/knowledge/learn-from-review — extract knowledge from review
- GET    /api/v1/creative/knowledge/summary — generate learning summary

Creative Calibration (C8):
- POST   /api/v1/creative/calibration/run — run calibration analysis
- GET    /api/v1/creative/calibration/runs — list calibration runs
- POST   /api/v1/creative/calibration/runs/{id}/approve — approve calibration
- POST   /api/v1/creative/calibration/runs/{id}/reject — reject calibration

Creative Cost Tracking (C9):
- GET    /api/v1/creative/cost/summary — comprehensive cost summary
- GET    /api/v1/creative/cost/by-product/{product_id} — cost by product
- GET    /api/v1/creative/cost/by-brief/{brief_id} — cost by brief
- GET    /api/v1/creative/cost/events — list cost events
- GET    /api/v1/creative/cost/budget-forecast — budget check with forecast

Creative Approval Queue (C10):
- POST   /api/v1/creative/approvals/requests — create approval request
- GET    /api/v1/creative/approvals/requests — list approval requests
- GET    /api/v1/creative/approvals/queue-stats — queue statistics
- POST   /api/v1/creative/approvals/requests/{id}/approve — approve request
- POST   /api/v1/creative/approvals/requests/{id}/reject — reject request
- POST   /api/v1/creative/approvals/requests/{id}/execute — mark as executed

Creative Analytics & Reporting (C11):
- GET    /api/v1/creative/analytics/dashboard — comprehensive dashboard metrics
- GET    /api/v1/creative/analytics/performance — performance metrics
- GET    /api/v1/creative/analytics/templates — template effectiveness
- GET    /api/v1/creative/analytics/knowledge — knowledge growth

Creative Automation & Scheduling (C12):
- POST   /api/v1/creative/automation/workflows — create automation workflow
- GET    /api/v1/creative/automation/workflows — list automation workflows
- PATCH  /api/v1/creative/automation/workflows/{id} — update workflow
- POST   /api/v1/creative/automation/workflows/{id}/trigger — trigger workflow
- POST   /api/v1/creative/automation/check-scheduled — run scheduled workflow check
- POST   /api/v1/creative/automation/run-cost-monitor — run cost monitoring
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.integrations.creative_gateway import list_operations
from app.integrations.image_gen import DEFAULT_MODEL as DEFAULT_IMAGE_MODEL
from app.integrations.image_gen import list_available_models
from app.schemas.user import UserResponse
from app.services import creative_service
from app.services.creative_service import CreativeServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/creative", tags=["creative_studio"])

# ============================================
# Auth dependencies
# ============================================
# P0-1: Replace get_workspace_id with authenticated workspace resolver.
# Users must be logged in; workspace is derived from JWT claims.
# Role-based access control for write operations.

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[UserResponse, Depends(get_current_user)]
WorkspaceId = Annotated[UUID, Depends(get_current_workspace_id)]
# Operator role required for write operations (POST/PATCH/DELETE)
OperatorRole = Annotated[UserResponse, Depends(require_role("operator"))]


# ============================================
# Request / Response models
# ============================================


class CreateBriefRequest(BaseModel):
    """Request to create a creative brief."""

    product_id: str | None = Field(None, description="Associated product ID (UUID)")
    listing_id: str | None = Field(None, description="Associated listing ID (UUID)")
    brief_type: str = Field("product_hero", description="Brief type")
    objective: str | None = Field(None, description="Creative objective", max_length=2000)
    target_market: str | None = Field(None, description="Target market (US, EU, etc.)", max_length=64)
    channel: str | None = Field(None, description="Target channel (amazon, independent, etc.)", max_length=32)
    visual_style: str | None = Field(None, description="Visual style descriptor", max_length=128)
    required_assets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of required asset specifications",
    )
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Production constraints (budget, max_retries, etc.)",
    )
    created_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


class UpdateBriefStatusRequest(BaseModel):
    """Request to update brief status."""

    status: str = Field(..., description="New status")
    updated_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


class CreateRunRequest(BaseModel):
    """Request to create a generation run."""

    product_id: str | None = Field(None, description="Associated product ID")
    brief_id: str | None = Field(None, description="Associated brief ID")
    operation: str = Field("generate", description="Operation type")
    provider: str | None = Field(None, description="Provider name")
    model: str | None = Field(None, description="Model name")
    input_asset_ids: list[str] = Field(default_factory=list, description="Input asset UUIDs")
    prompt_template_id: str | None = Field(None, max_length=128)
    prompt_version: str | None = Field(None, max_length=64)
    parameters: dict[str, Any] = Field(default_factory=dict, description="Generation parameters")
    trace_id: str | None = Field(None, max_length=64)


class ExecuteRunRequest(BaseModel):
    """Request to execute a generation run."""

    prompt: str = Field(..., description="Text prompt", min_length=1, max_length=4000)
    model: str = Field(DEFAULT_IMAGE_MODEL, description="Model to use")
    width: int = Field(1024, ge=256, le=2048)
    height: int = Field(1024, ge=256, le=2048)
    reference_image: str | None = Field(None, max_length=2048)
    negative_prompt: str | None = Field(None, max_length=2000)
    trace_id: str | None = Field(None, max_length=64)


class CreateAssetRequest(BaseModel):
    """Request to create/import an asset."""

    product_id: str | None = Field(None)
    brief_id: str | None = Field(None)
    parent_asset_id: str | None = Field(None)
    asset_type: str = Field("hero_image", max_length=32)
    source_type: str = Field("ORIGINAL", max_length=16)
    storage_key: str | None = Field(None, max_length=1024)
    preview_url: str | None = Field(None, max_length=2048)
    width: int | None = Field(None, ge=1)
    height: int | None = Field(None, ge=1)
    ratio: str | None = Field(None, max_length=16)
    mime_type: str | None = Field(None, max_length=32)
    generation_run_id: str | None = Field(None)
    version: int = Field(1, ge=1)
    status: str = Field("DRAFT", max_length=16)
    quality_result: dict[str, Any] = Field(default_factory=dict)
    compliance_result: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


class ReviewAssetRequest(BaseModel):
    """Request to review an asset."""

    result: str = Field(..., description="Review result: approved or rejected")
    reasons: list[str] = Field(default_factory=list, description="Review reasons")
    reviewer_id: str = Field(..., max_length=128)
    trace_id: str | None = Field(None, max_length=64)


# ============================================
# Status & Discovery
# ============================================


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Return Creative Studio service status and capabilities."""
    return creative_service.get_creative_status()


@router.get("/models")
async def get_models() -> dict[str, Any]:
    """List available image models with pricing."""
    return {"models": list_available_models()}


@router.get("/operations")
async def get_operations() -> dict[str, Any]:
    """List available creative operations."""
    return {"operations": list_operations()}


# ============================================
# Briefs
# ============================================


@router.post("/briefs", status_code=status.HTTP_201_CREATED)
async def create_brief(
    body: CreateBriefRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create a new creative brief."""
    try:
        brief = await creative_service.create_brief(
            db,
            workspace_id=ws,
            product_id=UUID(body.product_id) if body.product_id else None,
            listing_id=UUID(body.listing_id) if body.listing_id else None,
            brief_type=body.brief_type,
            objective=body.objective,
            target_market=body.target_market,
            channel=body.channel,
            visual_style=body.visual_style,
            required_assets=body.required_assets,
            constraints=body.constraints,
            created_by=body.created_by,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._brief_to_dict(brief)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/briefs")
async def list_briefs(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    status: str | None = None,
    product_id: str | None = None,
    brief_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List creative briefs."""
    try:
        return await creative_service.list_briefs(
            db,
            workspace_id=ws,
            status=status,
            product_id=UUID(product_id) if product_id else None,
            brief_type=brief_type,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/briefs/{brief_id}")
async def get_brief(
    brief_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get a creative brief by ID."""
    result = await creative_service.get_brief(
        db, brief_id=brief_id, workspace_id=ws
    )
    if not result:
        raise HTTPException(status_code=404, detail="Brief not found")
    return result


@router.patch("/briefs/{brief_id}/status")
async def update_brief_status(
    brief_id: UUID,
    body: UpdateBriefStatusRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Update a brief's status."""
    try:
        brief = await creative_service.update_brief_status(
            db,
            brief_id=brief_id,
            status=body.status,
            workspace_id=ws,
            updated_by=body.updated_by,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._brief_to_dict(brief)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============================================
# Generation Runs
# ============================================


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    body: CreateRunRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create a new generation run (queued)."""
    # P0-3: Validate operation support status
    from app.integrations.creative_gateway import OPERATION_TYPES
    op_info = OPERATION_TYPES.get(body.operation)
    if not op_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown operation type: {body.operation}",
        )
    if op_info.get("status") == "UNSUPPORTED":
        reason = op_info.get("reason", "This operation is not implemented.")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "operation_not_supported",
                "operation": body.operation,
                "message": reason,
            },
        )

    try:
        run = await creative_service.create_generation_run(
            db,
            workspace_id=ws,
            product_id=UUID(body.product_id) if body.product_id else None,
            brief_id=UUID(body.brief_id) if body.brief_id else None,
            operation=body.operation,
            provider=body.provider,
            model=body.model,
            input_asset_ids=body.input_asset_ids,
            prompt_template_id=body.prompt_template_id,
            prompt_version=body.prompt_version,
            parameters=body.parameters,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._run_to_dict(run)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/runs/{run_id}/execute")
async def execute_run(
    run_id: UUID,
    body: ExecuteRunRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Execute a generation run: call gateway, persist result, create asset."""
    try:
        run = await creative_service.execute_generation(
            db,
            run_id=run_id,
            workspace_id=ws,
            prompt=body.prompt,
            model=body.model,
            width=body.width,
            height=body.height,
            reference_image=body.reference_image,
            negative_prompt=body.negative_prompt,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._run_to_dict(run)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/runs")
async def list_runs(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    run_status: str | None = None,
    product_id: str | None = None,
    brief_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List generation runs."""
    try:
        return await creative_service.list_generation_runs(
            db,
            workspace_id=ws,
            status=run_status,
            product_id=UUID(product_id) if product_id else None,
            brief_id=UUID(brief_id) if brief_id else None,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get a generation run by ID."""
    result = await creative_service.get_generation_run(
        db, run_id=run_id, workspace_id=ws
    )
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


# ============================================
# Creative Assets
# ============================================


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def create_asset(
    body: CreateAssetRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create/import a creative asset."""
    try:
        asset = await creative_service.create_asset(
            db,
            workspace_id=ws,
            product_id=UUID(body.product_id) if body.product_id else None,
            brief_id=UUID(body.brief_id) if body.brief_id else None,
            parent_asset_id=UUID(body.parent_asset_id) if body.parent_asset_id else None,
            asset_type=body.asset_type,
            source_type=body.source_type,
            storage_key=body.storage_key,
            preview_url=body.preview_url,
            width=body.width,
            height=body.height,
            ratio=body.ratio,
            mime_type=body.mime_type,
            generation_run_id=UUID(body.generation_run_id) if body.generation_run_id else None,
            version=body.version,
            status=body.status,
            quality_result=body.quality_result,
            compliance_result=body.compliance_result,
            created_by=body.created_by,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._asset_to_dict(asset)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/assets/upload", status_code=status.HTTP_201_CREATED)
async def upload_asset(
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
    file: UploadFile = File(...),
    product_id: str | None = None,
    brief_id: str | None = None,
    asset_type: str = "hero_image",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Upload an image file as a creative asset."""
    import base64
    import os

    from app.services.creative_service import IMAGE_STORAGE_DIR

    # Save file to storage
    ext = os.path.splitext(file.filename or ".png")[1].lower() or ".png"
    asset_id = UUID(os.urandom(16).hex())
    filepath = os.path.join(IMAGE_STORAGE_DIR, f"{asset_id}{ext}")
    os.makedirs(IMAGE_STORAGE_DIR, exist_ok=True)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    asset = await creative_service.create_asset(
        db,
        workspace_id=ws,
        product_id=UUID(product_id) if product_id else None,
        brief_id=UUID(brief_id) if brief_id else None,
        asset_type=asset_type,
        source_type="IMPORTED",
        storage_key=filepath,
        preview_url=f"/api/v1/creative/assets/{asset_id}/image",
        mime_type=file.content_type or "image/png",
        created_by="upload",
        trace_id=trace_id,
    )
    await db.commit()
    return creative_service._asset_to_dict(asset)


@router.get("/assets")
async def list_assets(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    asset_status: str | None = None,
    product_id: str | None = None,
    brief_id: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List creative assets."""
    try:
        return await creative_service.list_assets(
            db,
            workspace_id=ws,
            status=asset_status,
            product_id=UUID(product_id) if product_id else None,
            brief_id=UUID(brief_id) if brief_id else None,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/assets/{asset_id}")
async def get_asset(
    asset_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get a creative asset by ID."""
    result = await creative_service.get_asset(
        db, asset_id=asset_id, workspace_id=ws
    )
    if not result:
        raise HTTPException(status_code=404, detail="Asset not found")
    return result


@router.get("/assets/{asset_id}/image")
async def serve_asset_image(
    asset_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
):
    """Serve the image file for an asset."""
    result = await creative_service.get_asset(
        db, asset_id=asset_id, workspace_id=ws
    )
    if not result:
        raise HTTPException(status_code=404, detail="Asset not found")

    storage_key = result.get("storage_key")
    if not storage_key:
        raise HTTPException(status_code=404, detail="No image file")

    path = Path(storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path=str(path),
        media_type=content_type,
        filename=path.name,
    )


# ============================================
# Quality Check & Review
# ============================================


@router.post("/assets/{asset_id}/qc")
async def run_qc(
    asset_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run quality check on an asset."""
    try:
        qc_result = await creative_service.run_quality_check(
            db, asset_id=asset_id, workspace_id=ws, trace_id=trace_id
        )
        await db.commit()
        return qc_result
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/assets/{asset_id}/review")
async def review_asset(
    asset_id: UUID,
    body: ReviewAssetRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Human review of an asset (approve/reject)."""
    try:
        asset = await creative_service.review_asset(
            db,
            asset_id=asset_id,
            result=body.result,
            reasons=body.reasons,
            reviewer_id=body.reviewer_id,
            workspace_id=ws,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._asset_to_dict(asset)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============================================
# Reviews
# ============================================


@router.get("/reviews")
async def list_reviews(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    asset_id: str | None = None,
    review_type: str | None = None,
    result: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List creative reviews."""
    try:
        return await creative_service.list_reviews(
            db,
            workspace_id=ws,
            asset_id=UUID(asset_id) if asset_id else None,
            review_type=review_type,
            result=result,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============================================
# Cost
# ============================================


@router.get("/cost/monthly")
async def get_monthly_cost(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    year: int | None = None,
    month: int | None = None,
) -> dict[str, Any]:
    """Get monthly creative generation cost."""
    cost = await creative_service.get_monthly_cost(
        db, workspace_id=ws, year=year, month=month
    )
    return {"cost_cny": float(cost), "year": year, "month": month}


@router.get("/cost/budget")
async def check_budget(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    requested_cost: float = 0,
) -> dict[str, Any]:
    """Check budget for a requested generation cost."""
    from decimal import Decimal
    return await creative_service.check_budget(
        db,
        workspace_id=ws,
        requested_cost=Decimal(str(requested_cost)),
    )


# ============================================
# C1: Creative Workspace — Product Master integration
# ============================================


class CreateBriefFromProductRequest(BaseModel):
    """Request to auto-generate a brief from a product."""

    objective: str | None = Field(None, max_length=2000)
    channel: str | None = Field(None, max_length=32)
    target_market: str | None = Field(None, max_length=64)
    visual_style: str | None = Field(None, max_length=128)
    created_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


@router.get("/workspace/{product_id}")
async def get_workspace(
    product_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get the Creative Workspace state for a product.

    Returns aggregated view: product info, briefs, assets, generation
    runs, and summary counts. This is the main entry point from
    Product Master to Creative Studio.
    """
    try:
        return await creative_service.get_workspace(
            db, product_id=product_id, workspace_id=ws
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/workspace/{product_id}/brief", status_code=status.HTTP_201_CREATED)
async def create_brief_from_product(
    product_id: UUID,
    body: CreateBriefFromProductRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Auto-generate a creative brief from product data.

    Reads product attributes, target market, and category to derive
    required asset types and visual style recommendations.
    """
    try:
        brief = await creative_service.create_brief_from_product(
            db,
            product_id=product_id,
            workspace_id=ws,
            objective=body.objective,
            channel=body.channel,
            target_market=body.target_market,
            visual_style=body.visual_style,
            created_by=body.created_by,
            trace_id=body.trace_id,
        )
        await db.commit()
        return creative_service._brief_to_dict(brief)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ============================================
# C1: Listing Asset Set Integration
# ============================================


class AddAssetToListingRequest(BaseModel):
    """Request to add an approved asset to a listing job."""

    asset_id: str = Field(..., description="Approved asset UUID")
    trace_id: str | None = Field(None, max_length=64)


@router.post("/listing/{listing_job_id}/assets", status_code=status.HTTP_200_OK)
async def add_asset_to_listing(
    listing_job_id: UUID,
    body: AddAssetToListingRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Add an approved asset to a listing job's asset set.

    Only APPROVED assets can be added. The asset URL is injected
    into the listing job's payload for WooCommerce publishing.
    """
    try:
        return await creative_service.add_asset_to_listing(
            db,
            asset_id=UUID(body.asset_id),
            listing_job_id=listing_job_id,
            workspace_id=ws,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/listing/{listing_job_id}/assets")
async def get_listing_assets(
    listing_job_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get all creative assets attached to a listing job."""
    try:
        return await creative_service.get_listing_assets(
            db,
            listing_job_id=listing_job_id,
            workspace_id=ws,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ===================================================================
# Prompt Template Registry (C2)
# ===================================================================


class CreateTemplateRequest(BaseModel):
    """Request to create a new prompt template."""

    template_key: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    asset_type: str = Field("hero_image", max_length=32)
    category: str = Field("general", max_length=64)
    prompt_text: str = Field(..., min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    version: str = Field("1.0.0", max_length=32)
    status: str = Field("DRAFT", max_length=16)
    quality_score: float | None = Field(None, ge=0, le=5)
    created_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


class UpdateTemplateRequest(BaseModel):
    """Request to update a prompt template."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    prompt_text: str | None = Field(None, min_length=1)
    variables: dict[str, Any] | None = None
    default_parameters: dict[str, Any] | None = None
    version: str | None = Field(None, max_length=32)
    status: str | None = Field(None, max_length=16)
    quality_score: float | None = Field(None, ge=0, le=5)
    trace_id: str | None = Field(None, max_length=64)


class RenderPromptRequest(BaseModel):
    """Request to render a prompt template with variables."""

    variables: dict[str, Any] = Field(default_factory=dict)


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(
    body: CreateTemplateRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create a new prompt template."""
    try:
        template = await creative_service.create_prompt_template(
            db,
            workspace_id=ws,
            template_key=body.template_key,
            name=body.name,
            description=body.description,
            asset_type=body.asset_type,
            category=body.category,
            prompt_text=body.prompt_text,
            variables=body.variables,
            default_parameters=body.default_parameters,
            version=body.version,
            status=body.status,
            quality_score=body.quality_score,
            created_by=body.created_by,
            trace_id=body.trace_id,
        )
        return creative_service._prompt_template_to_dict(template)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/templates")
async def list_templates(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    category: str | None = None,
    asset_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List prompt templates with optional filters."""
    try:
        return await creative_service.list_prompt_templates(
            db,
            workspace_id=ws,
            category=category,
            asset_type=asset_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/templates/{template_id}")
async def get_template(
    template_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get a prompt template by ID."""
    try:
        result = await creative_service.get_prompt_template(
            db,
            template_id=template_id,
            workspace_id=ws,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        return result
    except CreativeServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/templates/{template_id}")
async def update_template(
    template_id: UUID,
    body: UpdateTemplateRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Update an existing prompt template."""
    try:
        template = await creative_service.update_prompt_template(
            db,
            template_id=template_id,
            workspace_id=ws,
            name=body.name,
            description=body.description,
            prompt_text=body.prompt_text,
            variables=body.variables,
            default_parameters=body.default_parameters,
            version=body.version,
            status=body.status,
            quality_score=body.quality_score,
            trace_id=body.trace_id,
        )
        return creative_service._prompt_template_to_dict(template)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/templates/{template_id}/archive")
async def archive_template(
    template_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Archive a prompt template (soft delete)."""
    try:
        template = await creative_service.archive_prompt_template(
            db,
            template_id=template_id,
            workspace_id=ws,
            trace_id=trace_id,
        )
        return creative_service._prompt_template_to_dict(template)
    except CreativeServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/templates/{template_id}/render")
async def render_template(
    template_id: UUID,
    body: RenderPromptRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Render a prompt template with provided variables.

    Returns the rendered prompt text with variables substituted.
    """
    try:
        template_data = await creative_service.get_prompt_template(
            db,
            template_id=template_id,
            workspace_id=ws,
        )
        if not template_data:
            raise HTTPException(status_code=404, detail="Template not found")

        rendered = creative_service.render_prompt(template_data, body.variables)

        # Increment usage count
        await creative_service.increment_usage_count(
            db,
            template_id=template_id,
            workspace_id=ws,
        )

        return {
            "template_id": str(template_id),
            "template_key": template_data["template_key"],
            "rendered_prompt": rendered,
            "variables_used": body.variables,
        }
    except CreativeServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ===================================================================
# Batch Generation Pipeline (C3)
# ===================================================================


class BatchGenerateRequest(BaseModel):
    """Request to batch generate all assets for a brief."""

    brief_id: str = Field(..., description="Brief UUID")
    model: str = Field("doubao-seedream-5-0-pro-260628", description="AI model to use")
    execute_immediately: bool = Field(
        True,
        description="If True, execute runs synchronously; if False, queue for background processing",
    )
    trace_id: str | None = Field(None, max_length=64)


@router.post("/briefs/{brief_id}/generate", status_code=status.HTTP_200_OK)
async def batch_generate_brief_assets(
    brief_id: UUID,
    body: BatchGenerateRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Batch generate all assets required by a CreativeBrief.

    Reads the brief's required_assets, finds matching prompt templates
    by asset_type, renders prompts with product data, and creates
    generation runs for each asset.

    If execute_immediately=True (default), runs are executed synchronously
    and assets are returned in the response. Otherwise, runs are queued
    for background processing.

    Returns a summary with all created runs and assets.
    """
    try:
        return await creative_service.generate_brief_assets(
            db,
            brief_id=brief_id,
            workspace_id=ws,
            model=body.model,
            execute_immediately=body.execute_immediately,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ===================================================================
# WooCommerce Integration (C4)
# ===================================================================


class PushToWooCommerceRequest(BaseModel):
    """Request to push an approved asset to WooCommerce."""

    as_featured_image: bool = Field(
        True,
        description="If True, set as featured image; if False, add to gallery",
    )
    trace_id: str | None = Field(None, max_length=64)


@router.post("/assets/{asset_id}/push-to-wc", status_code=status.HTTP_200_OK)
async def push_asset_to_wc(
    asset_id: UUID,
    body: PushToWooCommerceRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Push an approved creative asset to WooCommerce as a product image.

    Only APPROVED assets can be pushed. The image is uploaded to the
    WordPress media library via the WooCommerce REST API, and optionally
    set as the product's featured image or added to the gallery.

    Requires WooCommerce REST API credentials in the product's meta:
    - wc_base_url
    - wc_consumer_key
    - wc_consumer_secret
    - wc_product_id
    """
    try:
        return await creative_service.push_asset_to_woocommerce(
            db,
            asset_id=asset_id,
            workspace_id=ws,
            as_featured_image=body.as_featured_image,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ===================================================================
# AI Quality Check (C6)
# ===================================================================


class AICheckRequest(BaseModel):
    """Request to run AI-based quality check on an asset."""

    trace_id: str | None = Field(None, max_length=64)


@router.post("/assets/{asset_id}/ai-qc", status_code=status.HTTP_200_OK)
async def run_ai_quality_check(
    asset_id: UUID,
    body: AICheckRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Run AI-based quality check on a creative asset.

    Uses LLM to analyze the image and assess:
    - Product fidelity (does the image match the product?)
    - Visual quality (resolution, artifacts, composition)
    - E-commerce readiness (background, visibility, conversion)
    - Compliance (copyright, PII, inappropriate content)
    - Regeneration suggestions

    The asset status is updated based on the AI recommendation:
    - 'approve' -> QC_PASSED
    - 'approve_with_notes' -> QC_PASSED (with notes)
    - 'regenerate' or 'reject' -> REJECTED
    """
    from app.agents.creative_agent import run_ai_quality_check as run_qc

    try:
        return await run_qc(
            db,
            workspace_id=ws,
            asset_id=asset_id,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ===================================================================
# Creative Knowledge Learning (C7)
# ===================================================================


class CreateKnowledgeEntryRequest(BaseModel):
    """Request to create a creative knowledge entry."""

    entry_type: str = Field(..., description="Knowledge entry type")
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    product_id: str | None = Field(None, description="Optional product UUID")
    asset_id: str | None = Field(None, description="Optional asset UUID")
    brief_id: str | None = Field(None, description="Optional brief UUID")
    category: str | None = Field(None, max_length=64)
    asset_type: str | None = Field(None, max_length=32)
    tags: list[str] = Field(default_factory=list)
    source: str = Field("manual", max_length=32)
    confidence: float = Field(0.0, ge=0, le=1)
    success_count: int = Field(0, ge=0)
    failure_count: int = Field(0, ge=0)
    created_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


@router.post("/knowledge/entries", status_code=status.HTTP_201_CREATED)
async def create_knowledge_entry(
    body: CreateKnowledgeEntryRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create a creative knowledge entry.

    Knowledge entries store patterns learned from creative assets:
    - success_pattern: patterns from successful creative assets
    - failure_pattern: patterns from failed/rejected assets
    - style_pattern: visual style patterns
    - prompt_pattern: effective prompt patterns
    - fidelity_pattern: product fidelity patterns
    - ecommerce_pattern: e-commerce readiness patterns
    - best_practice: general best practices
    - lesson_learned: specific lessons from incidents
    """
    try:
        return await creative_service.create_knowledge_entry(
            db,
            workspace_id=ws,
            entry_type=body.entry_type,
            title=body.title,
            content=body.content,
            product_id=UUID(body.product_id) if body.product_id else None,
            asset_id=UUID(body.asset_id) if body.asset_id else None,
            brief_id=UUID(body.brief_id) if body.brief_id else None,
            category=body.category,
            asset_type=body.asset_type,
            tags=body.tags,
            source=body.source,
            confidence=body.confidence,
            success_count=body.success_count,
            failure_count=body.failure_count,
            created_by=body.created_by,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/knowledge/entries")
async def list_knowledge_entries(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    entry_type: str | None = None,
    category: str | None = None,
    asset_type: str | None = None,
    product_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List creative knowledge entries with optional filters."""
    try:
        return await creative_service.list_knowledge_entries(
            db,
            workspace_id=ws,
            entry_type=entry_type,
            category=category,
            asset_type=asset_type,
            product_id=UUID(product_id) if product_id else None,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/knowledge/learn-from-review", status_code=status.HTTP_200_OK)
async def learn_from_review(
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
    asset_id: str = ...,
    review_result: str = ...,
    review_reasons: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any] | None:
    """Extract knowledge from an asset review.

    Analyzes the review result and reasons to create knowledge entries
    that can improve future creative generation.
    """
    try:
        return await creative_service.learn_from_asset_review(
            db,
            workspace_id=ws,
            asset_id=UUID(asset_id),
            review_result=review_result,
            review_reasons=review_reasons,
            trace_id=trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/knowledge/summary")
async def get_learning_summary(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    category: str | None = None,
    asset_type: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Generate a learning summary from recent creative knowledge.

    Aggregates knowledge entries to provide insights for the Creative Agent.
    """
    return await creative_service.generate_learning_summary(
        db,
        workspace_id=ws,
        category=category,
        asset_type=asset_type,
        days=days,
    )


# ===================================================================
# Creative Calibration (C8)
# ===================================================================


class CalibrationRequest(BaseModel):
    """Request to run creative calibration."""

    days: int = Field(30, ge=1, le=365, description="Number of days to look back")
    trace_id: str | None = Field(None, max_length=64)


class CalibrationDecisionRequest(BaseModel):
    """Request to approve or reject a calibration run."""

    actor: str = Field(..., min_length=1, max_length=64)
    note: str | None = Field(None, max_length=500)
    trace_id: str | None = Field(None, max_length=64)


@router.post("/calibration/run", status_code=status.HTTP_201_CREATED)
async def run_calibration(
    body: CalibrationRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Run creative calibration: aggregate patterns from knowledge entries.

    Determines success/failure patterns from creative knowledge entries
    and proposes improvements. The run stays 'proposed' until human approval.
    """
    try:
        return await creative_service.run_calibration(
            db,
            workspace_id=ws,
            days=body.days,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/calibration/runs")
async def list_calibration_runs(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List creative calibration runs, newest first."""
    return await creative_service.list_calibration_runs(
        db,
        workspace_id=ws,
        status=status,
        limit=limit,
    )


@router.post("/calibration/runs/{run_id}/approve", status_code=status.HTTP_200_OK)
async def approve_calibration(
    run_id: UUID,
    body: CalibrationDecisionRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Approve a creative calibration proposal (human-only).

    Only a human can approve a calibration run. Once approved, the run's
    patterns can be used to improve creative generation strategies.
    """
    try:
        return await creative_service.approve_calibration(
            db,
            workspace_id=ws,
            run_id=run_id,
            actor=body.actor,
            note=body.note,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/calibration/runs/{run_id}/reject", status_code=status.HTTP_200_OK)
async def reject_calibration(
    run_id: UUID,
    body: CalibrationDecisionRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Reject a creative calibration proposal (human-only)."""
    try:
        return await creative_service.reject_calibration(
            db,
            workspace_id=ws,
            run_id=run_id,
            actor=body.actor,
            note=body.note,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ===================================================================
# Creative Cost Tracking (C9)
# ===================================================================


@router.get("/cost/summary")
async def get_cost_summary(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    year: int | None = None,
    month: int | None = None,
    asset_type: str | None = None,
    model: str | None = None,
    product_id: str | None = None,
    brief_id: str | None = None,
) -> dict[str, Any]:
    """Get comprehensive cost summary with breakdowns by model and asset type."""
    return await creative_service.get_cost_summary(
        db,
        workspace_id=ws,
        year=year,
        month=month,
        asset_type=asset_type,
        model=model,
        product_id=UUID(product_id) if product_id else None,
        brief_id=UUID(brief_id) if brief_id else None,
    )


@router.get("/cost/by-product/{product_id}")
async def get_cost_by_product(
    product_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    days: int = 30,
) -> dict[str, Any]:
    """Get cost breakdown for a specific product."""
    return await creative_service.get_cost_by_product(
        db,
        workspace_id=ws,
        product_id=product_id,
        days=days,
    )


@router.get("/cost/by-brief/{brief_id}")
async def get_cost_by_brief(
    brief_id: UUID,
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get cost breakdown for a specific brief."""
    return await creative_service.get_cost_by_brief(
        db,
        workspace_id=ws,
        brief_id=brief_id,
    )


@router.get("/cost/events")
async def list_cost_events(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
    asset_type: str | None = None,
    model: str | None = None,
    cost_category: str | None = None,
) -> list[dict[str, Any]]:
    """List recent cost events with optional filters."""
    return await creative_service.list_cost_events(
        db,
        workspace_id=ws,
        limit=limit,
        offset=offset,
        asset_type=asset_type,
        model=model,
        cost_category=cost_category,
    )


@router.get("/cost/budget-forecast")
async def get_budget_forecast(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    requested_cost: float = 0,
    budget: float | None = None,
) -> dict[str, Any]:
    """Check budget with cost forecasting.

    Projects future costs based on historical spending patterns.
    """
    from decimal import Decimal
    return await creative_service.check_budget_with_forecast(
        db,
        workspace_id=ws,
        requested_cost=Decimal(str(requested_cost)),
        budget=Decimal(str(budget)) if budget else None,
    )


# ===================================================================
# Creative Approval Queue (C10)
# ===================================================================


class CreateApprovalRequest(BaseModel):
    """Request to create a creative approval request."""

    request_type: str = Field(..., description="Type of request (high_cost_generation, batch_generation, etc.)")
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, description="Detailed description")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context data")
    risk_level: str = Field("medium", description="Risk level (low, medium, high)")
    estimated_cost: float | None = Field(None, ge=0, description="Estimated cost")
    asset_count: int = Field(1, ge=1, description="Number of assets involved")
    requested_by: str = Field("system", max_length=128)
    trace_id: str | None = Field(None, max_length=64)


class ApprovalDecisionRequest(BaseModel):
    """Request to approve or reject an approval request."""

    actor: str = Field(..., min_length=1, max_length=128)
    comment: str | None = Field(None, max_length=1000)
    trace_id: str | None = Field(None, max_length=64)


class ExecuteRequest(BaseModel):
    """Request to mark an approval request as executed."""

    execution_result: dict[str, Any] = Field(default_factory=dict, description="Execution result data")
    trace_id: str | None = Field(None, max_length=64)


@router.post("/approvals/requests", status_code=status.HTTP_201_CREATED)
async def create_approval_request(
    body: CreateApprovalRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create a creative approval request.

    Approval requests are created for high-risk operations that require
    human approval before execution.
    """
    from decimal import Decimal
    try:
        return await creative_service.create_approval_request(
            db,
            workspace_id=ws,
            request_type=body.request_type,
            title=body.title,
            description=body.description,
            context=body.context,
            risk_level=body.risk_level,
            estimated_cost=Decimal(str(body.estimated_cost)) if body.estimated_cost else None,
            asset_count=body.asset_count,
            requested_by=body.requested_by,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/approvals/requests")
async def list_approval_requests(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    status: str | None = None,
    request_type: str | None = None,
    risk_level: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List creative approval requests with optional filters."""
    return await creative_service.list_approval_requests(
        db,
        workspace_id=ws,
        status=status,
        request_type=request_type,
        risk_level=risk_level,
        limit=limit,
        offset=offset,
    )


@router.get("/approvals/queue-stats")
async def get_approval_queue_stats(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
) -> dict[str, Any]:
    """Get approval queue statistics."""
    return await creative_service.get_approval_queue_stats(
        db,
        workspace_id=ws,
    )


@router.post("/approvals/requests/{request_id}/approve", status_code=status.HTTP_200_OK)
async def approve_approval_request(
    request_id: UUID,
    body: ApprovalDecisionRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Approve a creative approval request (human-only)."""
    try:
        return await creative_service.approve_request(
            db,
            workspace_id=ws,
            request_id=request_id,
            actor=body.actor,
            comment=body.comment,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/approvals/requests/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_approval_request(
    request_id: UUID,
    body: ApprovalDecisionRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Reject a creative approval request (human-only)."""
    try:
        return await creative_service.reject_request(
            db,
            workspace_id=ws,
            request_id=request_id,
            actor=body.actor,
            comment=body.comment,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/approvals/requests/{request_id}/execute", status_code=status.HTTP_200_OK)
async def execute_approval_request(
    request_id: UUID,
    body: ExecuteRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Mark an approved request as executed."""
    try:
        return await creative_service.mark_executed(
            db,
            workspace_id=ws,
            request_id=request_id,
            execution_result=body.execution_result,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ===================================================================
# Creative Analytics & Reporting (C11)
# ===================================================================


@router.get("/analytics/dashboard")
async def get_dashboard_metrics(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    days: int = 30,
) -> dict[str, Any]:
    """Get comprehensive dashboard metrics for the Creative Studio.

    Returns metrics for assets, generation, cost, templates, knowledge,
    approvals, and briefs.
    """
    return await creative_service.get_dashboard_metrics(
        db,
        workspace_id=ws,
        days=days,
    )


@router.get("/analytics/performance")
async def get_performance_metrics(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    days: int = 30,
) -> dict[str, Any]:
    """Get performance metrics for the Creative Studio.

    Returns generation time, cost per asset, and review metrics.
    """
    return await creative_service.get_performance_metrics(
        db,
        workspace_id=ws,
        days=days,
    )


@router.get("/analytics/templates")
async def get_template_effectiveness(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Get template effectiveness metrics.

    Returns success rates, costs, and usage metrics for each template.
    """
    return await creative_service.get_template_effectiveness(
        db,
        workspace_id=ws,
        days=days,
    )


@router.get("/analytics/knowledge")
async def get_knowledge_growth(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    days: int = 30,
) -> dict[str, Any]:
    """Get knowledge base growth metrics.

    Returns growth rate, new entries, and breakdown by type.
    """
    return await creative_service.get_knowledge_growth(
        db,
        workspace_id=ws,
        days=days,
    )


# ===================================================================
# Creative Automation & Scheduling (C12)
# ===================================================================


class CreateWorkflowRequest(BaseModel):
    """Request to create an automation workflow."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    trigger_type: str = Field("manual", description="Trigger type: manual, schedule, event")
    trigger_config: dict[str, Any] = Field(default_factory=dict, description="Trigger configuration")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Workflow steps")
    enabled: bool = Field(True, description="Whether the workflow is enabled")
    created_by: str | None = Field(None, max_length=128)
    trace_id: str | None = Field(None, max_length=64)


class UpdateWorkflowRequest(BaseModel):
    """Request to update an automation workflow."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    trigger_type: str | None = Field(None, description="Trigger type: manual, schedule, event")
    trigger_config: dict[str, Any] | None = Field(None, description="Trigger configuration")
    steps: list[dict[str, Any]] | None = Field(None, description="Workflow steps")
    enabled: bool | None = Field(None, description="Whether the workflow is enabled")
    trace_id: str | None = Field(None, max_length=64)


class TriggerWorkflowRequest(BaseModel):
    """Request to trigger an automation workflow."""

    context: dict[str, Any] = Field(default_factory=dict, description="Optional context")
    trace_id: str | None = Field(None, max_length=64)


@router.post("/automation/workflows", status_code=status.HTTP_201_CREATED)
async def create_automation_workflow(
    body: CreateWorkflowRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Create an automation workflow for the Creative Studio."""
    result = await creative_service.create_automation_workflow(
        db,
        workspace_id=ws,
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config,
        steps=body.steps,
        enabled=body.enabled,
        created_by=body.created_by,
        trace_id=body.trace_id,
    )
    await db.commit()
    return result


@router.get("/automation/workflows")
async def list_automation_workflows(
    db: DbSession,
    ws: WorkspaceId,
    _user: CurrentUser,
    enabled: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List automation workflows."""
    return await creative_service.list_automation_workflows(
        db,
        workspace_id=ws,
        enabled=enabled,
        limit=limit,
        offset=offset,
    )


@router.patch("/automation/workflows/{workflow_id}", status_code=status.HTTP_200_OK)
async def update_automation_workflow(
    workflow_id: str,
    body: UpdateWorkflowRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Update an automation workflow."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "trace_id"}
    try:
        return await creative_service.update_automation_workflow(
            db,
            workspace_id=ws,
            workflow_id=workflow_id,
            updates=updates,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/automation/workflows/{workflow_id}/trigger", status_code=status.HTTP_200_OK)
async def trigger_automation_workflow(
    workflow_id: str,
    body: TriggerWorkflowRequest,
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
) -> dict[str, Any]:
    """Trigger an automation workflow."""
    try:
        return await creative_service.trigger_workflow(
            db,
            workspace_id=ws,
            workflow_id=workflow_id,
            context=body.context,
            trace_id=body.trace_id,
        )
    except CreativeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/automation/check-scheduled", status_code=status.HTTP_200_OK)
async def check_scheduled_workflows(
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Check for and run scheduled workflows.

    This endpoint should be called by a scheduler (e.g., cron job) to check
    for workflows that are due to run.
    """
    return await creative_service.run_scheduled_workflow_check(
        db,
        workspace_id=ws,
        trace_id=trace_id,
    )


@router.post("/automation/run-cost-monitor", status_code=status.HTTP_200_OK)
async def run_cost_monitoring(
    db: DbSession,
    ws: WorkspaceId,
    _user: OperatorRole,
    budget_threshold: float | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run cost monitoring and create approval requests if budget exceeded."""
    from decimal import Decimal
    return await creative_service.run_cost_monitoring(
        db,
        workspace_id=ws,
        budget_threshold=Decimal(str(budget_threshold)) if budget_threshold else None,
        trace_id=trace_id,
    )
