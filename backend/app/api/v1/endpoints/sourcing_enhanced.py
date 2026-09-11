"""
选品增强 API 端点
包含：1688 API 集成、竞品分析、市场趋势、选品评测、自动化实验
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.competitor_analysis_service import (
    analyze_competitors,
    analyze_reviews,
    compare_pricing,
)
from app.services.experiment_automation_service import (
    auto_manage_experiment,
    create_experiment,
    evaluate_experiment,
    record_experiment_data,
    start_experiment,
)
from app.services.market_trend_service import (
    analyze_market_trend,
    compare_category_trends,
    get_hot_keywords,
)
from app.services.sourcing_1688_service import (
    get_price_trend,
    get_product_detail,
    get_supplier_info,
    is_configured,
    search_products,
)
from app.services.sourcing_evaluation_service import (
    get_evaluation_status,
    run_evaluation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sourcing", tags=["sourcing_enhanced"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================
# B1: 1688 API 集成
# ============================================

@router.get("/1688/status")
async def api_1688_status() -> dict[str, Any]:
    """检查 1688 API 配置状态"""
    return {"configured": is_configured(), "service": "1688_open_api"}


@router.get("/1688/search")
async def api_1688_search(
    keyword: str = Query(..., description="搜索关键词", min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    sort: str = Query("default", description="排序方式"),
) -> dict[str, Any]:
    """搜索 1688 产品"""
    result = search_products(keyword, page, page_size, sort)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "1688 API 调用失败"))
    return result


@router.get("/1688/product/{product_id}")
async def api_1688_product_detail(product_id: str) -> dict[str, Any]:
    """获取 1688 产品详情"""
    result = get_product_detail(product_id)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "获取产品详情失败"))
    return result


@router.get("/1688/supplier/{member_id}")
async def api_1688_supplier(member_id: str) -> dict[str, Any]:
    """获取 1688 供应商信息"""
    result = get_supplier_info(member_id)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "获取供应商信息失败"))
    return result


@router.get("/1688/price-trend/{product_id}")
async def api_1688_price_trend(
    product_id: str,
    days: int = Query(30, ge=7, le=365),
) -> dict[str, Any]:
    """获取产品价格趋势"""
    result = get_price_trend(product_id, days)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "获取价格趋势失败"))
    return result


# ============================================
# B2: 竞品分析
# ============================================

class CompetitorAnalysisRequest(BaseModel):
    product_id: str | None = Field(None, description="我方产品 ID")
    keyword: str | None = Field(None, description="搜索关键词")
    competitors: list[dict[str, Any]] | None = Field(None, description="手动录入竞品列表")


@router.post("/competitors/analyze")
async def api_competitor_analysis(
    req: CompetitorAnalysisRequest,
    session: DbSession,
) -> dict[str, Any]:
    """竞品分析"""
    result = await analyze_competitors(
        session,
        product_id=req.product_id,
        keyword=req.keyword,
        competitors=req.competitors,
    )
    return result


class PricingCompareRequest(BaseModel):
    our_price: float = Field(..., gt=0, description="我方价格")
    competitor_prices: list[float] = Field(..., description="竞品价格列表", min_length=1)


@router.post("/competitors/pricing")
async def api_pricing_compare(req: PricingCompareRequest) -> dict[str, Any]:
    """定价对比分析"""
    return compare_pricing(req.our_price, req.competitor_prices)


class ReviewAnalysisRequest(BaseModel):
    reviews: list[dict[str, Any]] = Field(..., description="评价列表", min_length=1)


@router.post("/competitors/reviews")
async def api_review_analysis(req: ReviewAnalysisRequest) -> dict[str, Any]:
    """评价分析"""
    return analyze_reviews(req.reviews)


# ============================================
# B3: 市场趋势分析
# ============================================

@router.get("/market-trend/analyze")
async def api_market_trend(
    keyword: str = Query(..., description="关键词", min_length=1),
    category: str | None = Query(None, description="品类"),
    days: int = Query(90, ge=7, le=365),
    region: str = Query("US", description="目标市场"),
) -> dict[str, Any]:
    """市场趋势分析"""
    return analyze_market_trend(keyword, category, days, region)


@router.get("/market-trend/hot-keywords")
async def api_hot_keywords(
    category: str | None = Query(None, description="品类筛选"),
    limit: int = Query(20, ge=1, le=50),
) -> dict[str, Any]:
    """热门关键词榜单"""
    return get_hot_keywords(category, limit)


class CategoryCompareRequest(BaseModel):
    categories: list[str] = Field(..., description="品类列表", min_length=2)
    days: int = Query(90, ge=7, le=365)


@router.post("/market-trend/compare")
async def api_category_compare(req: CategoryCompareRequest) -> dict[str, Any]:
    """多品类趋势对比"""
    return compare_category_trends(req.categories, req.days)


# ============================================
# B4: 选品评测
# ============================================

@router.get("/evaluation/status")
async def api_evaluation_status() -> dict[str, Any]:
    """获取评测集状态"""
    result = get_evaluation_status()
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class EvaluationRunRequest(BaseModel):
    test_case_ids: list[str] | None = Field(None, description="指定测试用例 ID，None 表示全部")


@router.post("/evaluation/run")
async def api_evaluation_run(req: EvaluationRunRequest) -> dict[str, Any]:
    """运行选品评测（使用内置基准评分器）"""
    result = run_evaluation(test_case_ids=req.test_case_ids)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ============================================
# B5: 自动化实验
# ============================================

class ExperimentCreateRequest(BaseModel):
    product_id: str = Field(..., description="产品 ID")
    product_name: str = Field(..., description="产品名称")
    variant_a: dict[str, Any] | None = None
    variant_b: dict[str, Any] | None = None
    experiment_days: int = Field(14, ge=1, le=90)
    hypothesis: str | None = None
    metrics: dict[str, Any] | None = None


@router.post("/experiments/create")
async def api_experiment_create(req: ExperimentCreateRequest) -> dict[str, Any]:
    """创建选品实验"""
    return create_experiment(
        product_id=req.product_id,
        product_name=req.product_name,
        variant_a=req.variant_a,
        variant_b=req.variant_b,
        experiment_days=req.experiment_days,
        hypothesis=req.hypothesis,
        metrics=req.metrics,
    )


class ExperimentStartRequest(BaseModel):
    experiment: dict[str, Any] = Field(..., description="实验配置对象")


@router.post("/experiments/start")
async def api_experiment_start(req: ExperimentStartRequest) -> dict[str, Any]:
    """启动实验"""
    return start_experiment(req.experiment)


class ExperimentRecordRequest(BaseModel):
    experiment: dict[str, Any]
    variant: str = Field(..., description="变体标识 A/B")
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0
    returns: int = 0


@router.post("/experiments/record")
async def api_experiment_record(req: ExperimentRecordRequest) -> dict[str, Any]:
    """记录实验数据"""
    return record_experiment_data(
        req.experiment,
        variant=req.variant,
        impressions=req.impressions,
        clicks=req.clicks,
        conversions=req.conversions,
        revenue=req.revenue,
        returns=req.returns,
    )


class ExperimentEvaluateRequest(BaseModel):
    experiment: dict[str, Any]


@router.post("/experiments/evaluate")
async def api_experiment_evaluate(req: ExperimentEvaluateRequest) -> dict[str, Any]:
    """评估实验"""
    return evaluate_experiment(req.experiment)


class ExperimentAutoManageRequest(BaseModel):
    experiment: dict[str, Any]


@router.post("/experiments/auto-manage")
async def api_experiment_auto_manage(req: ExperimentAutoManageRequest) -> dict[str, Any]:
    """自动化实验管理（启动/评估/终止/决策）"""
    return auto_manage_experiment(req.experiment)
