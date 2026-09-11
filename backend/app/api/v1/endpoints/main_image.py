"""
电商主图生产 API 端点（P1-5）

提供电商主图6步生产流程的API端点。

端点列表：
- GET /main-image/status - 服务状态
- POST /main-image/directions - 生成3套主图方向
- POST /main-image/copy - 生成主图短文案
- POST /main-image/all-copy - 生成所有卖点类型文案
- POST /main-image/variants - 批量生成主图变体
- POST /main-image/checklist - 生成执行清单和检查项
- GET /main-image/template - 获取完整Prompt模板
- POST /main-image/workflow - 运行完整6步工作流
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.main_image_service import (
    MAIN_IMAGE_DIRECTIONS,
    SELLING_POINT_TYPES,
    generate_all_selling_point_copies,
    generate_execution_checklist,
    generate_main_image_copy,
    generate_three_directions,
    generate_variants,
    get_complete_prompt_template,
    get_main_image_service_status,
    run_complete_workflow,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/main-image", tags=["main_image"])


# ============ 响应模型 ============

class StandardResponse(BaseModel):
    """统一API响应"""
    success: bool
    data: Any = None
    error: str | None = None


# ============ 请求模型 ============

class ProductInfoRequest(BaseModel):
    """商品信息请求"""
    name: str = Field(..., description="产品名称")
    description: str = Field("", description="产品描述")
    price: str = Field("", description="产品价格")
    category: str = Field("", description="产品类目")
    core_selling_points: list[str] = Field(default_factory=list, description="核心卖点列表")
    target_audience: str = Field("", description="目标人群")
    usage_scenarios: list[str] = Field(default_factory=list, description="使用场景列表")
    images: list[str] = Field(default_factory=list, description="产品图片URL列表")


class DirectionsRequest(ProductInfoRequest):
    """3套主图方向请求"""
    pass


class CopyRequest(ProductInfoRequest):
    """主图文案请求"""
    selling_point_type: str = Field("portability", description="卖点类型")
    count: int = Field(3, description="生成文案数量", ge=1, le=10)
    max_length: int = Field(10, description="每条文案最大字数", ge=1, le=20)


class VariantsRequest(ProductInfoRequest):
    """批量变体请求"""
    base_direction: str = Field("white_background", description="基础方向")
    variant_count: int = Field(10, description="变体数量", ge=1, le=20)


class ChecklistRequest(BaseModel):
    """执行清单请求"""
    product_info: dict[str, Any] = Field(..., description="商品信息")
    variants: list[dict[str, Any]] | None = Field(None, description="可选的变体列表")


class WorkflowRequest(ProductInfoRequest):
    """完整工作流请求"""
    use_llm: bool = Field(False, description="是否使用LLM增强")


# ============ API端点 ============

@router.get("/status", summary="获取电商主图生产服务状态")
async def api_get_status() -> StandardResponse:
    """获取服务状态"""
    return StandardResponse(success=True, data=get_main_image_service_status())


@router.post("/directions", summary="生成3套主图方向（Step 02）")
async def api_generate_directions(req: DirectionsRequest) -> StandardResponse:
    """
    生成3套主图方向策略：白底清爽/真实场景/促销转化

    不要赌一张图。先拿三种策略，再选最适合今天上新的版本。
    """
    try:
        product_info = req.model_dump()
        result = generate_three_directions(product_info)
        return StandardResponse(success=True, data=result["data"])
    except Exception as e:
        logger.error("Generate directions error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"生成3套主图方向失败: {str(e)}")


@router.post("/copy", summary="生成主图短文案（Step 05）")
async def api_generate_copy(req: CopyRequest) -> StandardResponse:
    """
    生成主图短文案，每条控制在10个字以内，只讲一个卖点。

    主图字越多，越不像主图。直接、具体、不过度承诺。
    """
    try:
        # 验证卖点类型
        if req.selling_point_type not in SELLING_POINT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的卖点类型: {req.selling_point_type}，支持: {list(SELLING_POINT_TYPES.keys())}",
            )

        product_info = req.model_dump(exclude={"selling_point_type", "count", "max_length"})
        result = generate_main_image_copy(
            product_info,
            selling_point_type=req.selling_point_type,
            count=req.count,
            max_length=req.max_length,
        )
        return StandardResponse(success=True, data=result["data"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Generate copy error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"生成主图文案失败: {str(e)}")


@router.post("/all-copy", summary="生成所有卖点类型文案")
async def api_generate_all_copy(req: ProductInfoRequest) -> StandardResponse:
    """生成所有8种卖点类型的文案，每种3条"""
    try:
        product_info = req.model_dump()
        result = generate_all_selling_point_copies(product_info)
        return StandardResponse(success=True, data=result["data"])
    except Exception as e:
        logger.error("Generate all copy error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"生成所有卖点文案失败: {str(e)}")


@router.post("/variants", summary="批量生成主图变体（Step 04）")
async def api_generate_variants(req: VariantsRequest) -> StandardResponse:
    """
    批量生成主图变体，一张跑通后再批量。

    沿用同一套模板，只改变一个重点：背景、场景、道具、文案或构图。
    每张图都要承担一个测试任务。
    """
    try:
        # 验证基础方向
        if req.base_direction not in MAIN_IMAGE_DIRECTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的基础方向: {req.base_direction}，支持: {list(MAIN_IMAGE_DIRECTIONS.keys())}",
            )

        product_info = req.model_dump(exclude={"base_direction", "variant_count"})
        result = generate_variants(
            product_info,
            base_direction=req.base_direction,
            variant_count=req.variant_count,
        )
        return StandardResponse(success=True, data=result["data"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Generate variants error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"生成主图变体失败: {str(e)}")


@router.post("/checklist", summary="生成执行清单和检查项（Step 06）")
async def api_generate_checklist(req: ChecklistRequest) -> StandardResponse:
    """
    生成执行清单和检查项。

    把方案、提示词、文案、文件名和检查项放进同一张表。
    从试试看，变成可交付。
    """
    try:
        result = generate_execution_checklist(
            req.product_info,
            variants=req.variants,
        )
        return StandardResponse(success=True, data=result["data"])
    except Exception as e:
        logger.error("Generate checklist error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"生成执行清单失败: {str(e)}")


@router.get("/template", summary="获取完整Prompt模板（可直接照抄）")
async def api_get_template() -> StandardResponse:
    """
    获取可直接照抄的完整Prompt模板。

    让AI从策划到清单一次跑完。
    """
    try:
        result = get_complete_prompt_template()
        return StandardResponse(success=True, data=result["data"])
    except Exception as e:
        logger.error("Get template error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"获取Prompt模板失败: {str(e)}")


@router.post("/workflow", summary="运行完整6步工作流")
async def api_run_workflow(req: WorkflowRequest) -> StandardResponse:
    """
    运行完整的电商主图6步生产工作流：

    Step 01: 先喂商品信息
    Step 02: 先出3套主图方向
    Step 03: 把方案改成绘图提示词
    Step 04: 一张跑通后再批量
    Step 05: 主图文案只讲一个卖点
    Step 06: 整理成执行清单
    """
    try:
        product_info = req.model_dump(exclude={"use_llm"})
        result = run_complete_workflow(product_info, use_llm=req.use_llm)
        return StandardResponse(success=True, data=result["data"])
    except Exception as e:
        logger.error("Run workflow error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"运行完整工作流失败: {str(e)}")


@router.get("/directions/config", summary="获取3套主图方向配置")
async def api_get_directions_config() -> StandardResponse:
    """获取3套主图方向的详细配置"""
    return StandardResponse(success=True, data=MAIN_IMAGE_DIRECTIONS)


@router.get("/selling-points/config", summary="获取卖点类型配置")
async def api_get_selling_points_config() -> StandardResponse:
    """获取8种卖点类型配置"""
    return StandardResponse(success=True, data=SELLING_POINT_TYPES)
