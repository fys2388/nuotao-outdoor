"""
内容生成系统 API 端点
支持卖点、SEO、EDM 内容生成、批量生成、审核流程
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.content_generation_service import (
    create_content_item,
    generate_edm_content,
    generate_selling_points,
    generate_seo_content,
    get_content_generation_status,
    list_content_items,
    review_content,
    submit_for_review,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["content"])


# ============================================
# 请求/响应模型
# ============================================

class SellingPointsRequest(BaseModel):
    """卖点生成请求"""
    product_name: str = Field(..., description="产品名称")
    product_category: str = Field("", description="产品分类")
    key_features: list[str] | None = Field(None, description="核心特性列表")
    target_audience: str = Field("outdoor enthusiasts", description="目标受众")
    price: float | None = Field(None, description="价格", gt=0)
    product_id: str | None = Field(None, description="关联产品 ID")


class SEOContentRequest(BaseModel):
    """SEO 内容生成请求"""
    product_name: str = Field(..., description="产品名称")
    product_category: str = Field("", description="产品分类")
    keywords: list[str] | None = Field(None, description="关键词列表")
    target_audience: str = Field("outdoor enthusiasts", description="目标受众")
    product_id: str | None = Field(None, description="关联产品 ID")


class EDMContentRequest(BaseModel):
    """EDM 邮件生成请求"""
    email_type: str = Field("abandoned_cart", description="邮件类型：abandoned_cart/repurchase/welcome")
    customer_name: str = Field("Valued Customer", description="客户名称")
    product_name: str = Field("", description="产品名称")
    product_category: str = Field("", description="产品分类")
    discount_percent: int = Field(10, description="折扣百分比", gt=0, le=50)
    abandoned_cart_value: float | None = Field(None, description="弃购购物车价值", gt=0)


class BatchGenerateRequest(BaseModel):
    """批量生成请求"""
    content_type: str = Field(..., description="内容类型")
    products: list[dict[str, Any]] = Field(..., description="产品列表")
    common_params: dict[str, Any] | None = Field(None, description="通用参数")


class ReviewRequest(BaseModel):
    """审核请求"""
    action: str = Field(..., description="审核动作：approve/reject")
    reviewer: str = Field("admin", description="审核者")
    comment: str = Field("", description="审核评论")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取内容生成系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取内容生成系统状态、支持的内容类型、质量规则"""
    return get_content_generation_status()


@router.post(
    "/generate/selling-points",
    summary="生成产品卖点",
)
async def generate_selling_points_endpoint(
    request: SellingPointsRequest,
) -> dict[str, Any]:
    """
    生成产品卖点

    包含：标题、卖点列表、产品描述、价值主张。
    生成后自动进行质量检查并保存为草稿。
    """
    try:
        content_data = generate_selling_points(
            product_name=request.product_name,
            product_category=request.product_category,
            key_features=request.key_features,
            target_audience=request.target_audience,
            price=request.price,
        )

        content_item = create_content_item(
            content_type="product_selling_points",
            title=content_data["title"],
            content_data=content_data,
            product_id=request.product_id,
            product_name=request.product_name,
        )

        return {
            "success": True,
            "content": content_data,
            "content_item": content_item,
            "quality_score": content_item["quality_score"],
            "quality_issues": content_item["quality_issues"],
            "message": "产品卖点生成成功",
        }
    except Exception as e:
        logger.exception("Generate selling points failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate selling points failed: {e!s}",
        )


@router.post(
    "/generate/seo",
    summary="生成 SEO 内容",
)
async def generate_seo_endpoint(
    request: SEOContentRequest,
) -> dict[str, Any]:
    """
    生成 SEO 内容

    包含：SEO 标题、Meta 描述、关键词、文章大纲、正文段落。
    生成后自动进行质量检查并保存为草稿。
    """
    try:
        content_data = generate_seo_content(
            product_name=request.product_name,
            product_category=request.product_category,
            keywords=request.keywords,
            target_audience=request.target_audience,
        )

        content_item = create_content_item(
            content_type="seo_article",
            title=content_data["seo_title"],
            content_data=content_data,
            product_id=request.product_id,
            product_name=request.product_name,
        )

        return {
            "success": True,
            "content": content_data,
            "content_item": content_item,
            "quality_score": content_item["quality_score"],
            "quality_issues": content_item["quality_issues"],
            "message": "SEO 内容生成成功",
        }
    except Exception as e:
        logger.exception("Generate SEO content failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate SEO content failed: {e!s}",
        )


