"""V3.0 Nuotao Score selection evaluation API.

Endpoints to run (single / batch) and read back the dual-track V3.0 evaluation:
six-dimension Nuotao Score, V1-V12 veto snapshot and funnel stage.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.product import Product
from app.models.product_intelligence import ProductNuotaoScore
from app.services.nuotao_selection_service import evaluate_product, evaluate_products

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/selection/nuotao", tags=["nuotao-selection"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class EvaluateRequest(BaseModel):
    product_id: str = Field(..., description="产品 ID（UUID）")


class BatchEvaluateRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1, max_length=500)


class LatestBatchRequest(BaseModel):
    product_ids: list[str] = Field(..., min_length=1, max_length=500)


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
