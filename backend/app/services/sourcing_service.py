"""
选品数据录入服务
支持人工录入、批量导入、AI 结构化分析质检、产品评分
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import (
    ProductScore,
    ProductSource,
)

logger = logging.getLogger(__name__)

# 默认工作空间 ID
DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

# 产品评分权重（M2.1 规则）
SCORE_WEIGHTS = {
    "profit": 0.30,
    "logistics": 0.20,
    "demand": 0.15,
    "competition": 0.10,
    "differentiation": 0.15,
    "compliance": 0.10,
}


def _safe_decimal(value: Any, default: float = 0.0) -> Decimal:
    """安全转换为 Decimal"""
    try:
        if value is None or value == "":
            return Decimal(str(default))
        return Decimal(str(value))
    except (ValueError, TypeError):
        return Decimal(str(default))


async def create_product_candidate(
    session: AsyncSession,
    product_data: dict[str, Any],
    source_type: str = "MANUAL",
    source_url: str | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> tuple[Product, ProductSource]:
    """
    创建产品候选（人工录入）

    Args:
        session: 数据库会话
        product_data: 产品数据
        source_type: 来源类型（1688/MANUAL/CSV/OTHER）
        source_url: 来源 URL
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        (产品对象, 产品来源对象)
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 创建产品
    product = Product(
        workspace_id=workspace_id,
        name=product_data.get("name", "Unnamed Product"),
        sku=product_data.get("sku", f"SKU-{int(time.time())}"),
        description=product_data.get("description", ""),
        category=product_data.get("category"),
        brand=product_data.get("brand"),
        status="draft",
        candidate_status="candidate",
        source=source_type.lower(),
        source_url=source_url,
        target_market=product_data.get("target_market", "US"),
    )

    # 设置可选字段
    if "weight" in product_data or "weight_kg" in product_data:
        product.weight_kg = _safe_decimal(product_data.get("weight_kg", product_data.get("weight", 0)))

    session.add(product)
    await session.flush()

    # 创建产品来源记录
    product_source = ProductSource(
        workspace_id=workspace_id,
        product_id=product.id,
        source_type=source_type,
        source_url=source_url,
        raw_data=product_data,
        trace_id=trace_id,
    )
    session.add(product_source)

    # 如果提供了成本数据，创建成本记录
    if any(key in product_data for key in ["cost_price", "purchase_cost", "domestic_shipping", "first_leg_shipping", "last_leg_shipping"]):
        from app.models.product import ProductCost
        product_cost = ProductCost(
            workspace_id=workspace_id,
            product_id=product.id,
            currency=product_data.get("currency", "USD"),
            purchase_cost=_safe_decimal(product_data.get("purchase_cost", product_data.get("cost_price", 0))),
            domestic_shipping=_safe_decimal(product_data.get("domestic_shipping", 0)),
            first_leg_shipping=_safe_decimal(product_data.get("first_leg_shipping", 0)),
            last_leg_shipping=_safe_decimal(product_data.get("last_leg_shipping", 0)),
        )
        session.add(product_cost)

    await session.flush()

    logger.info(
        "Product candidate created: id=%s, name=%s, source=%s, trace=%s",
        product.id,
        product.name,
        source_type,
        trace_id,
    )

    return product, product_source


