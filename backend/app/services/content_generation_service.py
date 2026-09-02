"""
内容生成系统服务
支持产品卖点、SEO 文章、EDM 营销邮件的批量生成和审核流程
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# 内容数据存储路径
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "content",
)

# 内容类型
CONTENT_TYPES = [
    "product_selling_points",  # 产品卖点
    "seo_article",             # SEO 文章
    "edm_abandoned_cart",     # 弃购挽回邮件
    "edm_repurchase",          # 复购营销邮件
    "product_description",     # 产品描述
    "ad_copy",                 # 广告文案
]

# 审核状态
CONTENT_STATUSES = [
    "draft",      # 草稿
    "pending",    # 待审核
    "approved",   # 已通过
    "rejected",   # 已拒绝
    "published",  # 已发布
]

# 内容质量检查规则
QUALITY_RULES = {
    "min_title_length": 10,
    "max_title_length": 120,
    "min_description_length": 50,
    "max_description_length": 500,
    "min_keywords": 3,
    "max_keywords": 10,
    "forbidden_words": ["best", "cheapest", "guaranteed", "100%", "miracle"],
}


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_content_path(content_id: str) -> str:
    """获取内容数据文件路径"""
    return os.path.join(DATA_DIR, f"{content_id}.json")


def _load_content(content_id: str) -> dict[str, Any] | None:
    """加载内容数据"""
    path = _get_content_path(content_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load content %s: %s", content_id, str(e))
        return None


def _save_content(content: dict[str, Any]) -> None:
    """保存内容数据"""
    _ensure_data_dir()
    path = _get_content_path(content["id"])
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save content %s: %s", content["id"], str(e))


def generate_selling_points(
    product_name: str,
    product_category: str = "",
    key_features: list[str] | None = None,
    target_audience: str = "outdoor enthusiasts",
    price: float | None = None,
) -> dict[str, Any]:
    """
    生成产品卖点

    Args:
        product_name: 产品名称
        product_category: 产品分类
        key_features: 核心特性列表
        target_audience: 目标受众
        price: 价格

    Returns:
        卖点内容
    """
    if key_features is None:
        key_features = []

    # 基于模板生成卖点
    bullet_points = []

    # 特性卖点
    for i, feature in enumerate(key_features[:5]):
        templates = [
            f"✓ {feature} - Designed for {target_audience}",
            f"✓ Premium {feature} for enhanced performance",
            f"✓ {feature} - Built to last in any condition",
        ]
        bullet_points.append(templates[i % len(templates)])

    # 如果没有提供特性，生成通用卖点
    if not bullet_points:
        bullet_points = [
            f"✓ Premium quality {product_category.lower()} for {target_audience}",
            f"✓ Durable construction built for outdoor adventures",
            f"✓ Lightweight and portable design for easy transport",
            f"✓ Versatile performance in various weather conditions",
            f"✓ Backed by our quality guarantee and customer support",
        ]

    # 生成标题
    title = f"{product_name} - Premium {product_category} for {target_audience.title()}"

    # 生成简短描述
    description = (
        f"Discover the {product_name}, a premium {product_category.lower()} designed specifically for "
        f"{target_audience}. Featuring {'、'.join(key_features[:3]) if key_features else 'exceptional quality and durability'}, "
        f"this product delivers outstanding performance in any outdoor environment."
    )

    # 生成价值主张
    value_proposition = (
        f"Experience the perfect blend of quality, performance, and value with the {product_name}. "
        f"Whether you're a seasoned adventurer or just starting out, this {product_category.lower()} "
        f"is designed to exceed your expectations."
    )

    return {
        "title": title,
        "bullet_points": bullet_points,
        "description": description,
        "value_proposition": value_proposition,
        "target_audience": target_audience,
        "price": price,
    }


def generate_seo_content(
    product_name: str,
    product_category: str = "",
    keywords: list[str] | None = None,
    target_audience: str = "outdoor enthusiasts",
) -> dict[str, Any]:
    """
    生成 SEO 内容

    Args:
        product_name: 产品名称
        product_category: 产品分类
        keywords: 关键词列表
        target_audience: 目标受众

    Returns:
        SEO 内容
    """
    if keywords is None:
        # 生成默认关键词
        keywords = [
            f"best {product_category.lower()}",
            f"{product_name.lower()} review",
            f"{product_category.lower()} for {target_audience}",
            f"buy {product_name.lower()}",
            f"{product_category.lower()} buying guide",
        ]

    # 生成 SEO 标题
    seo_title = f"{product_name} Review: Best {product_category} for {target_audience.title()} in 2026"

    # 生成 Meta 描述
    meta_description = (
        f"Looking for the best {product_category.lower()}? Read our comprehensive {product_name} review. "
        f"Discover why {target_audience} love this {product_category.lower()}. Features, specs, pricing, and more."
    )

    # 生成文章大纲
    article_outline = [
        "Introduction: Why This Product Matters",
        f"Product Overview: What is the {product_name}?",
        "Key Features and Specifications",
        "Performance and Durability Testing",
        f"Who Should Buy This {product_category}?",
        "Pros and Cons",
        "Comparison with Alternatives",
        "Pricing and Value for Money",
        "Customer Reviews and Feedback",
        "Final Verdict and Recommendation",
    ]

    # 生成正文段落
    paragraphs = [
        f"When it comes to finding the perfect {product_category.lower()}, the {product_name} stands out as a top choice for {target_audience}. In this comprehensive review, we'll explore everything you need to know about this exceptional product.",
        f"The {product_name} is designed with {target_audience} in mind, offering a perfect balance of performance, durability, and value. Whether you're tackling challenging trails or enjoying a weekend getaway, this {product_category.lower()} delivers consistent results.",
        f"One of the standout features of the {product_name} is its exceptional build quality. Constructed from premium materials, this {product_category.lower()} is built to withstand the rigors of outdoor use while maintaining its performance over time.",
        f"In terms of value for money, the {product_name} offers an impressive package. Compared to other {product_category.lower()}s in its class, it provides superior features and performance at a competitive price point.",
    ]

    return {
        "seo_title": seo_title,
        "meta_description": meta_description,
        "keywords": keywords,
        "article_outline": article_outline,
        "paragraphs": paragraphs,
        "word_count": sum(len(p.split()) for p in paragraphs),
        "target_audience": target_audience,
    }


def generate_edm_content(
    email_type: str,
    customer_name: str = "Valued Customer",
    product_name: str = "",
    product_category: str = "",
    discount_percent: int = 10,
    abandoned_cart_value: float | None = None,
) -> dict[str, Any]:
    """
    生成 EDM 营销邮件内容

    Args:
        email_type: 邮件类型（abandoned_cart/repurchase/welcome）
        customer_name: 客户名称
        product_name: 产品名称
        product_category: 产品分类
        discount_percent: 折扣百分比
        abandoned_cart_value: 弃购购物车价值

    Returns:
        EDM 邮件内容
    """
    if email_type == "abandoned_cart":
        # 弃购挽回邮件
        subject = f"Hi {customer_name}, you left something in your cart!"
        preview_text = f"Your {product_category or 'items'} are waiting. Complete your order and get {discount_percent}% off!"
        body = [
            f"Hi {customer_name},",
            f"We noticed you left some items in your shopping cart. Don't miss out on the {product_name or 'products'} you were interested in!",
            f"As a special offer, use code WELCOMEBACK{discount_percent} to get {discount_percent}% off your order today.",
            "Your cart is saved and ready for checkout. Simply click the link below to complete your purchase.",
            "If you have any questions, our customer support team is here to help.",
            "Happy shopping!",
            "The Nuotao Outdoor Team",
        ]
        cta_button = "Complete Your Purchase"
        urgency = "This offer expires in 48 hours. Don't wait!"

    elif email_type == "repurchase":
        # 复购营销邮件
        subject = f"Hi {customer_name}, time to restock your favorites!"
        preview_text = f"Your favorite {product_category or 'products'} are back in stock. Get {discount_percent}% off on your next order!"
        body = [
            f"Hi {customer_name},",
            f"We hope you're enjoying your {product_name or 'purchase'}! As a valued customer, we wanted to let you know that your favorite items are back in stock.",
            f"To show our appreciation, use code REPEAT{discount_percent} for {discount_percent}% off your next order.",
            "Whether you need a replacement, an upgrade, or just want to try something new, now is the perfect time.",
            "Browse our latest collection and discover your next favorite outdoor gear.",
            "Best regards,",
            "The Nuotao Outdoor Team",
        ]
        cta_button = "Shop Now and Save"
        urgency = "Limited time offer. Stock is limited!"

    else:
        # 欢迎邮件（默认）
        subject = f"Welcome to Nuotao Outdoor, {customer_name}!"
        preview_text = f"Get {discount_percent}% off your first order. Discover premium outdoor gear for every adventure."
        body = [
            f"Hi {customer_name},",
            "Welcome to Nuotao Outdoor! We're thrilled to have you join our community of outdoor enthusiasts.",
            f"As a welcome gift, use code NEWCOMER{discount_percent} for {discount_percent}% off your first order.",
            "Explore our collection of premium outdoor gear, carefully selected for quality, performance, and value.",
            "From camping essentials to hiking gear, we've got everything you need for your next adventure.",
            "If you have any questions, our team is always here to help.",
            "Happy adventuring!",
            "The Nuotao Outdoor Team",
        ]
        cta_button = "Start Shopping"
        urgency = ""

    return {
        "email_type": email_type,
        "subject": subject,
        "preview_text": preview_text,
        "body": body,
        "cta_button": cta_button,
        "urgency": urgency,
        "discount_percent": discount_percent,
        "abandoned_cart_value": abandoned_cart_value,
    }


def create_content_item(
    content_type: str,
    title: str,
    content_data: dict[str, Any],
    product_id: str | None = None,
    product_name: str = "",
    created_by: str = "system",
) -> dict[str, Any]:
    """
    创建内容项

    Args:
        content_type: 内容类型
        title: 标题
        content_data: 内容数据
        product_id: 关联产品 ID
        product_name: 关联产品名称
        created_by: 创建者

    Returns:
        内容项
    """
    now = datetime.utcnow()
    content_id = str(uuid4())

    content_item = {
        "id": content_id,
        "content_type": content_type,
        "title": title,
        "content": content_data,
        "product_id": product_id,
        "product_name": product_name,
        "status": "draft",
        "created_by": created_by,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "review_history": [],
        "quality_score": None,
        "quality_issues": [],
    }

    # 自动质量检查
    quality_result = check_content_quality(content_item)
    content_item["quality_score"] = quality_result["score"]
    content_item["quality_issues"] = quality_result["issues"]

    _save_content(content_item)
    logger.info("Content created: id=%s, type=%s, title=%s, quality=%.1f", content_id, content_type, title, quality_result["score"])
    return content_item


def check_content_quality(content_item: dict[str, Any]) -> dict[str, Any]:
    """
    检查内容质量

    Args:
        content_item: 内容项

    Returns:
        质量检查结果
    """
    issues = []
    score = 100

    content = content_item.get("content", {})
    title = content_item.get("title", "")

    # 检查标题长度
    if len(title) < QUALITY_RULES["min_title_length"]:
        issues.append(f"Title too short: {len(title)} chars (min {QUALITY_RULES['min_title_length']})")
        score -= 10
    elif len(title) > QUALITY_RULES["max_title_length"]:
        issues.append(f"Title too long: {len(title)} chars (max {QUALITY_RULES['max_title_length']})")
        score -= 5

    # 检查禁用词
    title_lower = title.lower()
    for word in QUALITY_RULES["forbidden_words"]:
        if word in title_lower:
            issues.append(f"Forbidden word in title: '{word}'")
            score -= 15

    # 检查内容类型特定的质量
    content_type = content_item.get("content_type", "")

    if content_type == "seo_article":
        keywords = content.get("keywords", [])
        if len(keywords) < QUALITY_RULES["min_keywords"]:
            issues.append(f"Too few keywords: {len(keywords)} (min {QUALITY_RULES['min_keywords']})")
            score -= 10

        word_count = content.get("word_count", 0)
        if word_count < 200:
            issues.append(f"Article too short: {word_count} words (min 200)")
            score -= 10

    elif content_type in ["edm_abandoned_cart", "edm_repurchase"]:
        if not content.get("cta_button"):
            issues.append("Missing CTA button")
            score -= 10
        if not content.get("subject"):
            issues.append("Missing email subject")
            score -= 10

    elif content_type == "product_selling_points":
        bullet_points = content.get("bullet_points", [])
        if len(bullet_points) < 3:
            issues.append(f"Too few bullet points: {len(bullet_points)} (min 3)")
            score -= 10

    # 确保分数不低于 0
    score = max(0, score)

    return {
        "score": score,
        "issues": issues,
        "passed": len(issues) == 0,
    }


def submit_for_review(content_id: str, submitted_by: str = "system") -> dict[str, Any]:
    """
    提交内容审核

    Args:
        content_id: 内容 ID
        submitted_by: 提交者

    Returns:
        更新后的内容项
    """
    content = _load_content(content_id)
    if not content:
        raise ValueError(f"Content not found: {content_id}")

    if content["status"] not in ["draft", "rejected"]:
        raise ValueError(f"Content cannot be submitted for review in current status: {content['status']}")

    now = datetime.utcnow()
    content["status"] = "pending"
    content["updated_at"] = now.isoformat()
    content["review_history"].append({
        "action": "submitted",
        "by": submitted_by,
        "timestamp": now.isoformat(),
        "comment": "Submitted for review",
    })

    _save_content(content)
    logger.info("Content submitted for review: id=%s, by=%s", content_id, submitted_by)
    return content


def review_content(
    content_id: str,
    action: str,
    reviewer: str = "admin",
    comment: str = "",
) -> dict[str, Any]:
    """
    审核内容

    Args:
        content_id: 内容 ID
        action: 审核动作（approve/reject）
        reviewer: 审核者
        comment: 审核评论

    Returns:
        更新后的内容项
    """
    content = _load_content(content_id)
    if not content:
        raise ValueError(f"Content not found: {content_id}")

    if content["status"] != "pending":
        raise ValueError(f"Content is not pending review: {content['status']}")

    now = datetime.utcnow()

    if action == "approve":
        content["status"] = "approved"
    elif action == "reject":
        content["status"] = "rejected"
    else:
        raise ValueError(f"Invalid review action: {action}. Must be 'approve' or 'reject'")

    content["updated_at"] = now.isoformat()
    content["review_history"].append({
        "action": action,
        "by": reviewer,
        "timestamp": now.isoformat(),
        "comment": comment,
    })

    _save_content(content)
    logger.info("Content reviewed: id=%s, action=%s, by=%s", content_id, action, reviewer)
    return content


def list_content_items(
    content_type: str | None = None,
    status: str | None = None,
    product_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    获取内容列表

    Args:
        content_type: 按内容类型筛选
        status: 按状态筛选
        product_id: 按产品筛选
        limit: 返回数量限制

    Returns:
        内容列表和统计
    """
    _ensure_data_dir()

    items = []
    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
                item = json.load(f)

            # 筛选
            if content_type and item.get("content_type") != content_type:
                continue
            if status and item.get("status") != status:
                continue
            if product_id and item.get("product_id") != product_id:
                continue

            items.append(item)
        except Exception as e:
            logger.warning("Failed to load content file %s: %s", filename, str(e))

    # 按更新时间排序
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    items = items[:limit]

    # 统计
    stats = {
        "total": len(items),
        "by_type": {},
        "by_status": {},
        "average_quality": 0,
    }

    quality_scores = []
    for item in items:
        content_type = item.get("content_type", "unknown")
        item_status = item.get("status", "unknown")
        stats["by_type"][content_type] = stats["by_type"].get(content_type, 0) + 1
        stats["by_status"][item_status] = stats["by_status"].get(item_status, 0) + 1
        if item.get("quality_score") is not None:
            quality_scores.append(item["quality_score"])

    if quality_scores:
        stats["average_quality"] = sum(quality_scores) / len(quality_scores)

    return {
        "items": items,
        "stats": stats,
    }


def get_content_generation_status() -> dict[str, Any]:
    """获取内容生成系统状态"""
    return {
        "status": "running",
        "content_types": CONTENT_TYPES,
        "content_statuses": CONTENT_STATUSES,
        "quality_rules": QUALITY_RULES,
        "features": [
            "selling_points_generation",
            "seo_content_generation",
            "edm_email_generation",
            "batch_generation",
            "quality_check",
            "review_workflow",
        ],
        "workflow": "Generate content → Quality check → Draft → Submit for review → Approve/Reject → Publish",
        "note": "Content generation system is ready. Supports product selling points, SEO articles, EDM emails, batch generation, and human-in-the-loop review workflow.",
    }