@router.post(
    "/generate/edm",
    summary="生成 EDM 营销邮件",
)
async def generate_edm_endpoint(
    request: EDMContentRequest,
) -> dict[str, Any]:
    """
    生成 EDM 营销邮件

    支持的邮件类型：
    - abandoned_cart：弃购挽回邮件
    - repurchase：复购营销邮件
    - welcome：欢迎邮件

    包含：主题、预览文本、正文、CTA 按钮、紧迫感文案。
    """
    try:
        content_data = generate_edm_content(
            email_type=request.email_type,
            customer_name=request.customer_name,
            product_name=request.product_name,
            product_category=request.product_category,
            discount_percent=request.discount_percent,
            abandoned_cart_value=request.abandoned_cart_value,
        )

        content_item = create_content_item(
            content_type=f"edm_{request.email_type}",
            title=content_data["subject"],
            content_data=content_data,
        )

        return {
            "success": True,
            "content": content_data,
            "content_item": content_item,
            "quality_score": content_item["quality_score"],
            "quality_issues": content_item["quality_issues"],
            "message": "EDM 邮件生成成功",
        }
    except Exception as e:
        logger.exception("Generate EDM content failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate EDM content failed: {e!s}",
        )


@router.post(
    "/generate/batch",
    summary="批量生成内容",
)
async def batch_generate_endpoint(
    request: BatchGenerateRequest,
) -> dict[str, Any]:
    """
    批量生成内容

    支持为多个产品批量生成同类型内容（卖点/SEO/EDM）。
    返回每个产品的生成结果和汇总统计。
    """
    try:
        results = []
        success_count = 0
        failed_count = 0

        common_params = request.common_params or {}

        for product in request.products:
            try:
                if request.content_type == "product_selling_points":
                    content_data = generate_selling_points(
                        product_name=product.get("name", ""),
                        product_category=product.get("category", common_params.get("product_category", "")),
                        key_features=product.get("features", common_params.get("key_features")),
                        target_audience=common_params.get("target_audience", "outdoor enthusiasts"),
                        price=product.get("price"),
                    )
                elif request.content_type == "seo_article":
                    content_data = generate_seo_content(
                        product_name=product.get("name", ""),
                        product_category=product.get("category", common_params.get("product_category", "")),
                        keywords=common_params.get("keywords"),
                        target_audience=common_params.get("target_audience", "outdoor enthusiasts"),
                    )
                else:
                    raise ValueError(f"Unsupported content type for batch: {request.content_type}")

                content_item = create_content_item(
                    content_type=request.content_type,
                    title=content_data.get("title", content_data.get("seo_title", "")),
                    content_data=content_data,
                    product_id=product.get("id"),
                    product_name=product.get("name", ""),
                )

                results.append({
                    "product_name": product.get("name", ""),
                    "success": True,
                    "content_id": content_item["id"],
                    "quality_score": content_item["quality_score"],
                })
                success_count += 1

            except Exception as e:
                results.append({
                    "product_name": product.get("name", ""),
                    "success": False,
                    "error": str(e),
                })
                failed_count += 1

        return {
            "success": True,
            "total": len(request.products),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
            "message": f"批量生成完成：成功 {success_count}，失败 {failed_count}",
        }
    except Exception as e:
        logger.exception("Batch generate failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch generate failed: {e!s}",
        )


@router.post(
    "/items/{content_id}/submit-review",
    summary="提交内容审核",
)
async def submit_review_endpoint(
    content_id: str,
) -> dict[str, Any]:
    """
    提交内容审核

    将草稿状态的内容提交为待审核状态。
    """
    try:
        content = submit_for_review(content_id)
        return {
            "success": True,
            "content": content,
            "message": "内容已提交审核",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Submit review failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Submit review failed: {e!s}",
        )


@router.post(
    "/items/{content_id}/review",
    summary="审核内容",
)
async def review_content_endpoint(
    content_id: str,
    request: ReviewRequest,
) -> dict[str, Any]:
    """
    审核内容

    支持通过（approve）或拒绝（reject）内容。
    审核后内容状态更新为已通过或已拒绝。
    """
    try:
        content = review_content(
            content_id=content_id,
            action=request.action,
            reviewer=request.reviewer,
            comment=request.comment,
        )
        return {
            "success": True,
            "content": content,
            "message": f"内容已{request.action}",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Review content failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review content failed: {e!s}",
        )


@router.get(
    "/items",
    summary="获取内容列表",
)
async def list_content_endpoint(
    content_type: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取内容列表

    支持按内容类型、状态、关联产品筛选。
    返回内容列表和统计信息（按类型/状态分布、平均质量分）。
    """
    try:
        result = list_content_items(
            content_type=content_type,
            status=status,
            product_id=product_id,
            limit=limit,
        )
        return result
    except Exception as e:
        logger.exception("List content failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List content failed: {e!s}",
        )