async def batch_import_products(
    session: AsyncSession,
    products_data: list[dict[str, Any]],
    source_type: str = "CSV",
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    批量导入产品

    Args:
        session: 数据库会话
        products_data: 产品数据列表
        source_type: 来源类型
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        导入结果统计
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    results = {
        "total": len(products_data),
        "success": 0,
        "failed": 0,
        "products": [],
        "errors": [],
    }

    for index, product_data in enumerate(products_data):
        try:
            product, product_source = await create_product_candidate(
                session=session,
                product_data=product_data,
                source_type=source_type,
                workspace_id=workspace_id,
                trace_id=f"{trace_id}-{index}" if trace_id else None,
            )
            results["products"].append({
                "id": str(product.id),
                "name": product.name,
                "sku": product.sku,
                "status": "success",
            })
            results["success"] += 1
        except Exception as e:
            results["errors"].append({
                "index": index,
                "name": product_data.get("name", "Unknown"),
                "error": str(e),
            })
            results["failed"] += 1
            logger.exception("Batch import failed for product %d: %s", index, str(e))

    logger.info(
        "Batch import completed: total=%d, success=%d, failed=%d, trace=%s",
        results["total"],
        results["success"],
        results["failed"],
        trace_id,
    )

    return results


async def calculate_product_score(
    session: AsyncSession,
    product_id: UUID,
    score_data: dict[str, Any] | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> ProductScore:
    """
    计算产品评分（6 维度，0-100 分）

    Args:
        session: 数据库会话
        product_id: 产品 ID
        score_data: 评分数据（如果不提供则使用默认值）
        workspace_id: 工作空间 ID
        trace_id: 追踪 ID

    Returns:
        产品评分对象
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    # 如果提供了评分数据，使用提供的数据；否则使用默认值
    if score_data:
        profit = _safe_decimal(score_data.get("profit", 0))
        logistics = _safe_decimal(score_data.get("logistics", 0))
        demand = _safe_decimal(score_data.get("demand", 0))
        competition = _safe_decimal(score_data.get("competition", 0))
        differentiation = _safe_decimal(score_data.get("differentiation", 0))
        compliance = _safe_decimal(score_data.get("compliance", 0))
    else:
        # 默认评分（中等水平）
        profit = Decimal("5.0")
        logistics = Decimal("5.0")
        demand = Decimal("5.0")
        competition = Decimal("5.0")
        differentiation = Decimal("5.0")
        compliance = Decimal("5.0")

    # 计算加权总分
    total = (
        profit * Decimal(str(SCORE_WEIGHTS["profit"])) +
        logistics * Decimal(str(SCORE_WEIGHTS["logistics"])) +
        demand * Decimal(str(SCORE_WEIGHTS["demand"])) +
        competition * Decimal(str(SCORE_WEIGHTS["competition"])) +
        differentiation * Decimal(str(SCORE_WEIGHTS["differentiation"])) +
        compliance * Decimal(str(SCORE_WEIGHTS["compliance"]))
    ) * Decimal("10")  # 转换为 0-100 分制

    # 创建评分记录
    product_score = ProductScore(
        workspace_id=workspace_id,
        product_id=product_id,
        profit=profit,
        logistics=logistics,
        demand=demand,
        competition=competition,
        differentiation=differentiation,
        compliance=compliance,
        total=total.quantize(Decimal("0.01")),
        model_version="heuristic-v1",
        rule_version="m2.1-v1",
        trace_id=trace_id,
    )
    session.add(product_score)
    await session.flush()

    logger.info(
        "Product score calculated: product=%s, total=%.2f, trace=%s",
        product_id,
        float(total),
        trace_id,
    )

    return product_score


async def ai_quality_check(
    product_data: dict[str, Any],
) -> dict[str, Any]:
    """
    AI 结构化分析质检（简化版）

    检查产品数据的完整性、格式正确性、潜在问题

    Args:
        product_data: 产品数据

    Returns:
        质检结果
    """
    issues = []
    warnings = []
    score = 100

    # 检查必填字段
    required_fields = ["name", "sku", "retail_price", "cost_price"]
    for field in required_fields:
        if field not in product_data or not product_data[field]:
            issues.append(f"Missing required field: {field}")
            score -= 15

    # 检查价格合理性
    if "retail_price" in product_data and "cost_price" in product_data:
        retail = _safe_decimal(product_data["retail_price"])
        cost = _safe_decimal(product_data["cost_price"])
        if retail <= 0 or cost <= 0:
            issues.append("Invalid price: retail or cost price is zero or negative")
            score -= 20
        elif retail < cost:
            warnings.append("Retail price is lower than cost price (potential loss)")
            score -= 10
        elif (retail - cost) / retail < Decimal("0.2"):
            warnings.append("Low profit margin (< 20%)")
            score -= 5

    # 检查名称长度
    if "name" in product_data:
        name_length = len(product_data["name"])
        if name_length < 5:
            warnings.append("Product name is too short (< 5 characters)")
            score -= 5
        elif name_length > 200:
            warnings.append("Product name is too long (> 200 characters)")
            score -= 5

    # 检查 SKU 格式
    if product_data.get("sku"):
        sku = product_data["sku"]
        if len(sku) < 3:
            warnings.append("SKU is too short (< 3 characters)")
            score -= 3
        if " " in sku:
            warnings.append("SKU contains spaces (recommend using hyphens or underscores)")
            score -= 2

    # 检查分类
    if "category" not in product_data or not product_data["category"]:
        warnings.append("No category specified")
        score -= 5

    # 检查描述
    if "description" not in product_data or len(product_data.get("description", "")) < 20:
        warnings.append("Description is too short or missing (< 20 characters)")
        score -= 5

    # 确保分数不低于 0
    score = max(0, score)

    return {
        "passed": len(issues) == 0,
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "checks": {
            "required_fields": all(field in product_data and product_data[field] for field in required_fields),
            "price_validity": "retail_price" in product_data and "cost_price" in product_data,
            "name_quality": "name" in product_data and 5 <= len(product_data["name"]) <= 200,
            "sku_format": "sku" in product_data and len(product_data["sku"]) >= 3 and " " not in product_data["sku"],
            "category_present": "category" in product_data and product_data["category"],
            "description_quality": "description" in product_data and len(product_data["description"]) >= 20,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


async def get_product_candidates(
    session: AsyncSession,
    status: str | None = "candidate",
    workspace_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    获取产品候选列表

    Args:
        session: 数据库会话
        status: 按状态筛选
        workspace_id: 工作空间 ID
        limit: 每页数量
        offset: 偏移量

    Returns:
        产品候选列表和分页信息
    """
    if workspace_id is None:
        workspace_id = DEFAULT_WORKSPACE_ID

    query = select(Product).where(Product.workspace_id == workspace_id)

    if status:
        query = query.where(Product.status == status)

    query = query.order_by(Product.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    products = result.scalars().all()

    # 统计总数
    count_query = select(Product).where(Product.workspace_id == workspace_id)
    if status:
        count_query = count_query.where(Product.status == status)
    count_result = await session.execute(count_query)
    total = len(count_result.scalars().all())

    return {
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "status": p.status,
                "candidate_status": p.candidate_status,
                "category": p.category,
                "source": p.source,
                "weight_kg": str(p.weight_kg) if p.weight_kg else None,
                "target_market": p.target_market,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in products
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_sourcing_status() -> dict[str, Any]:
    """获取选品系统状态"""
    return {
        "status": "running",
        "source_types": ["1688", "MANUAL", "CSV", "OTHER"],
        "candidate_statuses": ["candidate", "approved", "testing", "winner", "rejected"],
        "score_dimensions": list(SCORE_WEIGHTS.keys()),
        "score_weights": SCORE_WEIGHTS,
        "score_range": "0-100",
        "ai_quality_check": "enabled",
        "note": "Product sourcing system is ready. Supports manual entry, batch import, AI quality check, and multi-dimensional scoring.",
    }
