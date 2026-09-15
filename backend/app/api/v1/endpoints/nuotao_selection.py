"""V3.0 Nuotao Score selection evaluation API.

Endpoints to run (single / batch) and read back the dual-track V3.0 evaluation:
six-dimension Nuotao Score, V1-V12 veto snapshot and funnel stage.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.product import Product
from app.models.product_intelligence import ProductNuotaoScore
from app.services.nuotao_selection_service import (
    build_product_report,
    evaluate_product,
    evaluate_products,
    get_public_badge,
)
from app.services.nuotao_test_loop import (
    promote_to_hero,
    record_test_result,
    start_market_test,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/selection/nuotao", tags=["nuotao-selection"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class EvaluateRequest(BaseModel):
    product_id: str = Field(..., description="产品 ID（UUID）")


class BatchEvaluateRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1, max_length=500)


class LatestBatchRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1, max_length=500)


class StartTestRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=64)
    plan: dict | None = None


class TestResultRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=64)
    actual: dict = Field(default_factory=dict)
    success: bool | None = None
    note: str | None = Field(default=None, max_length=1000)


class PromoteHeroRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)
    force: bool = False


def _serialize_score(record: ProductNuotaoScore) -> dict:
    return {
        "score_id": str(record.id),
        "product_id": str(record.product_id),
        "nuotao_total": float(record.total),
        "grade": record.grade,
        "dimensions": {
            "value": float(record.value_score),
            "utility": float(record.utility_score),
            "weight_packability": float(record.weight_packability_score),
            "durability": float(record.durability_score),
            "brand_fit": float(record.brand_fit_score),
            "differentiation": float(record.differentiation_score),
        },
        "reject_reasons": record.reject_reasons,
        "dimension_evidence": record.dimension_evidence,
        "model_version": record.model_version,
        "rule_version": record.rule_version,
        "scored_at": record.scored_at.isoformat() if record.scored_at else None,
    }


@router.post("/evaluate", summary="对单个产品执行 V3.0 Nuotao 评分与否决评估")
async def run_evaluate(request: EvaluateRequest, db: DbSession):
    try:
        product_id = UUID(request.product_id)
        result = await evaluate_product(db, product_id)
        await db.commit()
        return {"success": True, "evaluation": result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("Nuotao V3 evaluate failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/evaluate-batch", summary="批量执行 V3.0 评估")
async def run_evaluate_batch(request: BatchEvaluateRequest, db: DbSession):
    try:
        product_ids = [UUID(pid) for pid in request.product_ids]
        result = await evaluate_products(db, product_ids)
        await db.commit()
        return {"success": True, **result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("Nuotao V3 batch evaluate failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.get("/public-badge", summary="B2C 前台 Nuotao 徽章（仅 Core/Hero，字段白名单）")
async def get_public_badge_endpoint(
    db: DbSession,
    product_id: UUID | None = Query(default=None),
    sku: str | None = Query(default=None, max_length=128),
):
    if product_id is None and not sku:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_id or sku is required",
        )
    return await get_public_badge(db, product_id=product_id, sku=sku)


@router.get("/{product_id}/latest", summary="读取产品最新 V3.0 评分与漏斗阶段")
async def get_latest(product_id: UUID, db: DbSession):
    product = await db.get(Product, product_id)
    record = (
        (
            await db.execute(
                select(ProductNuotaoScore)
                .where(ProductNuotaoScore.product_id == product_id)
                .order_by(ProductNuotaoScore.scored_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    return {
        "product_id": str(product_id),
        "exists": product is not None,
        "funnel_stage": product.funnel_stage if product else None,
        "product_reject_reasons": product.reject_reasons if product else None,
        "latest": _serialize_score(record) if record else None,
    }


@router.post("/latest-batch", summary="批量读取最新 V3.0 评分")
async def get_latest_batch(request: LatestBatchRequest, db: DbSession):
    product_ids = [UUID(pid) for pid in request.product_ids]
    rows = (
        await db.execute(
            select(ProductNuotaoScore)
            .where(ProductNuotaoScore.product_id.in_(product_ids))
            .order_by(ProductNuotaoScore.scored_at.asc())
        )
    ).scalars().all()
    stage_rows = (
        await db.execute(
            select(Product.id, Product.funnel_stage).where(Product.id.in_(product_ids))
        )
    ).all()
    stage_map = {str(pid): stage for pid, stage in stage_rows}
    # Ascending order + overwrite leaves the newest row per product.
    latest: dict[str, dict] = {}
    for record in rows:
        key = str(record.product_id)
        latest[key] = {
            **_serialize_score(record),
            "funnel_stage": stage_map.get(key),
        }
    return {"success": True, "items": latest}


@router.get("/{product_id}/report", summary="生成产品 V3.0 选品报告（结构化）")
async def get_product_report(product_id: UUID, db: DbSession):
    try:
        report = await build_product_report(db, product_id)
        return {"success": True, "report": report}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Nuotao V3 report failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/{product_id}/test/start", summary="人工批准并启动小批量测试（8→3）")
async def post_start_test(product_id: UUID, request: StartTestRequest, db: DbSession):
    try:
        result = await start_market_test(
            db, product_id, actor=request.actor, plan=request.plan
        )
        await db.commit()
        return {"success": True, **result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("start market test failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/{product_id}/test/result", summary="回填小批量测试 KPI 结果（3→1-2）")
async def post_test_result(product_id: UUID, request: TestResultRequest, db: DbSession):
    try:
        result = await record_test_result(
            db,
            product_id,
            actor=request.actor,
            actual=request.actual,
            success=request.success,
            note=request.note,
        )
        await db.commit()
        return {"success": True, **result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("record test result failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc


@router.post("/{product_id}/promote-hero", summary="人工终审提名 Hero（最终 1-2）")
async def post_promote_hero(product_id: UUID, request: PromoteHeroRequest, db: DbSession):
    try:
        result = await promote_to_hero(
            db,
            product_id,
            actor=request.actor,
            comment=request.comment,
            force=request.force,
        )
        await db.commit()
        return {"success": True, **result}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.exception("promote to hero failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
