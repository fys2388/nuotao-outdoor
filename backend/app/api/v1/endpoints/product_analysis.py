"""
产品分析与Prompt生成 API 端点（P0-3）

提供AI产品分析、产品信息报告生成、生图Prompt自动生成等API。

端点列表：
- GET /product-analysis/status - 服务状态
- POST /product-analysis/analyze - AI产品分析（10字段识别结果）
- POST /product-analysis/report - 生成产品信息报告（17字段）
- POST /product-analysis/analyze-and-report - 一键完成分析+报告
- POST /product-analysis/prompt - 基于报告生成完整Prompt（8部分）
- POST /product-analysis/batch-prompts - 批量生成多种页面类型的Prompt
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.product_analysis_service import (
    ProductAnalysisError,
    analyze_and_generate_report,
    analyze_product,
    generate_product_report,
    get_product_analysis_status,
)
from app.services.prompt_generator_service import (
    DEFAULT_PAGE_SECTIONS,
    DETAIL_PAGE_TYPES,
    generate_batch_prompts,
    generate_full_prompt,
    get_prompt_generator_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/product-analysis", tags=["product_analysis"])


# ============ 响应模型 ============

class StandardResponse(BaseModel):
    """统一API响应"""
    success: bool
    data: Any = None
    error: str | None = None


# ============ 请求模型 ============

class ProductInfoRequest(BaseModel):
    """1688商品信息请求"""
    name: str = Field(..., description="产品名称")
    description: str = Field("", description="产品描述")
    price: str = Field("", description="产品价格")
    category: str = Field("", description="产品类目")
    images: list[str] = Field(default_factory=list, description="产品图片URL列表")
    supplier_name: str = Field("", description="供应商名称")
    additional_info: str = Field("", description="额外信息")
    temperature: float = Field(0.3, description="LLM温度")
    max_tokens: int = Field(2000, description="最大token数")


class ProductReportRequest(BaseModel):
    """产品信息报告请求"""
    product_info: dict[str, Any] = Field(..., description="1688商品信息")
    ai_recognition: dict[str, Any] | None = Field(None, description="可选的AI识别结果")
    temperature: float = Field(0.3, description="LLM温度")
    max_tokens: int = Field(2000, description="最大token数")


class AnalyzeAndReportRequest(BaseModel):
    """一键分析+报告请求"""
    product_info: dict[str, Any] = Field(..., description="1688商品信息")
    temperature: float = Field(0.3, description="LLM温度")
    max_tokens: int = Field(2000, description="最大token数")


class PromptGenerateRequest(BaseModel):
    """Prompt生成请求"""
    product_report: dict[str, Any] = Field(..., description="产品信息报告（17字段）")
    page_type: str = Field("brand_scene", description="详情页类型")
    aspect_ratio: str = Field("3:4", description="画面比例")
    custom_sections: list[str] | None = Field(None, description="自定义详情页板块顺序")
    include_header: bool = Field(True, description="是否包含头部说明")


class BatchPromptGenerateRequest(BaseModel):
    """批量Prompt生成请求"""
    product_report: dict[str, Any] = Field(..., description="产品信息报告")
    page_types: list[str] | None = Field(None, description="要生成的页面类型列表")
    aspect_ratio: str = Field("3:4", description="画面比例")


# ============ API端点 ============

@router.get("/status", summary="获取产品分析服务状态")
async def api_get_status() -> StandardResponse:
    """获取产品分析和Prompt生成服务状态"""
    return StandardResponse(
        success=True,
        data={
            "product_analysis": get_product_analysis_status(),
            "prompt_generator": get_prompt_generator_status(),
        },
    )


@router.post("/analyze", summary="AI产品分析（STEP 01）")
async def api_analyze_product(req: ProductInfoRequest) -> StandardResponse:
    """
    AI产品分析：输入1688商品信息，输出10字段AI识别结果

    识别字段：品牌名称、产品类目、产品外观、材质质感、核心卖点、
    适用场景、目标人群、视觉风格、主色调、可延展页面方向
    """
    try:
        product_info = {
            "name": req.name,
            "description": req.description,
            "price": req.price,
            "category": req.category,
            "images": req.images,
            "supplier_name": req.supplier_name,
            "additional_info": req.additional_info,
        }
        result = await analyze_product(
            product_info,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return StandardResponse(success=True, data=result["data"])
    except ProductAnalysisError as e:
        logger.error("Analyze product error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Analyze product unexpected error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/report", summary="生成产品信息报告（STEP 02）")
async def api_generate_report(req: ProductReportRequest) -> StandardResponse:
    """
    生成产品信息报告：输入1688商品信息和AI识别结果，输出17字段产品信息报告

    报告字段：品牌名称、产品名称、产品类别、产品尺寸、材质工艺、产品颜色、
    产品容量、适用对象、核心卖点、产品功能、目标人群、使用场景、视觉风格、
    主色调、可延展页面、产品描述、品质保障
    """
    try:
        result = await generate_product_report(
            req.product_info,
            ai_recognition=req.ai_recognition,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return StandardResponse(success=True, data=result["data"])
    except ProductAnalysisError as e:
        logger.error("Generate report error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Generate report unexpected error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"报告生成失败: {str(e)}")


@router.post("/analyze-and-report", summary="一键完成分析+报告（STEP 01+02）")
async def api_analyze_and_report(req: AnalyzeAndReportRequest) -> StandardResponse:
    """
    一键完成产品分析+报告生成

    先进行AI产品分析（10字段），再基于分析结果生成产品信息报告（17字段）
    """
    try:
        result = await analyze_and_generate_report(
            req.product_info,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return StandardResponse(success=True, data=result["data"])
    except ProductAnalysisError as e:
        logger.error("Analyze and report error: %s", str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Analyze and report unexpected error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"分析+报告失败: {str(e)}")


@router.post("/prompt", summary="基于报告生成完整Prompt（STEP 03）")
async def api_generate_prompt(req: PromptGenerateRequest) -> StandardResponse:
    """
    基于产品信息报告，自动生成8部分完整的生图Prompt

    Prompt结构：产品主体、品牌风格、画面场景、详情页类型、色调光影、
    构图比例、视觉效果、禁止内容
    """
    try:
        # 验证page_type
        if req.page_type not in DETAIL_PAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的页面类型: {req.page_type}，支持: {list(DETAIL_PAGE_TYPES.keys())}",
            )

        result = generate_full_prompt(
            req.product_report,
            page_type=req.page_type,
            aspect_ratio=req.aspect_ratio,
            custom_sections=req.custom_sections,
            include_header=req.include_header,
        )
        return StandardResponse(success=True, data=result["data"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Generate prompt error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Prompt生成失败: {str(e)}")


@router.post("/batch-prompts", summary="批量生成多种页面类型的Prompt")
async def api_generate_batch_prompts(req: BatchPromptGenerateRequest) -> StandardResponse:
    """
    批量生成多种详情页类型的Prompt

    默认生成：品牌场景页、产品主视觉页、功能卖点页、场景展示页、
    细节特写页、品质保障页
    """
    try:
        # 验证page_types
        if req.page_types:
            invalid_types = [pt for pt in req.page_types if pt not in DETAIL_PAGE_TYPES]
            if invalid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的页面类型: {invalid_types}，支持: {list(DETAIL_PAGE_TYPES.keys())}",
                )

        result = generate_batch_prompts(
            req.product_report,
            page_types=req.page_types,
            aspect_ratio=req.aspect_ratio,
        )
        return StandardResponse(success=True, data=result["data"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Generate batch prompts error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"批量Prompt生成失败: {str(e)}")


@router.get("/page-types", summary="获取支持的详情页类型")
async def api_get_page_types() -> StandardResponse:
    """获取支持的详情页类型列表"""
    return StandardResponse(
        success=True,
        data={
            "page_types": DETAIL_PAGE_TYPES,
            "default_sections": DEFAULT_PAGE_SECTIONS,
        },
    )
