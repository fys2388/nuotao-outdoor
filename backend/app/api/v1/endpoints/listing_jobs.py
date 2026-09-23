"""SOP 阶段 ③「上架工单」—— API endpoint for ListingJob lifecycle.

提供：
- POST /listing-jobs           提交上架工单（pending）
- GET  /listing-jobs           列工单（可按 status 过滤）
- GET  /listing-jobs/{id}      查看工单详情
- POST /listing-jobs/{id}/review   人工终审（approve / reject）
- POST /listing-jobs/{id}/push     触发 WC 推送
- POST /listing-jobs/{id}/retry    重试失败的推送

路由前缀：/listing-jobs（挂在 api_router 根下）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import get_current_user, get_current_workspace_id
from app.api.v1.endpoints.listing_publish import (
    push_product_to_woocommerce_gated,
)
from app.core.database import get_db
from app.models.listing_job import ListingJob
from app.models.product import Product
from app.schemas.user import UserResponse

router = APIRouter(prefix="/listing-jobs", tags=["listing-jobs"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[UserResponse, Depends(get_current_user)]
WorkspaceId = Annotated[UUID, Depends(get_current_workspace_id)]


def _job_to_dict(job: ListingJob) -> dict[str, Any]:
    return job.to_dict()


@router.get("", summary="列上架工单")
async def list_listing_jobs(
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: CurrentUser,
    status: str | None = Query(default=None, description="按 status 过滤"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """按状态列出工单，最新在前。"""
    stmt = (
        select(ListingJob)
        .where(ListingJob.workspace_id == workspace_id)
        .order_by(ListingJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(ListingJob.status == status)
    rows = (await db.execute(stmt)).scalars().all()

    stmt_stats = (
        select(ListingJob.status, func.count())
        .where(ListingJob.workspace_id == workspace_id)
        .group_by(ListingJob.status)
    )
    stats_rows = await db.execute(stmt_stats)
    stats: dict[str, int] = {r[0]: r[1] for r in stats_rows.all()}

    return {
        "data": [_job_to_dict(j) for j in rows],
        "stats": stats,
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.post("", summary="提交上架工单", status_code=201)
async def create_listing_job(
    body: dict[str, Any],
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: CurrentUser,
):
    """提交一个上架工单（默认 pending）。

    body:
      product_id: UUID 必填
      payload: object 必填（完整 WC payload 快照）
      note: str 可选
      submitted_by: str 可选（默认 "pipeline"）
      trace_id: str 可选
    """
    product_id_raw = body.get("product_id")
    if not product_id_raw:
        raise HTTPException(status_code=422, detail="缺少 product_id")
    try:
        product_uuid = _parse_uuid(product_id_raw, "product_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    payload = body.get("payload")
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=422, detail="payload 必须是对象")

    product = (
        await db.execute(
            select(Product).where(
                Product.id == product_uuid,
                Product.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    active_stmt = (
        select(ListingJob.id)
        .where(
            ListingJob.workspace_id == workspace_id,
            ListingJob.product_id == product_uuid,
            or_(
                ListingJob.status == "pending",
                ListingJob.status == "approved",
                ListingJob.status == "processing",
            ),
        )
        .limit(1)
    )
    active = (await db.execute(active_stmt)).scalar_one_or_none()
    if active is not None:
        raise HTTPException(status_code=409, detail=f"该商品已有活跃工单 {active}")

    job = ListingJob(
        workspace_id=workspace_id,
        product_id=product_uuid,
        sku=product.sku or "",
        name=product.name or "",
        payload=payload,
        status="pending",
        note=body.get("note"),
        submitted_by=body.get("submitted_by") or _user.get("username") or "pipeline",
        submitted_at=datetime.now(timezone.utc),
        trace_id=body.get("trace_id"),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


@router.get("/{job_id}", summary="查看工单详情")
async def get_listing_job(
    job_id: str,
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: CurrentUser,
):
    job = await _load_job(db, job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    return _job_to_dict(job)


@router.post("/{job_id}/review", summary="人工终审")
async def review_listing_job(
    job_id: str,
    body: dict[str, Any],
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: CurrentUser,
):
    """approve → status=approved；reject → status=rejected。

    body:
      decision: "approve" | "reject" 必填
      reviewer: str 可选
      note: str 可选
      reject_reasons: list 可选
    """
    job = await _load_job(db, job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="工单不存在")

    decision = (body.get("decision") or "").lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="decision 必须是 approve 或 reject")
    if job.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"工单当前状态为 {job.status}，仅 pending 可终审"
        )

    reviewer = body.get("reviewer") or _user.get("username") or "system:reviewer"
    job.status = "approved" if decision == "approve" else "rejected"
    job.reviewed_by = reviewer
    job.reviewed_at = datetime.now(timezone.utc)
    if body.get("note"):
        job.note = body.get("note")
    if decision == "reject" and isinstance(body.get("reject_reasons"), list):
        job.reject_reasons = body.get("reject_reasons")

    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


@router.post("/{job_id}/push", summary="触发 WC 推送")
async def push_listing_job(
    job_id: str,
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: CurrentUser,
):
    """将 approved 工单送入 WC 推送。"""
    job = await _load_job(db, job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="工单不存在")

    if job.status != "approved":
        raise HTTPException(
            status_code=409, detail=f"工单状态为 {job.status}，仅 approved 可推送"
        )

    job.status = "processing"
    job.pushed_at = datetime.now(timezone.utc)
    job.retry_count = (job.retry_count or 0) + 1
    await db.commit()
    await db.refresh(job)

    try:
        result = await push_product_to_woocommerce_gated(
            product_id=str(job.product_id),
            force=False,
        )
    except HTTPException as exc:
        job.status = "failed"
        job.wc_verify_status = "error"
        job.wc_verify_detail = str(getattr(exc, "detail", exc))[:2000]
        await db.commit()
        await db.refresh(job)
        return _job_to_dict(job)
    except Exception as exc:
        job.status = "failed"
        job.wc_verify_status = "error"
        job.wc_verify_detail = f"推送异常: {type(exc).__name__}: {exc}"[:2000]
        await db.commit()
        await db.refresh(job)
        return _job_to_dict(job)

    ok = bool(result and result.get("success"))
    job.wc_verify_status = "ok" if ok else "failed"
    job.wc_verify_detail = str(result)[:2000] if result else "无返回"
    if ok and isinstance(result.get("woocommerce_id"), int):
        job.wc_product_id = result.get("woocommerce_id")
        job.status = "published"
        job.published_at = datetime.now(timezone.utc)
    else:
        job.status = "failed"

    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


@router.post("/{job_id}/retry", summary="重试失败推送")
async def retry_listing_job(
    job_id: str,
    db: DBSession,
    workspace_id: WorkspaceId,
    _user: CurrentUser,
):
    """对 failed 工单发起重试（status → processing）。"""
    job = await _load_job(db, job_id, workspace_id)
    if job is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    if job.status not in ("failed", "rejected"):
        raise HTTPException(
            status_code=409, detail=f"工单状态为 {job.status}，仅 failed/rejected 可重试"
        )
    job.status = "approved"
    job.reviewed_by = _user.get("username") or "system:retry"
    job.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return await push_listing_job(job_id, db=db, workspace_id=workspace_id, _user=_user)


async def _load_job(db: AsyncSession, job_id: str, workspace_id: UUID) -> ListingJob | None:
    try:
        uid = _parse_uuid(job_id, "job_id")
    except ValueError:
        return None
    return (
        await db.execute(
            select(ListingJob).where(
                ListingJob.id == uid,
                ListingJob.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()


def _parse_uuid(s: str, field: str) -> UUID:
    try:
        return UUID(str(s))
    except (ValueError, TypeError):
        raise ValueError(f"{field} 不是合法 UUID: {s}")
