"""
选品数据录入 API 端点
支持人工录入、批量导入、AI 质检、产品评分
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sourcing_service import (
    ai_quality_check,
    batch_import_products,
    calculate_product_score,
    create_product_candidate,
    get_product_candidates,
    get_sourcing_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sourcing", tags=["sourcing"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# 请求/响应模型
# ============================================

class ProductCandidateRequest(BaseModel):
    """产品候选创建请求"""
    name: str = Field(..., description="产品名称", min_length=1, max_length=255)
    sku: str | None = Field(None, description="SKU 编码")
    description: str | None = Field(None, description="产品描述")
    category: str | None = Field(None, description="产品分类")
    brand: str | None = Field(None, description="品牌")
    retail_price: float | None = Field(None, description="零售价", gt=0)
    cost_price: float | None = Field(None, description="成本价", gt=0)
    weight: float | None = Field(None, description="重量（kg）", gt=0)
    currency: str = Field("USD", description="货币代码")
    source_type: str = Field("MANUAL", description="来源类型：1688/MANUAL/CSV/OTHER")
    source_url: str | None = Field(None, description="来源 URL")
    purchase_cost: float | None = Field(None, description="采购成本")
    domestic_shipping: float | None = Field(None, description="国内运费")
    first_leg_shipping: float | None = Field(None, description="头程运费")
    last_leg_shipping: float | None = Field(None, description="尾程运费")


class BatchImportRequest(BaseModel):
    """批量导入请求"""
    products: list[dict[str, Any]] = Field(..., description="产品数据列表")
    source_type: str = Field("CSV", description="来源类型")


class ProductScoreRequest(BaseModel):
    """产品评分请求"""
    product_id: str = Field(..., description="产品 ID（UUID）")
    profit: float | None = Field(None, description="利润评分（0-10）", ge=0, le=10)
    logistics: float | None = Field(None, description="物流评分（0-10）", ge=0, le=10)
    demand: float | None = Field(None, description="需求评分（0-10）", ge=0, le=10)
    competition: float | None = Field(None, description="竞争评分（0-10）", ge=0, le=10)
    differentiation: float | None = Field(None, description="差异化评分（0-10）", ge=0, le=10)
    compliance: float | None = Field(None, description="合规评分（0-10）", ge=0, le=10)


class QualityCheckRequest(BaseModel):
    """质检请求"""
    product_data: dict[str, Any] = Field(..., description="产品数据")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取选品系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取选品系统状态和配置"""
    return get_sourcing_status()


@router.post(
    "/candidates",
    summary="创建产品候选（人工录入）",
)
async def create_candidate(
    request: ProductCandidateRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    创建产品候选（人工录入）

    支持录入产品基本信息、价格、成本、物流费用等。
    创建后自动记录产品来源和成本快照。
    """
    try:
        product_data = request.model_dump(exclude_none=True)
        source_type = product_data.pop("source_type", "MANUAL")
        source_url = product_data.pop("source_url", None)

        product, product_source = await create_product_candidate(
            session=db,
            product_data=product_data,
            source_type=source_type,
            source_url=source_url,
        )
        await db.commit()

        return {
            "success": True,
            "product": {
                "id": str(product.id),
                "name": product.name,
                "sku": product.sku,
                "status": product.status,
                "category": product.category,
            },
            "source": {
                "id": str(product_source.id),
                "type": product_source.source_type,
                "url": product_source.source_url,
            },
        }
    except Exception as e:
        await db.rollback()
        logger.exception("Create product candidate failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create product candidate failed: {e!s}",
        )


@router.post(
    "/batch-import",
    summary="批量导入产品",
)
async def batch_import(
    request: BatchImportRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    批量导入产品

    支持 CSV/JSON 格式的批量产品数据导入。
    每个产品独立处理，失败的产品会记录错误信息，不影响其他产品导入。
    """
    try:
        result = await batch_import_products(
            session=db,
            products_data=request.products,
            source_type=request.source_type,
        )
        await db.commit()
        return result
    except Exception as e:
        await db.rollback()
        logger.exception("Batch import failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch import failed: {e!s}",
        )


@router.post(
    "/quality-check",
    summary="AI 结构化分析质检",
)
async def quality_check(
    request: QualityCheckRequest,
) -> dict[str, Any]:
    """
    AI 结构化分析质检

    检查产品数据的完整性、格式正确性、价格合理性、潜在问题。
    返回质检分数、问题列表、警告列表。
    """
    try:
        result = await ai_quality_check(request.product_data)
        return result
    except Exception as e:
        logger.exception("Quality check failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quality check failed: {e!s}",
        )


@router.post(
    "/score",
    summary="计算产品评分",
)
async def calculate_score(
    request: ProductScoreRequest,
    db: DbSession,
) -> dict[str, Any]:
    """
    计算产品评分（6 维度，0-100 分）

    评分维度及权重：
    - 利润 (30%)
    - 物流 (20%)
    - 需求 (15%)
    - 竞争 (10%)
    - 差异化 (15%)
    - 合规 (10%)
    """
    try:
        from uuid import UUID as _UUID

        product_id = _UUID(request.product_id)
        score_data = request.model_dump(exclude={"product_id"}, exclude_none=True)

        product_score = await calculate_product_score(
            session=db,
            product_id=product_id,
            score_data=score_data if score_data else None,
        )
        await db.commit()

        return {
            "success": True,
            "product_id": str(product_id),
            "score": {
                "profit": float(product_score.profit),
                "logistics": float(product_score.logistics),
                "demand": float(product_score.demand),
                "competition": float(product_score.competition),
                "differentiation": float(product_score.differentiation),
                "compliance": float(product_score.compliance),
                "total": float(product_score.total),
            },
            "model_version": product_score.model_version,
            "rule_version": product_score.rule_version,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Calculate product score failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculate product score failed: {e!s}",
        )


@router.get(
    "/candidates",
    summary="获取产品候选列表",
)
async def list_candidates(
    db: DbSession,
    status: str | None = "candidate",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    获取产品候选列表

    支持按状态筛选（candidate/approved/testing/winner/rejected），
    支持分页。
    """
    try:
        result = await get_product_candidates(
            session=db,
            status=status,
            limit=limit,
            offset=offset,
        )
        return result
    except Exception as e:
        logger.exception("List product candidates failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List product candidates failed: {e!s}",
        )
