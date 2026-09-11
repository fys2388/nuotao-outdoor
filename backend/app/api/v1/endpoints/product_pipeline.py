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
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.product_pipeline_service import (
    get_pipeline_status,
    run_pipeline,
    confirm_and_list,
    import_from_1688,
    PIPELINE_STEPS,
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
