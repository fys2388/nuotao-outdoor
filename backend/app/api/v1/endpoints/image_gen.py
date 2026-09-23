"""Image generation API endpoints (M6).

Routes:
- GET  /api/v1/image-gen/status          — service status + available models
- GET  /api/v1/image-gen/models          — list available models with pricing
- POST /api/v1/image-gen/generate        — generate an image (create + execute)
- POST /api/v1/image-gen/batch-generate  — generate N images in one round trip
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
from app.core.workspace import get_workspace_id
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
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


# ============================================
# Request / Response models
# ============================================


class GenerateImageRequest(BaseModel):
    """Request to generate an image."""

    prompt: str = Field(..., description="Text prompt for image generation", min_length=1, max_length=4000)
    negative_prompt: str | None = Field(None, description="Negative prompt", max_length=2000)
    product_id: str | None = Field(None, description="Associated product ID (UUID)")
    use_case: str = Field("main_image", description="Image use case: main_image/detail_image/lifestyle_image/marketing_image/variant_image")
    model: str = Field(image_gen_gateway.DEFAULT_MODEL, description="Model to use (defaults to Seedream 5.0 pro)")
    width: int = Field(1024, description="Image width in pixels", ge=256, le=2048)
    height: int = Field(1024, description="Image height in pixels", ge=256, le=2048)
    reference_image: str | None = Field(
        None,
        description="Source image URL for image-to-image (pass the 1688 original to keep the product faithful)",
        max_length=2048,
    )


class BatchGenerateImageRequest(BaseModel):
    """Request to generate a batch of images for a product listing.

    The image gate requires 5 main + 6 detail images; this endpoint generates
    ``count`` images in one round trip, each with an optional per-variant prompt
    suffix so main-image directions (white-bg / scene / promo) or detail-page
    sections get distinct prompts.

    When ``reference_image`` is provided every variant is generated via
    image-to-image from the same source (Nuotao standard: reproduce the 1688
    original product). I2I never silently degrades to a mock placeholder.
    """

    prompt: str = Field(..., description="Base text prompt", min_length=1, max_length=4000)
    count: int = Field(..., description="Number of images to generate (1-12)", ge=1, le=12)
    variants: list[str] | None = Field(
        None,
        description="Optional per-variant prompt suffixes. If shorter than count, the last is reused.",
    )
    negative_prompt: str | None = Field(None, description="Negative prompt", max_length=2000)
    product_id: str | None = Field(None, description="Associated product ID (UUID)")
    use_case: str = Field("main_image", description="Image use case")
    model: str = Field(image_gen_gateway.DEFAULT_MODEL, description="Model to use")
    width: int = Field(1024, ge=256, le=2048)
    height: int = Field(1024, ge=256, le=2048)
    reference_image: str | None = Field(
        None,
        description="Source image URL for image-to-image (the 1688 original)",
        max_length=2048,
    )


class CreateTaskRequest(BaseModel):
    """Request to create a pending task (without executing)."""

    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str | None = Field(None, max_length=2000)
    product_id: str | None = None
    use_case: str = "main_image"
    model: str = image_gen_gateway.DEFAULT_MODEL
    width: int = 1024
    height: int = 1024
    reference_image: str | None = Field(None, max_length=2048)


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


def _mock_warning(result: dict[str, Any] | None) -> dict[str, str] | None:
    """Build a warning when the gateway degraded to a mock placeholder."""
    if isinstance(result, dict) and result.get("actual_model") == "mock":
        return {
            "warning": (
                "当前未配置真实生图模型（VOLCENGINE_API_KEY / DASHSCOPE_API_KEY 缺失），"
                "本次仅生成 mock 占位图，不可用于上架。请在后端 .env 配置生图 API Key 后重试。"
            ),
            "mock": "true",
        }
    return None


@router.post("/generate", summary="Generate an image (create + execute)")
async def generate_image(
    request: GenerateImageRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Generate an image immediately. Creates a task and executes it.

    High-cost models (>¥0.15/img) will be flagged for approval but still
    generated; the image cannot be published until approved.
    """
    try:
        product_id = UUID(request.product_id) if request.product_id else None
        task = await generate_image_and_save(
            db,
            workspace_id=workspace_id,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            product_id=product_id,
            use_case=request.use_case,
            model=request.model,
            width=request.width,
            height=request.height,
            reference_image=request.reference_image,
        )
        await db.commit()

        result = await get_task(db, task_id=task.id, workspace_id=workspace_id)
        response: dict[str, Any] = {"success": True, "task": result}
        warning = _mock_warning(result)
        if warning:
            response["warning"] = warning["warning"]
            response["mock"] = True
        return response
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Generate image failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Generate image failed: {e!s}") from None


