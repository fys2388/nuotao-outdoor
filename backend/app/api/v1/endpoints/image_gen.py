"""Image generation API endpoints (M6).

Routes:
- GET  /api/v1/image-gen/status          — service status + available models
- GET  /api/v1/image-gen/models          — list available models with pricing
- POST /api/v1/image-gen/generate        — generate an image (create + execute)
- POST /api/v1/image-gen/tasks           — create a pending task
- POST /api/v1/image-gen/tasks/{id}/execute — execute a pending task
- GET  /api/v1/image-gen/tasks           — list tasks
- GET  /api/v1/image-gen/tasks/{id}      — get task detail
- POST /api/v1/image-gen/tasks/{id}/approve — approve a generated image
- POST /api/v1/image-gen/tasks/{id}/reject  — reject a generated image
"""
from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.integrations import image_gen as image_gen_gateway
from app.services.image_generation_service import (
    ImageGenServiceError,
    approve_image,
    create_generation_task,
    execute_generation_task,
    generate_image_and_save,
    get_image_gen_status,
    get_task,
    list_tasks,
    reject_image,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/image-gen", tags=["image_generation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# Request / Response models
# ============================================


class GenerateImageRequest(BaseModel):
    """Request to generate an image."""
    prompt: str = Field(..., description="Text prompt for image generation", min_length=1, max_length=4000)
    negative_prompt: str | None = Field(None, description="Negative prompt", max_length=2000)
    product_id: str | None = Field(None, description="Associated product ID (UUID)")
    use_case: str = Field("main_image", description="Image use case: main_image/detail_image/lifestyle_image/marketing_image/variant_image")
    model: str = Field("wan2.7-image", description="Model to use (defaults to wan2.7-image)")
    width: int = Field(1024, description="Image width in pixels", ge=256, le=2048)
    height: int = Field(1024, description="Image height in pixels", ge=256, le=2048)


class CreateTaskRequest(BaseModel):
    """Request to create a pending task (without executing)."""
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str | None = Field(None, max_length=2000)
    product_id: str | None = None
    use_case: str = "main_image"
    model: str = "wan2.7-image"
    width: int = 1024
    height: int = 1024


class ApprovalRequest(BaseModel):
    """Approval request."""
    approved_by: str = Field("admin", description="Approver identifier")


# ============================================
# API endpoints
# ============================================


@router.get("/status", summary="Get image generation service status")
async def get_status() -> dict[str, Any]:
    """Return service status, available models, and budget configuration."""
    return get_image_gen_status()


@router.get("/models", summary="List available image generation models")
async def list_models() -> dict[str, Any]:
    """List all supported models with pricing and quality info."""
    return {"models": image_gen_gateway.list_available_models()}


@router.post("/generate", summary="Generate an image (create + execute)")
async def generate_image(
    request: GenerateImageRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Generate an image immediately. Creates a task and executes it.

    High-cost models (>¥0.15/img) will be flagged for approval but still
    generated; the image cannot be published until approved.
    """
    try:
        product_id = UUID(request.product_id) if request.product_id else None
        task = await generate_image_and_save(
            db,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            product_id=product_id,
            use_case=request.use_case,
            model=request.model,
            width=request.width,
            height=request.height,
        )
        await db.commit()

        result = await get_task(db, task_id=task.id)
        return {"success": True, "task": result}
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Generate image failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Generate image failed: {e!s}") from None


@router.post("/tasks", summary="Create a pending image generation task")
async def create_task(
    request: CreateTaskRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Create a pending task without executing it. Use /tasks/{id}/execute to run."""
    try:
        product_id = UUID(request.product_id) if request.product_id else None
        task = await create_generation_task(
            db,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            product_id=product_id,
            use_case=request.use_case,
            model=request.model,
            width=request.width,
            height=request.height,
        )
        await db.commit()
        return {"success": True, "task_id": str(task.id), "status": task.status}
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Create task failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Create task failed: {e!s}") from None


@router.post("/tasks/{task_id}/execute", summary="Execute a pending image generation task")
async def execute_task(
    task_id: str,
    db: DbSession,
) -> dict[str, Any]:
    """Execute a pending task. Calls the image generation API and persists the result."""
    try:
        task = await execute_generation_task(db, task_id=UUID(task_id))
        await db.commit()
        result = await get_task(db, task_id=task.id)
        return {"success": True, "task": result}
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Execute task failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Execute task failed: {e!s}") from None


@router.get("/tasks", summary="List image generation tasks")
async def list_image_tasks(
    db: DbSession,
    status_filter: str | None = None,
    use_case: str | None = None,
    product_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List image generation tasks with optional filters."""
    try:
        pid = UUID(product_id) if product_id else None
        return await list_tasks(
            db,
            status=status_filter,
            use_case=use_case,
            product_id=pid,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception("List tasks failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"List tasks failed: {e!s}") from None


@router.get("/tasks/{task_id}", summary="Get image generation task detail")
async def get_task_detail(
    task_id: str,
    db: DbSession,
) -> dict[str, Any]:
    """Get a single task by ID."""
    result = await get_task(db, task_id=UUID(task_id))
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from None
    return result


@router.post("/tasks/{task_id}/approve", summary="Approve a generated image for production use")
async def approve_generated_image(
    task_id: str,
    request: ApprovalRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Approve a generated image (human-in-the-loop gate)."""
    try:
        task = await approve_image(db, task_id=UUID(task_id), approved_by=request.approved_by)
        await db.commit()
        result = await get_task(db, task_id=task.id)
        return {"success": True, "task": result}
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Approve image failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Approve image failed: {e!s}") from None


@router.post("/tasks/{task_id}/reject", summary="Reject a generated image")
async def reject_generated_image(
    task_id: str,
    db: DbSession,
) -> dict[str, Any]:
    """Reject a generated image."""
    try:
        task = await reject_image(db, task_id=UUID(task_id))
        await db.commit()
        result = await get_task(db, task_id=task.id)
        return {"success": True, "task": result}
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Reject image failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Reject image failed: {e!s}") from None
