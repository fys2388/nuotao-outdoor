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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_intelligence import (
    ProductCostSnapshot,
    ProductScore,
    ProductSource,
    SourcingCandidate,
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

    from app.services.product_source_identity import (
        get_or_create_by_source,
        resolve_source_offer_id,
    )

    # 「同一 1688 链接不重复建档」：先按来源键命中已有候选，其次按 SKU 认领历史行。
    # 这里原先是无条件 INSERT，配合「SKU 缺省为当前秒级时间戳」，同一个 1688 链接
    # 每导入一次就多一条候选。
    source_offer_id = resolve_source_offer_id(
        source_url=source_url,
        source_id=product_data.get("source_id") or product_data.get("offer_id"),
        meta=product_data if isinstance(product_data, dict) else None,
    )
    # 有来源键时 SKU 派生为 SOP 红线格式 NT-<offer_id>（与 product_pipeline
    # _generate_sku 一致）；没有稳定标识时只能用时间戳兜底（此时确实不存在
    # 任何稳定标识可以把两次导入认成同一个商品）。
    requested_sku = product_data.get("sku") or (
        f"NT-{source_offer_id}" if source_offer_id else f"SKU-{int(time.time())}"
    )

    def _build_candidate() -> Product:
        return Product(
            workspace_id=workspace_id,
            name=product_data.get("name", "Unnamed Product"),
            sku=requested_sku,
            description=product_data.get("description", ""),
            category=product_data.get("category"),
            brand=product_data.get("brand"),
            status="draft",
            candidate_status="candidate",
            source=source_type.lower(),
            source_url=source_url,
            source_offer_id=source_offer_id,
            target_market=product_data.get("target_market", "US"),
        )

    product, created = await get_or_create_by_source(
        session,
        workspace_id=workspace_id,
        source_offer_id=source_offer_id,
        build=_build_candidate,
        fallback_sku=requested_sku,
    )

    if not created:
        # 命中同一来源的已有候选：同步本次导入的信息，而不是再建一条。
        if product_data.get("name"):
            product.name = str(product_data["name"])
        if product_data.get("description"):
            product.description = product_data["description"]
        if product_data.get("category"):
            product.category = product_data["category"]
        if product_data.get("brand"):
            product.brand = product_data["brand"]
        if source_url:
            product.source_url = source_url
        logger.info(
            "复用已有候选（同一来源）: id=%s offer=%s sku=%s",
            product.id, source_offer_id, product.sku,
        )

    # 幂等命中时把来源键补上：历史行（0069 迁移前建的）source_offer_id
    # 可能为空，补写后下次直接命中来源查重（与 get_or_create_by_source 的
    # fallback_sku 认领逻辑配合）。
    if not created and source_offer_id and not product.source_offer_id:
        product.source_offer_id = source_offer_id

    # 设置可选字段
    if "weight" in product_data or "weight_kg" in product_data:
        product.weight_kg = _safe_decimal(product_data.get("weight_kg", product_data.get("weight", 0)))

    # 设置零售价到 product.meta（用于决策流程定价检查）
    retail_price = product_data.get("retail_price")
    if retail_price:
        product.meta = dict(product.meta) if product.meta else {}
        product.meta["retail_price"] = retail_price
        product.meta["regular_price"] = retail_price
        product.meta["currency"] = "USD"
    
    # 将 1688 源图片写入 product.meta["images"]，供前端商品列表/详情展示。
    # 前端读路径：meta.media.images → meta.images → attributes.images
    images = product_data.get("images") or product_data.get("image_urls") or []
    if isinstance(images, str):
        images = [images]
    valid_images = [
        str(u).strip()
        for u in images
        if str(u).strip().startswith(("http://", "https://"))
    ]
    if valid_images:
        product.meta = dict(product.meta) if product.meta else {}
        product.meta["images"] = valid_images

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

    # 如果提供了成本数据，创建成本记录。
    # 采购单价的来源字段按优先级取：purchase_cost > cost_price > price。
    # sourcing_1688_service 的提取结果把 1688 报价放在 "price"（如 "25.80"），
    # 而本函数原先只认 purchase_cost/cost_price —— 字段名不匹配导致 1688 选品
    # 的价格被静默丢弃，永远不写 product_cost。
    purchase_cost = _safe_decimal(
        product_data.get("purchase_cost", product_data.get("cost_price", product_data.get("price", 0)))
    )
    domestic_shipping = _safe_decimal(product_data.get("domestic_shipping", 0))
    first_leg_shipping = _safe_decimal(product_data.get("first_leg_shipping", 0))
    last_leg_shipping = _safe_decimal(product_data.get("last_leg_shipping", 0))

    if purchase_cost > 0 or any(
        key in product_data
        for key in ("domestic_shipping", "first_leg_shipping", "last_leg_shipping")
    ):
        from app.models.product import ProductCost
        from app.services.product_cost_service import landed_breakdown

        # 复用 PROFIT-001 的落地成本口径，和人工录入/API upsert 保持一致。
        # 原先这里只写四个分项、不算总额，导致 total_cost 与 total_landed_cost
        # 恒为 0 —— 下游所有按总额取数的逻辑（利润、COGS、采购单确认）都失效。
        _intl, total_landed_cost, total_cost = landed_breakdown(
            purchase_cost=purchase_cost,
            domestic_shipping=domestic_shipping,
            first_leg_shipping=first_leg_shipping,
            last_leg_shipping=last_leg_shipping,
            international_shipping=None,
            packaging=Decimal("0"),
            tax_estimate=Decimal("0"),
            handling=Decimal("0"),
        )
        product_cost = ProductCost(
            workspace_id=workspace_id,
            product_id=product.id,
            currency=product_data.get("currency", "USD"),
            purchase_cost=purchase_cost,
            domestic_shipping=domestic_shipping,
            first_leg_shipping=first_leg_shipping,
            last_leg_shipping=last_leg_shipping,
            international_shipping=_intl,
            total_landed_cost=total_landed_cost,
            total_cost=total_cost,
        )
        session.add(product_cost)
        logger.info(
            "ProductCost created: product_id=%s purchase_cost=%s total_landed=%s",
            product.id, purchase_cost, total_landed_cost,
        )

    await session.flush()

    # SOP §1.5：candidate 创建必须同步 append-only 成本快照 + 供应商候选
    # （product_sourcing_candidates）+ 审计事件，全部在同一请求事务内。
    # 原先这条路径只写 product_cost，SOP 要求的产品成本快照与供应商候选
    # 始终缺失，导致验收时「product_sourcing_candidates = 0」。
    from app.services import event_service

    snapshot_id = await _append_candidate_cost_snapshot(
        session,
        workspace_id=workspace_id,
        product_id=product.id,
        product_data=product_data,
        trace_id=trace_id,
    )

    sourcing_candidate = await get_or_create_sourcing_candidate(
        session,
        workspace_id=workspace_id,
        product_id=product.id,
        source_type=source_type,
        source_url=source_url,
        title=str(product.name),
        purchase_cost=purchase_cost,
        moq=int(product_data.get("min_order_qty") or 0) or None,
        supplier_code=product_data.get("brand") or None,
        source_offer_id=source_offer_id,
        trace_id=trace_id,
    )

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.candidate.imported",
        entity_type="product",
        entity_id=str(product.id),
        payload={
            "source_type": source_type,
            "source_offer_id": source_offer_id,
            "product_id": str(product.id),
            "sourcing_candidate_id": str(sourcing_candidate.id),
            "cost_snapshot_id": str(snapshot_id),
            "created": created,
        },
        trace_id=trace_id,
        commit=False,
    )

    logger.info(
        "Product candidate created: id=%s, name=%s, source=%s, created=%s, "
        "sourcing_candidate=%s, trace=%s",
        product.id,
        product.name,
        source_type,
        created,
        sourcing_candidate.id,
        trace_id,
    )

    return product, product_source