@router.post("/batch-generate", summary="Batch generate images for a product listing")
async def batch_generate_images(
    request: BatchGenerateImageRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Generate ``count`` images in one round trip.

    Each image gets its own task row and its own prompt (base prompt + optional
    per-variant suffix). A single variant failure does NOT abort the batch —
    the response includes per-image success/failure so the frontend can show
    partial progress and retry only the failed ones.
    """
    import asyncio

    product_id = UUID(request.product_id) if request.product_id else None
    tasks: list[dict[str, Any]] = []
    success_count = 0
    fail_count = 0

    for i in range(request.count):
        variant_suffix = ""
        if request.variants:
            idx = min(i, len(request.variants) - 1)
            variant_suffix = request.variants[idx].strip()
        prompt = f"{request.prompt} {variant_suffix}".strip() if variant_suffix else request.prompt

        try:
            task = await generate_image_and_save(
                db,
                workspace_id=workspace_id,
                prompt=prompt,
                negative_prompt=request.negative_prompt,
                product_id=product_id,
                use_case=request.use_case,
                model=request.model,
                width=request.width,
                height=request.height,
                reference_image=request.reference_image,
            )
            await db.commit()
            result = await get_task(db, task_id=task.id, workspace_id=workspace_id)
            item: dict[str, Any] = {"index": i, "success": True, "task": result, "prompt": prompt}
            if isinstance(result, dict) and result.get("actual_model") == "mock":
                item["mock"] = True
            tasks.append(item)
            success_count += 1
        except Exception as e:  # noqa: BLE001 — per-image failure must not abort the batch
            await db.rollback()
            tasks.append({
                "index": i,
                "success": False,
                "prompt": prompt,
                "error": str(e),
            })
            fail_count += 1
            logger.warning("Batch image gen variant %d/%d failed: %s", i + 1, request.count, e)

        # Small delay to respect API rate limits.
        if i < request.count - 1:
            await asyncio.sleep(0.3)

    response: dict[str, Any] = {
        "success": success_count > 0,
        "requested": request.count,
        "succeeded": success_count,
        "failed": fail_count,
        "tasks": tasks,
    }
    if success_count > 0 and all(t.get("mock") for t in tasks if t.get("success")):
        response["mock"] = True
        response["warning"] = (
            "所有图片均为 mock 占位图，不可用于上架。请检查后端 .env 是否配置了 "
            "VOLCENGINE_API_KEY 或 DASHSCOPE_API_KEY。"
        )
    return response


@router.post("/tasks", summary="Create a pending image generation task")
async def create_task(
    request: CreateTaskRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Create a pending task without executing it. Use /tasks/{id}/execute to run."""
    try:
        product_id = UUID(request.product_id) if request.product_id else None
        task = await create_generation_task(
            db,
            workspace_id=workspace_id,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            product_id=product_id,
            use_case=request.use_case,
            model=request.model,
            width=request.width,
            height=request.height,
            reference_image=request.reference_image,
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
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Execute a pending task. Calls the image generation API and persists the result."""
    try:
        task = await execute_generation_task(
            db,
            task_id=UUID(task_id),
            workspace_id=workspace_id,
        )
        await db.commit()
        result = await get_task(db, task_id=task.id, workspace_id=workspace_id)
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
    workspace_id: WorkspaceId,
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
            workspace_id=workspace_id,
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
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Get a single task by ID."""
    result = await get_task(db, task_id=UUID(task_id), workspace_id=workspace_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found") from None
    return result


@router.post("/tasks/{task_id}/approve", summary="Approve a generated image for production use")
async def approve_generated_image(
    task_id: str,
    request: ApprovalRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Approve a generated image (human-in-the-loop gate)."""
    try:
        task = await approve_image(
            db,
            task_id=UUID(task_id),
            approved_by=request.approved_by,
            workspace_id=workspace_id,
        )
        await db.commit()
        result = await get_task(db, task_id=task.id, workspace_id=workspace_id)
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
    workspace_id: WorkspaceId,
) -> dict[str, Any]:
    """Reject a generated image."""
    try:
        task = await reject_image(db, task_id=UUID(task_id), workspace_id=workspace_id)
        await db.commit()
        result = await get_task(db, task_id=task.id, workspace_id=workspace_id)
        return {"success": True, "task": result}
    except ImageGenServiceError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except Exception as e:
        await db.rollback()
        logger.exception("Reject image failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Reject image failed: {e!s}") from None


# ============================================
# BUG #20: Local image download endpoint
# ============================================
# When OSS is not configured, generated images are stored locally under
# IMAGE_STORAGE_DIR. This endpoint serves them as a static file so the
# frontend and WooCommerce can reference a public URL instead of an
# inaccessible local path.

from fastapi.responses import FileResponse  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402


@router.get("/download/{image_id}", summary="Download a locally-generated image")
async def download_local_image(image_id: str):
    """Serve a locally-generated image by task ID.

    BUG #20: fallback when OSS/CDN is not configured. The frontend can
    build a public URL like ``/api/v1/image-gen/download/{task_id}`` and
    WooCommerce can consume it directly.

    ``image_id`` is the task UUID (the filename on disk). The response is
    streamed with the correct Content-Type based on the file extension.
    """
    # Resolve storage dir from settings (matches image_generation_service)
    from app.core.config import get_settings
    storage_dir = Path(get_settings().image_gen_storage_dir)

    # Resolve the actual file path safely (no traversal)
    safe_name = str(image_id).strip()
    if not safe_name or ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise HTTPException(status_code=400, detail="Invalid image ID")

    # Try common extensions (file on disk is stored as {task_id}{ext})
    candidate = None
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
        c = storage_dir / (safe_name + ext)
        if c.is_file():
            candidate = c
            break

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Image not found: {image_id}")

    content_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".gif": "image/gif",
    }.get(candidate.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path=str(candidate),
        media_type=content_type,
        filename=candidate.name,
    )
