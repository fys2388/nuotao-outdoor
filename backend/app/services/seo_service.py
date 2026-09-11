"""
SEO 基建服务
支持结构化数据（Schema.org JSON-LD）、Sitemap 生成、关键词策略、SEO 审计
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger(__name__)

# SEO 数据存储路径
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "seo",
)

# 默认网站配置
DEFAULT_SITE_CONFIG = {
    "site_name": "Nuotao Outdoor",
    "site_url": "https://nuotaooutdoor.com",
    "site_description": "Premium outdoor gear and camping equipment for adventurers worldwide.",
    "site_language": "en",
    "organization": {
        "name": "Nuotao Outdoor",
        "url": "https://nuotaooutdoor.com",
        "logo": "https://nuotaooutdoor.com/logo.png",
        "contact_point": {
            "email": "support@nuotaooutdoor.com",
            "contact_type": "customer service",
            "available_language": ["English", "German", "Spanish", "French"],
        },
        "same_as": [
            "https://facebook.com/nuotaooutdoor",
            "https://instagram.com/nuotaooutdoor",
            "https://youtube.com/@nuotaooutdoor",
        ],
    },
    "social_media": {
        "facebook": "https://facebook.com/nuotaooutdoor",
        "instagram": "https://instagram.com/nuotaooutdoor",
        "youtube": "https://youtube.com/@nuotaooutdoor",
        "pinterest": "https://pinterest.com/nuotaooutdoor",
    },
}


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def generate_product_structured_data(
    product_name: str,
    product_description: str = "",
    price: float | None = None,
    currency: str = "USD",
    product_url: str = "",
    image_url: str = "",
    brand: str = "Nuotao Outdoor",
    sku: str = "",
    availability: str = "InStock",
    rating_value: float | None = None,
    review_count: int = 0,
    category: str = "",
) -> dict[str, Any]:
    """
    生成产品页面结构化数据（Schema.org Product JSON-LD）

    Args:
        product_name: 产品名称
        product_description: 产品描述
        price: 价格
        currency: 货币代码
        product_url: 产品页面 URL
        image_url: 产品图片 URL
        brand: 品牌
        sku: SKU
        availability: 库存状态（InStock/OutOfStock/PreOrder）
        rating_value: 评分（0-5）
        review_count: 评论数量
        category: 产品分类

    Returns:
        Schema.org Product 结构化数据
    """
    site_config = DEFAULT_SITE_CONFIG

    if not product_url:
        product_url = f"{site_config['site_url']}/products/{sku.lower() if sku else product_name.lower().replace(' ', '-')}"

    if not image_url:
        image_url = f"{site_config['site_url']}/images/products/{sku.lower() if sku else 'product'}.jpg"

    # 构建 Product 结构化数据
    product_data: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": product_name,
        "description": product_description or f"Buy {product_name} at {site_config['site_name']}. Premium quality outdoor gear.",
        "url": product_url,
        "image": [image_url],
        "brand": {
            "@type": "Brand",
            "name": brand,
        },
        "sku": sku,
        "category": category,
        "offers": {
            "@type": "Offer",
            "url": product_url,
            "priceCurrency": currency,
            "availability": f"https://schema.org/{availability}",
            "itemCondition": "https://schema.org/NewCondition",
        },
    }

    # 添加价格
    if price is not None:
        product_data["offers"]["price"] = price

    # 添加评分
    if rating_value is not None and review_count > 0:
        product_data["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": rating_value,
            "reviewCount": review_count,
        }

    return product_data


def generate_organization_structured_data() -> dict[str, Any]:
    """
    生成组织结构化数据（Schema.org Organization JSON-LD）

    Returns:
        Schema.org Organization 结构化数据
    """
    org = DEFAULT_SITE_CONFIG["organization"]
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": org["name"],
        "url": org["url"],
        "logo": org["logo"],
        "contactPoint": {
            "@type": "ContactPoint",
            "email": org["contact_point"]["email"],
            "contactType": org["contact_point"]["contact_type"],
            "availableLanguage": org["contact_point"]["available_language"],
        },
        "sameAs": org["same_as"],
    }


def generate_breadcrumb_structured_data(
    breadcrumbs: list[dict[str, str]],
) -> dict[str, Any]:
    """
    生成面包屑导航结构化数据（Schema.org BreadcrumbList JSON-LD）

    Args:
        breadcrumbs: 面包屑列表，每项包含 name 和 url

    Returns:
        Schema.org BreadcrumbList 结构化数据
    """
    item_list_element = []
    for i, crumb in enumerate(breadcrumbs, 1):
        item_list_element.append({
            "@type": "ListItem",
            "position": i,
            "name": crumb["name"],
            "item": crumb["url"],
        })

    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": item_list_element,
    }


def generate_faq_structured_data(
    faqs: list[dict[str, str]],
) -> dict[str, Any]:
    """
    生成 FAQ 结构化数据（Schema.org FAQPage JSON-LD）

    Args:
        faqs: FAQ 列表，每项包含 question 和 answer

    Returns:
        Schema.org FAQPage 结构化数据
    """
    main_entity = []
    for faq in faqs:
        main_entity.append({
            "@type": "Question",
            "name": faq["question"],
            "acceptedAnswer": {
                "@type": "Answer",
                "text": faq["answer"],
            },
        })

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": main_entity,
    }


def generate_sitemap(
    pages: list[dict[str, Any]],
    products: list[dict[str, Any]] | None = None,
    categories: list[dict[str, Any]] | None = None,
) -> str:
    """
    生成 XML Sitemap

    Args:
        pages: 普通页面列表，每项包含 url、lastmod、changefreq、priority
        products: 产品页面列表
        categories: 分类页面列表

    Returns:
        XML 格式的 sitemap 字符串
    """
    site_config = DEFAULT_SITE_CONFIG

    # 创建根元素
    urlset = Element("urlset")
    urlset.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset.set("xmlns:xhtml", "http://www.w3.org/1999/xhtml")

    now = datetime.utcnow().strftime("%Y-%m-%d")

    # 添加首页
    home_url = SubElement(urlset, "url")
    SubElement(home_url, "loc").text = site_config["site_url"] + "/"
    SubElement(home_url, "lastmod").text = now
    SubElement(home_url, "changefreq").text = "daily"
    SubElement(home_url, "priority").text = "1.0"

    # 添加普通页面
    for page in pages:
        url_elem = SubElement(urlset, "url")
        SubElement(url_elem, "loc").text = page["url"]
        SubElement(url_elem, "lastmod").text = page.get("lastmod", now)
        SubElement(url_elem, "changefreq").text = page.get("changefreq", "weekly")
        SubElement(url_elem, "priority").text = str(page.get("priority", 0.8))

    # 添加分类页面
    if categories:
        for category in categories:
            url_elem = SubElement(urlset, "url")
            SubElement(url_elem, "loc").text = f"{site_config['site_url']}/category/{category.get('slug', category.get('name', '').lower().replace(' ', '-'))}"
            SubElement(url_elem, "lastmod").text = now
            SubElement(url_elem, "changefreq").text = "weekly"
            SubElement(url_elem, "priority").text = "0.7"

    # 添加产品页面
    if products:
        for product in products:
            url_elem = SubElement(urlset, "url")
            product_slug = product.get("slug", product.get("name", "").lower().replace(" ", "-"))
            SubElement(url_elem, "loc").text = f"{site_config['site_url']}/products/{product_slug}"
            SubElement(url_elem, "lastmod").text = product.get("updated_at", now)
            SubElement(url_elem, "changefreq").text = "monthly"
            SubElement(url_elem, "priority").text = "0.6"

    # 生成 XML 字符串
    xml_bytes = tostring(urlset, encoding="unicode", xml_declaration=True)
    return xml_bytes


def generate_robots_txt(
    sitemap_url: str = "",
    disallow_paths: list[str] | None = None,
) -> str:
    """
    生成 robots.txt

    Args:
        sitemap_url: Sitemap URL
        disallow_paths: 禁止爬取的路径列表

    Returns:
        robots.txt 内容
    """
    site_config = DEFAULT_SITE_CONFIG

    if not sitemap_url:
        sitemap_url = f"{site_config['site_url']}/sitemap.xml"

    if disallow_paths is None:
        disallow_paths = [
            "/admin/",
            "/cart/",
            "/checkout/",
            "/account/",
            "/wp-admin/",
            "/wp-includes/",
            "/?s=",
            "/search/",
        ]

    lines = [
        "# robots.txt for Nuotao Outdoor",
        f"# Generated at {datetime.utcnow().isoformat()}",
        "",
        "User-agent: *",
        "Allow: /",
    ]

    for path in disallow_paths:
        lines.append(f"Disallow: {path}")

    lines.extend([
        "",
        "# Allow specific bots",
        "User-agent: Googlebot",
        "Allow: /",
        "",
        "User-agent: Bingbot",
        "Allow: /",
        "",
        f"Sitemap: {sitemap_url}",
    ])

    return "\n".join(lines)


def generate_keyword_strategy(
    product_category: str = "outdoor gear",
    target_audience: str = "outdoor enthusiasts",
    location: str = "US",
) -> dict[str, Any]:
    """
    生成关键词策略

    Args:
        product_category: 产品分类
        target_audience: 目标受众
        location: 目标市场

    Returns:
        关键词策略（分组、优先级、搜索量估算、竞争度）
    """
    # 基于模板生成关键词策略
    keyword_groups = {
        "primary_keywords": {
            "description": f"主要关键词 - 高搜索量，高竞争，针对{product_category}",
            "keywords": [
                {"keyword": f"best {product_category}", "search_volume": "high", "competition": "high", "priority": 1},
                {"keyword": f"{product_category} for {target_audience}", "search_volume": "medium", "competition": "medium", "priority": 1},
                {"keyword": f"buy {product_category} online", "search_volume": "medium", "competition": "high", "priority": 2},
                {"keyword": f"{product_category} review", "search_volume": "medium", "competition": "medium", "priority": 2},
            ],
        },
        "long_tail_keywords": {
            "description": "长尾关键词 - 低搜索量，低竞争，高转化率",
            "keywords": [
                {"keyword": f"best {product_category} for beginners", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"affordable {product_category} under $100", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"lightweight {product_category} for hiking", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"durable {product_category} for camping", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"{product_category} buying guide 2026", "search_volume": "low", "competition": "low", "priority": 2},
            ],
        },
        "commercial_keywords": {
            "description": "商业关键词 - 高购买意图，高转化率",
            "keywords": [
                {"keyword": f"{product_category} for sale", "search_volume": "medium", "competition": "high", "priority": 1},
                {"keyword": f"cheap {product_category}", "search_volume": "medium", "competition": "medium", "priority": 2},
                {"keyword": f"{product_category} free shipping", "search_volume": "low", "competition": "low", "priority": 2},
                {"keyword": f"{product_category} discount code", "search_volume": "low", "competition": "low", "priority": 3},
            ],
        },
        "informational_keywords": {
            "description": "信息类关键词 - 高搜索量，低购买意图，用于内容营销",
            "keywords": [
                {"keyword": f"how to choose {product_category}", "search_volume": "medium", "competition": "medium", "priority": 2},
                {"keyword": f"what to look for in {product_category}", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"{product_category} vs alternatives", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"tips for using {product_category}", "search_volume": "low", "competition": "low", "priority": 3},
            ],
        },
        "local_keywords": {
            "description": f"本地关键词 - 针对{location}市场",
            "keywords": [
                {"keyword": f"{product_category} {location}", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"buy {product_category} in {location}", "search_volume": "low", "competition": "low", "priority": 3},
                {"keyword": f"{product_category} store near me", "search_volume": "low", "competition": "low", "priority": 4},
            ],
        },
    }

    # 统计
    total_keywords = sum(len(group["keywords"]) for group in keyword_groups.values())
    high_priority = sum(
        1 for group in keyword_groups.values()
        for kw in group["keywords"]
        if kw["priority"] <= 2
    )

    return {
        "product_category": product_category,
        "target_audience": target_audience,
        "location": location,
        "keyword_groups": keyword_groups,
        "summary": {
            "total_keywords": total_keywords,
            "high_priority_keywords": high_priority,
            "groups_count": len(keyword_groups),
        },
        "recommendations": [
            "优先优化高优先级关键词（priority 1-2）在产品页面和分类页面",
            "使用长尾关键词创建博客内容和购买指南",
            "商业关键词用于着陆页和广告活动",
            "信息类关键词用于内容营销和SEO文章",
            "定期监控关键词排名和搜索量变化",
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }


def seo_audit(
    page_url: str = "",
    page_title: str = "",
    meta_description: str = "",
    h1_tags: list[str] | None = None,
    content_length: int = 0,
    image_count: int = 0,
    images_with_alt: int = 0,
    internal_links: int = 0,
    external_links: int = 0,
    has_structured_data: bool = False,
    has_sitemap: bool = True,
    has_robots_txt: bool = True,
    page_load_time_ms: float | None = None,
    is_mobile_friendly: bool = True,
    has_https: bool = True,
) -> dict[str, Any]:
    """
    SEO 审计检查

    Args:
        page_url: 页面 URL
        page_title: 页面标题
        meta_description: Meta 描述
        h1_tags: H1 标签列表
        content_length: 内容长度（字符数）
        image_count: 图片数量
        images_with_alt: 有 alt 属性的图片数量
        internal_links: 内部链接数量
        external_links: 外部链接数量
        has_structured_data: 是否有结构化数据
        has_sitemap: 是否有 sitemap
        has_robots_txt: 是否有 robots.txt
        page_load_time_ms: 页面加载时间（毫秒）
        is_mobile_friendly: 是否移动端友好
        has_https: 是否有 HTTPS

    Returns:
        SEO 审计结果
    """
    issues = []
    warnings = []
    passed_checks = []
    score = 100

    # 1. 标题检查
    if not page_title:
        issues.append("Missing page title")
        score -= 15
    elif len(page_title) < 30:
        warnings.append(f"Page title too short: {len(page_title)} chars (min 30)")
        score -= 5
    elif len(page_title) > 60:
        warnings.append(f"Page title too long: {len(page_title)} chars (max 60)")
        score -= 3
    else:
        passed_checks.append(f"Page title length OK: {len(page_title)} chars")

    # 2. Meta 描述检查
    if not meta_description:
        issues.append("Missing meta description")
        score -= 10
    elif len(meta_description) < 70:
        warnings.append(f"Meta description too short: {len(meta_description)} chars (min 70)")
        score -= 3
    elif len(meta_description) > 160:
        warnings.append(f"Meta description too long: {len(meta_description)} chars (max 160)")
        score -= 2
    else:
        passed_checks.append(f"Meta description length OK: {len(meta_description)} chars")

    # 3. H1 标签检查
    if h1_tags is None:
        h1_tags = []
    if len(h1_tags) == 0:
        issues.append("Missing H1 tag")
        score -= 10
    elif len(h1_tags) > 1:
        warnings.append(f"Multiple H1 tags: {len(h1_tags)} (should be exactly 1)")
        score -= 5
    else:
        passed_checks.append("Exactly one H1 tag")

    # 4. 内容长度检查
    if content_length < 300:
        issues.append(f"Content too thin: {content_length} chars (min 300)")
        score -= 10
    elif content_length < 500:
        warnings.append(f"Content could be longer: {content_length} chars (recommended 500+)")
        score -= 3
    else:
        passed_checks.append(f"Content length OK: {content_length} chars")

    # 5. 图片 Alt 检查
    if image_count > 0:
        alt_ratio = images_with_alt / image_count
        if alt_ratio < 0.8:
            warnings.append(f"Missing alt attributes: {int((1-alt_ratio)*100)}% of images")
            score -= 5
        else:
            passed_checks.append(f"Image alt coverage OK: {int(alt_ratio*100)}%")
    else:
        warnings.append("No images on page (consider adding relevant images)")
        score -= 2

    # 6. 内部链接检查
    if internal_links < 3:
        warnings.append(f"Too few internal links: {internal_links} (recommended 3+)")
        score -= 3
    else:
        passed_checks.append(f"Internal links OK: {internal_links}")

    # 7. 结构化数据检查
    if not has_structured_data:
        warnings.append("Missing structured data (Schema.org JSON-LD)")
        score -= 5
    else:
        passed_checks.append("Structured data present")

    # 8. 技术 SEO 检查
    if not has_https:
        issues.append("HTTPS not enabled")
        score -= 15
    else:
        passed_checks.append("HTTPS enabled")

    if not is_mobile_friendly:
        issues.append("Not mobile friendly")
        score -= 10
    else:
        passed_checks.append("Mobile friendly")

    if page_load_time_ms is not None:
        if page_load_time_ms > 3000:
            issues.append(f"Page load too slow: {page_load_time_ms}ms (target < 3000ms)")
            score -= 10
        elif page_load_time_ms > 2000:
            warnings.append(f"Page load could be faster: {page_load_time_ms}ms (target < 2000ms)")
            score -= 3
        else:
            passed_checks.append(f"Page load time OK: {page_load_time_ms}ms")

    if not has_sitemap:
        warnings.append("Missing XML sitemap")
        score -= 3
    else:
        passed_checks.append("XML sitemap present")

    if not has_robots_txt:
        warnings.append("Missing robots.txt")
        score -= 2
    else:
        passed_checks.append("robots.txt present")

    # 确保分数不低于 0
    score = max(0, score)

    # 评级
    if score >= 90:
        grade = "A"
        grade_label = "Excellent"
    elif score >= 80:
        grade = "B"
        grade_label = "Good"
    elif score >= 70:
        grade = "C"
        grade_label = "Average"
    elif score >= 60:
        grade = "D"
        grade_label = "Poor"
    else:
        grade = "F"
        grade_label = "Critical"

    return {
        "page_url": page_url,
        "score": score,
        "grade": grade,
        "grade_label": grade_label,
        "issues": issues,
        "warnings": warnings,
        "passed_checks": passed_checks,
        "summary": {
            "total_checks": len(issues) + len(warnings) + len(passed_checks),
            "issues_count": len(issues),
            "warnings_count": len(warnings),
            "passed_count": len(passed_checks),
        },
        "recommendations": [
            "Fix all critical issues first",
            "Address warnings to improve score",
            "Add structured data for rich snippets",
            "Optimize page load speed",
            "Create high-quality, long-form content",
            "Build internal linking structure",
        ],
        "audited_at": datetime.utcnow().isoformat(),
    }


def get_seo_status() -> dict[str, Any]:
    """获取 SEO 基建系统状态"""
    return {
        "status": "running",
        "site_config": DEFAULT_SITE_CONFIG,
        "features": [
            "product_structured_data",
            "organization_structured_data",
            "breadcrumb_structured_data",
            "faq_structured_data",
            "xml_sitemap_generation",
            "robots_txt_generation",
            "keyword_strategy",
            "seo_audit",
        ],
        "schema_types": ["Product", "Organization", "BreadcrumbList", "FAQPage", "Offer", "AggregateRating"],
        "note": "SEO infrastructure system is ready. Supports structured data generation, XML sitemap, robots.txt, keyword strategy, and SEO audit.",
    }
