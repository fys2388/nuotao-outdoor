"""
产品端到端工作流 API 端点（P2-2）

Routes:
- GET  /api/v1/product-pipeline/status          — 工作流服务状态
- POST /api/v1/product-pipeline/run             — 运行完整工作流
- POST /api/v1/product-pipeline/confirm-list    — 人工确认后上架
- GET  /api/v1/product-pipeline/steps           — 获取工作流步骤定义
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.api.v1.deps import get_current_user
from app.core.redis import get_redis
from app.services import product_import_job_service
from app.services.product_pipeline_service import (
    PIPELINE_STEPS,
    confirm_and_list,
    get_pipeline_status,
    import_and_analyze_from_1688,
    import_from_1688,
    run_pipeline,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/product-pipeline", tags=["product_pipeline"])


# ============================================
# Request / Response models
# ============================================


class ProductInfoRequest(BaseModel):
    """商品信息请求"""
    name: str = Field(..., description="商品名称", min_length=1)
    category: str = Field("", description="商品类目")
    price: str = Field("", description="商品价格")
    description: str = Field("", description="商品描述")
    core_selling_points: list[str] = Field(default_factory=list, description="核心卖点")
    target_audience: str = Field("", description="目标人群")
    usage_scenarios: list[str] = Field(default_factory=list, description="使用场景")
    product_features: list[str] = Field(default_factory=list, description="产品功能")
    materials: list[str] = Field(default_factory=list, description="材质")
    dimensions: str = Field("", description="尺寸")
    weight: str = Field("", description="重量")
    source_url: str = Field("", description="1688商品链接")
    source_id: str = Field("", description="1688商品ID")


class RunPipelineRequest(BaseModel):
    """运行工作流请求"""
    product_info: ProductInfoRequest
    auto_list: bool = Field(False, description="是否自动上架（默认False，需要人工确认）")
    include_images: bool = Field(False, description="是否包含图片生成")


class ConfirmListRequest(BaseModel):
    """确认上架请求"""
    pipeline_result: dict[str, Any] = Field(..., description="工作流结果")
    status: str = Field("publish", description="上架状态（publish/draft/pending）")


class ImportFrom1688Request(BaseModel):
    """从1688导入商品请求"""
    url_or_id: str = Field(..., description="1688商品URL或商品ID", min_length=1)
    auto_run_pipeline: bool = Field(False, description="是否自动运行完整工作流")
    auto_list: bool = Field(False, description="是否自动上架WooCommerce（仅在auto_run_pipeline=True时生效）")


class ImportAndAnalyzeFrom1688Request(BaseModel):
    """从1688导入并执行 AI 产品分析请求"""
    url_or_id: str = Field(..., description="1688商品URL或商品ID", min_length=1)
    temperature: float = Field(0.3, ge=0, le=1, description="LLM温度")
    max_tokens: int = Field(2000, ge=500, le=8000, description="最大token数")


# ============================================
# API endpoints
# ============================================


@router.get("/status", summary="获取工作流服务状态")
async def get_status() -> dict[str, Any]:
    """返回工作流服务状态、步骤定义和配置"""
    return get_pipeline_status()


@router.get("/steps", summary="获取工作流步骤定义")
async def get_steps() -> dict[str, Any]:
    """返回工作流6个步骤的详细定义"""
    return {
        "success": True,
        "data": {
            "steps": PIPELINE_STEPS,
            "total_steps": len(PIPELINE_STEPS),
        },
        "error": None,
    }


@router.post("/run", summary="运行完整产品工作流")
async def run_product_pipeline(
    request: RunPipelineRequest,
) -> dict[str, Any]:
    """
    运行完整的产品端到端工作流：
    1. 商品信息输入
    2. AI产品分析（10字段识别 + 17字段报告）
    3. 主图生产（3套方向 + 短文案 + 10个变体）
    4. 生图Prompt生成
    5. 上架数据生成
    6. 上架WooCommerce（可选，需要人工确认）
    """
    try:
        product_info = request.product_info.model_dump()
        result = await run_pipeline(
            product_info,
            auto_list=request.auto_list,
            include_images=request.include_images,
        )
        return result
    except Exception as e:
        logger.error("Run pipeline error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post("/confirm-list", summary="人工确认后执行上架")
async def confirm_product_listing(
    request: ConfirmListRequest,
) -> dict[str, Any]:
    """
    人工确认工作流结果后，执行上架到WooCommerce

    Args:
        pipeline_result: 工作流结果（包含listing_data）
        status: 上架状态（publish/draft/pending）
    """
    try:
        result = confirm_and_list(
            request.pipeline_result,
            status=request.status,
        )
        return {
            "success": result.get("success", False),
            "data": result,
            "error": None if result.get("success") else result.get("error"),
        }
    except Exception as e:
        logger.error("Confirm list error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post("/import-from-1688", summary="从1688商品URL/ID一键导入")
async def import_product_from_1688(
    request: ImportFrom1688Request,
) -> dict[str, Any]:
    """
    从1688商品URL或ID一键导入商品信息到产品工作流

    流程：
    1. 解析URL提取商品ID
    2. 调用1688 API获取商品详情
    3. 转换为产品工作流输入格式（名称/价格/描述/图片/属性等）
    4. 可选：自动运行完整工作流（AI分析→主图→Prompt→上架数据）
    5. 可选：自动上架WooCommerce

    Args:
        url_or_id: 1688商品URL或商品ID
        auto_run_pipeline: 是否自动运行完整工作流
        auto_list: 是否自动上架（仅在auto_run_pipeline=True时生效）

    Returns:
        导入结果，包含商品信息和可选的工作流结果
    """
    try:
        result = import_from_1688(
            url_or_id=request.url_or_id,
            auto_run_pipeline=request.auto_run_pipeline,
            auto_list=request.auto_list,
        )
        return result
    except Exception as e:
        logger.error("Import from 1688 error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post(
    "/import-and-analyze-1688",
    summary="从1688导入并立即完成 AI 产品分析",
    dependencies=[Depends(get_current_user)],
)
async def import_and_analyze_product_from_1688(
    request: ImportAndAnalyzeFrom1688Request,
) -> dict[str, Any]:
    """
    导入单个 1688 商品并立即生成 10 字段 AI 识别和 17 字段产品报告。

    管理端批量导入由前端逐条调用本接口，保证单条失败隔离和进度反馈。
    """
    try:
        return await import_and_analyze_from_1688(
            url_or_id=request.url_or_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        logger.error("Import and analyze from 1688 error: %s", str(e))
        return {
            "success": False,
            "data": None,
            "error": str(e),
        }


@router.post(
    "/import-and-analyze-1688/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交1688导入与AI分析后台任务",
    dependencies=[Depends(get_current_user)],
)
async def create_import_and_analyze_job(
    request: ImportAndAnalyzeFrom1688Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    """立即返回任务 ID，前端通过状态接口轮询结果，避免网关长连接超时。"""
    try:
        job = await product_import_job_service.create_job(
            redis,
            url_or_id=request.url_or_id,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return {
            "success": True,
            "data": {
                "job_id": job["job_id"],
                "status": job["status"],
            },
            "error": None,
        }
    except Exception as e:
        logger.error("Create 1688 import job failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="无法创建后台导入任务，请检查 Redis 服务",
        ) from e


@router.get(
    "/import-and-analyze-1688/jobs/{job_id}",
    summary="查询1688导入与AI分析后台任务",
    dependencies=[Depends(get_current_user)],
)
async def get_import_and_analyze_job(
    job_id: str,
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, Any]:
    """查询后台任务状态和最终商品分析结果。"""
    try:
        job = await product_import_job_service.get_job(redis, job_id)
    except Exception as e:
        logger.error("Get 1688 import job failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="无法读取后台导入任务状态",
        ) from e
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="导入任务不存在或已过期",
        )
    return {"success": True, "data": job, "error": None}