async def _append_candidate_cost_snapshot(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    product_data: dict[str, Any],
    trace_id: str | None,
) -> UUID:
    """candidate 创建时同步写一条 append-only 成本快照（SOP §1.5）。

    只在有成本数据时落快照：purchase_cost > 0 或任一运费分项存在。
    成本数据全部缺失时不造零值快照（宁缺勿造，与 intake 口径一致），
    返回的 UUID 复用 product_id 占位，事件 payload 中可识别。
    """
    from datetime import UTC, datetime

    from app.services.product_cost_service import landed_breakdown

    purchase_cost = _safe_decimal(
        product_data.get("purchase_cost", product_data.get("cost_price", 0))
    )
    domestic_shipping = _safe_decimal(product_data.get("domestic_shipping", 0))
    first_leg_shipping = _safe_decimal(product_data.get("first_leg_shipping", 0))
    last_leg_shipping = _safe_decimal(product_data.get("last_leg_shipping", 0))

    if purchase_cost <= 0 and not any(
        value > 0
        for value in (domestic_shipping, first_leg_shipping, last_leg_shipping)
    ):
        return product_id

    _intl, total_landed_cost, total_cost = landed_breakdown(
        purchase_cost=purchase_cost,
        domestic_shipping=domestic_shipping,
        first_leg_shipping=first_leg_shipping,
        last_leg_shipping=last_leg_shipping,
        international_shipping=None,
        packaging=Decimal("0"),
        tax_estimate=Decimal("0"),
        handling=Decimal("0"),
    )

    snapshot = ProductCostSnapshot(
        workspace_id=workspace_id,
        product_id=product_id,
        currency=product_data.get("currency", "USD"),
        purchase_cost=purchase_cost,
        domestic_shipping=domestic_shipping,
        first_leg_shipping=first_leg_shipping,
        last_leg_shipping=last_leg_shipping,
        international_shipping=_intl,
        total_landed_cost=total_landed_cost,
        total_cost=total_cost,
        weight_kg=(
            _safe_decimal(
                product_data.get("weight_kg", product_data.get("weight"))
            )
            if product_data.get("weight_kg") or product_data.get("weight")
            else None
        ),
        source="sourcing_import",
        valid_from=datetime.now(UTC),
        trace_id=trace_id,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot.id


async def get_or_create_sourcing_candidate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    source_type: str,
    source_url: str | None,
    title: str,
    purchase_cost: Decimal,
    moq: int | None,
    supplier_code: str | None,
    source_offer_id: str | None,
    trace_id: str | None,
) -> SourcingCandidate:
    """为产品幂等维护一条 1688 供应商候选（SOP §1.5）。

    幂等键：``(workspace_id, product_id, source_offer_id)``——同一产品同一
    1688 来源只保留一条；重复建档时更新报价字段而不是再插一条。没有
    offer id（非 1688 来源）时退化为 ``(workspace_id, product_id)``。
    """
    query = select(SourcingCandidate).where(
        SourcingCandidate.workspace_id == workspace_id,
        SourcingCandidate.product_id == product_id,
    )
    if source_offer_id:
        # 复用 products 的来源键语义：候选行上以 notes 前缀记录来源 offer，
        # 与 product_id 一起构成稳定查重键。
        query = query.where(
            SourcingCandidate.notes == f"offer:{source_offer_id}"
        )
    else:
        query = query.where(SourcingCandidate.notes.is_(None))

    existing = (
        (await session.execute(query)).scalars().all()
    )
    if existing:
        candidate = existing[0]
        candidate.purchase_price = purchase_cost
        candidate.moq = moq or candidate.moq
        if supplier_code:
            candidate.supplier_code = supplier_code
        if source_url:
            candidate.source_url = source_url
        candidate.title = title
        candidate.trace_id = trace_id
        await session.flush()
        return candidate

    candidate = SourcingCandidate(
        workspace_id=workspace_id,
        product_id=product_id,
        source_type=source_type,
        source_url=source_url,
        title=title[:255],
        status="candidate",
        purchase_price=purchase_cost,
        moq=moq,
        supplier_code=supplier_code,
        notes=f"offer:{source_offer_id}" if source_offer_id else None,
        trace_id=trace_id,
    )
    session.add(candidate)
    await session.flush()
    return candidate


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
            # savepoint 隔离：单条失败只回滚本条，不拖垮后续条目。
            async with session.begin_nested():
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
                "source_offer_id": product.source_offer_id,
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

    query = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.candidate_status.isnot(None),
        Product.deleted_at.is_(None),
    )

    if status and status != "all":
        query = query.where(Product.candidate_status == status)

    query = query.order_by(Product.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    products = result.scalars().all()

    # 统计总数
    count_query = select(func.count(Product.id)).where(
        Product.workspace_id == workspace_id,
        Product.candidate_status.isnot(None),
        Product.deleted_at.is_(None),
    )
    if status and status != "all":
        count_query = count_query.where(Product.candidate_status == status)
    total = int((await session.execute(count_query)).scalar_one())

    product_ids = [product.id for product in products]
    latest_scores: dict[UUID, ProductScore] = {}
    latest_costs: dict[UUID, ProductCostSnapshot] = {}

    if product_ids:
        score_rows = (
            (
                await session.execute(
                    select(ProductScore)
                    .where(
                        ProductScore.workspace_id == workspace_id,
                        ProductScore.product_id.in_(product_ids),
                    )
                    .order_by(ProductScore.product_id, ProductScore.scored_at.desc())
                )
            )
            .scalars()
            .all()
        )
        for score in score_rows:
            latest_scores.setdefault(score.product_id, score)

        cost_rows = (
            (
                await session.execute(
                    select(ProductCostSnapshot)
                    .where(
                        ProductCostSnapshot.workspace_id == workspace_id,
                        ProductCostSnapshot.product_id.in_(product_ids),
                    )
                    .order_by(
                        ProductCostSnapshot.product_id,
                        ProductCostSnapshot.valid_from.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        for cost in cost_rows:
            latest_costs.setdefault(cost.product_id, cost)

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
                "source_url": p.source_url,
                "description": p.description,
                "attributes": p.attributes or {},
                "dimensions": p.dimensions,
                "meta": p.meta or {},
                "weight_kg": str(p.weight_kg) if p.weight_kg else None,
                "target_market": p.target_market,
                "latest_score": (
                    {
                        "id": str(latest_scores[p.id].id),
                        "total": str(latest_scores[p.id].total),
                        "profit": str(latest_scores[p.id].profit),
                        "logistics": str(latest_scores[p.id].logistics),
                        "demand": str(latest_scores[p.id].demand),
                        "competition": str(latest_scores[p.id].competition),
                        "differentiation": str(latest_scores[p.id].differentiation),
                        "compliance": str(latest_scores[p.id].compliance),
                        "model_version": latest_scores[p.id].model_version,
                        "rule_version": latest_scores[p.id].rule_version,
                        "scored_at": latest_scores[p.id].scored_at.isoformat(),
                    }
                    if p.id in latest_scores
                    else None
                ),
                "latest_cost": (
                    {
                        "id": str(latest_costs[p.id].id),
                        "currency": latest_costs[p.id].currency,
                        "purchase_cost": str(latest_costs[p.id].purchase_cost),
                        "total_landed_cost": str(latest_costs[p.id].total_landed_cost),
                        "total_cost": str(latest_costs[p.id].total_cost),
                        "version": latest_costs[p.id].version,
                        "valid_from": latest_costs[p.id].valid_from.isoformat(),
                    }
                    if p.id in latest_costs
                    else None
                ),
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
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
