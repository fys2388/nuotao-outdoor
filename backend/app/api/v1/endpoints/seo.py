"""
SEO 基建 API 端点
支持结构化数据生成、Sitemap 生成、关键词策略、SEO 审计
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.seo_service import (
    generate_breadcrumb_structured_data,
    generate_faq_structured_data,
    generate_keyword_strategy,
    generate_organization_structured_data,
    generate_product_structured_data,
    generate_robots_txt,
    generate_sitemap,
    get_seo_status,
    seo_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seo", tags=["seo"])


# ============================================
# 请求/响应模型
# ============================================

class ProductStructuredDataRequest(BaseModel):
    """产品结构化数据请求"""
    product_name: str = Field(..., description="产品名称")
    product_description: str = Field("", description="产品描述")
    price: float | None = Field(None, description="价格", gt=0)
    currency: str = Field("USD", description="货币代码")
    product_url: str = Field("", description="产品页面 URL")
    image_url: str = Field("", description="产品图片 URL")
    brand: str = Field("Nuotao Outdoor", description="品牌")
    sku: str = Field("", description="SKU")
    availability: str = Field("InStock", description="库存状态")
    rating_value: float | None = Field(None, description="评分（0-5）", ge=0, le=5)
    review_count: int = Field(0, description="评论数量", ge=0)
    category: str = Field("", description="产品分类")


class BreadcrumbRequest(BaseModel):
    """面包屑结构化数据请求"""
    breadcrumbs: list[dict[str, str]] = Field(..., description="面包屑列表，每项包含 name 和 url")


class FAQRequest(BaseModel):
    """FAQ 结构化数据请求"""
    faqs: list[dict[str, str]] = Field(..., description="FAQ 列表，每项包含 question 和 answer")


class SitemapRequest(BaseModel):
    """Sitemap 生成请求"""
    pages: list[dict[str, Any]] = Field(default_factory=list, description="普通页面列表")
    products: list[dict[str, Any]] | None = Field(None, description="产品页面列表")
    categories: list[dict[str, Any]] | None = Field(None, description="分类页面列表")


class KeywordStrategyRequest(BaseModel):
    """关键词策略请求"""
    product_category: str = Field("outdoor gear", description="产品分类")
    target_audience: str = Field("outdoor enthusiasts", description="目标受众")
    location: str = Field("US", description="目标市场")


class SEOAuditRequest(BaseModel):
    """SEO 审计请求"""
    page_url: str = Field("", description="页面 URL")
    page_title: str = Field("", description="页面标题")
    meta_description: str = Field("", description="Meta 描述")
    h1_tags: list[str] | None = Field(None, description="H1 标签列表")
    content_length: int = Field(0, description="内容长度（字符数）", ge=0)
    image_count: int = Field(0, description="图片数量", ge=0)
    images_with_alt: int = Field(0, description="有 alt 属性的图片数量", ge=0)
    internal_links: int = Field(0, description="内部链接数量", ge=0)
    external_links: int = Field(0, description="外部链接数量", ge=0)
    has_structured_data: bool = Field(False, description="是否有结构化数据")
    has_sitemap: bool = Field(True, description="是否有 sitemap")
    has_robots_txt: bool = Field(True, description="是否有 robots.txt")
    page_load_time_ms: float | None = Field(None, description="页面加载时间（毫秒）", gt=0)
    is_mobile_friendly: bool = Field(True, description="是否移动端友好")
    has_https: bool = Field(True, description="是否有 HTTPS")


# ============================================
# API 端点
# ============================================

@router.get(
    "/status",
    summary="获取 SEO 基建系统状态",
)
async def get_status() -> dict[str, Any]:
    """获取 SEO 基建系统状态、网站配置、支持的功能"""
    return get_seo_status()


@router.post(
    "/structured-data/product",
    summary="生成产品结构化数据",
)
async def generate_product_sd(
    request: ProductStructuredDataRequest,
) -> dict[str, Any]:
    """
    生成产品页面结构化数据（Schema.org Product JSON-LD）

    包含：Product、Offer、Brand、AggregateRating 等 Schema 类型。
    可直接嵌入页面 <script type="application/ld+json"> 标签中。
    """
    try:
        structured_data = generate_product_structured_data(
            product_name=request.product_name,
            product_description=request.product_description,
            price=request.price,
            currency=request.currency,
            product_url=request.product_url,
            image_url=request.image_url,
            brand=request.brand,
            sku=request.sku,
            availability=request.availability,
            rating_value=request.rating_value,
            review_count=request.review_count,
            category=request.category,
        )
        return {
            "success": True,
            "structured_data": structured_data,
            "json_ld": f'<script type="application/ld+json">{__import__("json").dumps(structured_data, indent=2)}</script>',
            "schema_types": ["Product", "Offer", "Brand"],
            "message": "产品结构化数据生成成功",
        }
    except Exception as e:
        logger.exception("Generate product structured data failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate product structured data failed: {e!s}",
        )


@router.get(
    "/structured-data/organization",
    summary="生成组织结构化数据",
)
async def generate_organization_sd() -> dict[str, Any]:
    """
    生成组织结构化数据（Schema.org Organization JSON-LD）

    包含：Organization、ContactPoint、sameAs 社交媒体链接。
    建议放在网站首页或全局页脚。
    """
    try:
        structured_data = generate_organization_structured_data()
        return {
            "success": True,
            "structured_data": structured_data,
            "schema_types": ["Organization", "ContactPoint"],
            "message": "组织结构化数据生成成功",
        }
    except Exception as e:
        logger.exception("Generate organization structured data failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate organization structured data failed: {e!s}",
        )


@router.post(
    "/structured-data/breadcrumb",
    summary="生成面包屑结构化数据",
)
async def generate_breadcrumb_sd(
    request: BreadcrumbRequest,
) -> dict[str, Any]:
    """
    生成面包屑导航结构化数据（Schema.org BreadcrumbList JSON-LD）

    帮助搜索引擎理解页面层级结构，可能在搜索结果中显示面包屑导航。
    """
    try:
        structured_data = generate_breadcrumb_structured_data(request.breadcrumbs)
        return {
            "success": True,
            "structured_data": structured_data,
            "schema_types": ["BreadcrumbList", "ListItem"],
            "item_count": len(request.breadcrumbs),
            "message": "面包屑结构化数据生成成功",
        }
    except Exception as e:
        logger.exception("Generate breadcrumb structured data failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate breadcrumb structured data failed: {e!s}",
        )


@router.post(
    "/structured-data/faq",
    summary="生成 FAQ 结构化数据",
)
async def generate_faq_sd(
    request: FAQRequest,
) -> dict[str, Any]:
    """
    生成 FAQ 结构化数据（Schema.org FAQPage JSON-LD）

    包含常见问题和答案，可能在搜索结果中显示为富摘要。
    """
    try:
        structured_data = generate_faq_structured_data(request.faqs)
        return {
            "success": True,
            "structured_data": structured_data,
            "schema_types": ["FAQPage", "Question", "Answer"],
            "faq_count": len(request.faqs),
            "message": "FAQ 结构化数据生成成功",
        }
    except Exception as e:
        logger.exception("Generate FAQ structured data failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate FAQ structured data failed: {e!s}",
        )


@router.post(
    "/sitemap",
    summary="生成 XML Sitemap",
)
async def generate_sitemap_endpoint(
    request: SitemapRequest,
) -> dict[str, Any]:
    """
    生成 XML Sitemap

    包含首页、普通页面、分类页面、产品页面。
    每个 URL 包含 lastmod、changefreq、priority 属性。
    """
    try:
        sitemap_xml = generate_sitemap(
            pages=request.pages,
            products=request.products,
            categories=request.categories,
        )
        url_count = sitemap_xml.count("<url>")
        return {
            "success": True,
            "sitemap_xml": sitemap_xml,
            "url_count": url_count,
            "message": f"XML Sitemap 生成成功，共 {url_count} 个 URL",
        }
    except Exception as e:
        logger.exception("Generate sitemap failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate sitemap failed: {e!s}",
        )


@router.get(
    "/robots-txt",
    summary="生成 robots.txt",
)
async def generate_robots_txt_endpoint() -> dict[str, Any]:
    """
    生成 robots.txt

    包含用户代理规则、禁止爬取路径、Sitemap 位置。
    """
    try:
        robots_txt = generate_robots_txt()
        return {
            "success": True,
            "robots_txt": robots_txt,
            "message": "robots.txt 生成成功",
        }
    except Exception as e:
        logger.exception("Generate robots.txt failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate robots.txt failed: {e!s}",
        )


@router.post(
    "/keyword-strategy",
    summary="生成关键词策略",
)
async def generate_keyword_strategy_endpoint(
    request: KeywordStrategyRequest,
) -> dict[str, Any]:
    """
    生成关键词策略

    包含 6 个关键词分组：主要关键词、长尾关键词、商业关键词、信息类关键词、本地关键词。
    每个关键词包含搜索量估算、竞争度、优先级。
    """
    try:
        strategy = generate_keyword_strategy(
            product_category=request.product_category,
            target_audience=request.target_audience,
            location=request.location,
        )
        return {
            "success": True,
            "strategy": strategy,
            "message": f"关键词策略生成成功，共 {strategy['summary']['total_keywords']} 个关键词",
        }
    except Exception as e:
        logger.exception("Generate keyword strategy failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generate keyword strategy failed: {e!s}",
        )


@router.post(
    "/audit",
    summary="SEO 审计检查",
)
async def seo_audit_endpoint(
    request: SEOAuditRequest,
) -> dict[str, Any]:
    """
    SEO 审计检查

    检查 15+ 项 SEO 要素：标题、Meta 描述、H1、内容长度、图片 Alt、内部链接、结构化数据、HTTPS、移动端友好、页面速度、Sitemap、robots.txt。

    返回：总分（0-100）、评级（A-F）、问题列表、警告列表、通过检查列表、改进建议。
    """
    try:
        audit_result = seo_audit(
            page_url=request.page_url,
            page_title=request.page_title,
            meta_description=request.meta_description,
            h1_tags=request.h1_tags,
            content_length=request.content_length,
            image_count=request.image_count,
            images_with_alt=request.images_with_alt,
            internal_links=request.internal_links,
            external_links=request.external_links,
            has_structured_data=request.has_structured_data,
            has_sitemap=request.has_sitemap,
            has_robots_txt=request.has_robots_txt,
            page_load_time_ms=request.page_load_time_ms,
            is_mobile_friendly=request.is_mobile_friendly,
            has_https=request.has_https,
        )
        return {
            "success": True,
            "audit": audit_result,
            "message": f"SEO 审计完成，得分 {audit_result['score']}/100，评级 {audit_result['grade']} ({audit_result['grade_label']})",
        }
    except Exception as e:
        logger.exception("SEO audit failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SEO audit failed: {e!s}",
        )
