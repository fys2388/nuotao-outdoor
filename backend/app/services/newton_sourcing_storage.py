"""
牛顿选品结果入库服务

将牛顿AI找品结果自动写入系统选品候选库，对接现有选品流程。
支持：
- 批量导入牛顿找品商品到选品候选库
- 查询牛顿来源的选品候选
- 选品候选统计
- 选品结果持久化（JSON文件 + 数据库）

遵循AGENTS.md规范：
- 业务规则集中在服务层
- Agent禁止直连数据库，通过services层访问
- 全链路可审计
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.services.product_source_identity import (
    resolve_source_offer_id,
)
from app.services.sourcing_service import create_product_candidate

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
SOURCING_RESULTS_DIR = os.path.join(DATA_DIR, "newton_sourcing_results")

# 1688 报价为人民币，入库统一换算为美元（与候选行的 currency="USD" 保持一致）。
# 与 evaluation_context._DEFAULT_CNY_USD_RATE 同口径。
_CNY_TO_USD = 0.14

# 牛顿来源标识
NEWTON_SOURCE_TYPE = "1688"
NEWTON_SOURCE_PREFIX = "newton_ai"


def _ensure_dirs() -> None:
    """确保数据目录存在"""
    os.makedirs(SOURCING_RESULTS_DIR, exist_ok=True)


def save_sourcing_result(
    query: str,
    products: list[dict[str, Any]],
    summary: str = "",
    task_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    保存牛顿选品结果到JSON文件

    Args:
        query: 找品查询词
        products: 商品列表
        summary: AI总结
        task_id: 牛顿Agent任务ID
        metadata: 额外元数据

    Returns:
        保存的文件路径
    """
    _ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"newton_sourcing_{timestamp}.json"
    filepath = os.path.join(SOURCING_RESULTS_DIR, filename)

    result = {
        "sourcing_id": f"NS_{timestamp}",
        "query": query,
        "task_id": task_id,
        "summary": summary,
        "total": len(products),
        "products": products,
        "created_at": datetime.now().isoformat(),
        "metadata": metadata or {},
    }

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("选品结果已保存: %s (%d个商品)", filepath, len(products))
    except IOError as e:
        logger.error("保存选品结果失败: %s", str(e))

    return filepath


def load_sourcing_results(limit: int = 20) -> list[dict[str, Any]]:
    """
    加载历史选品结果列表

    Args:
        limit: 返回条数

    Returns:
        选品结果列表（按时间倒序）
    """
    if not os.path.exists(SOURCING_RESULTS_DIR):
        return []

    files = sorted(
        [f for f in os.listdir(SOURCING_RESULTS_DIR) if f.endswith(".json")],
        reverse=True,
    )[:limit]

    results = []
    for filename in files:
        filepath = os.path.join(SOURCING_RESULTS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                results.append({
                    "sourcing_id": data.get("sourcing_id"),
                    "query": data.get("query"),
                    "total": data.get("total", 0),
                    "created_at": data.get("created_at"),
                    "task_id": data.get("task_id"),
                    "filename": filename,
                })
        except (json.JSONDecodeError, IOError):
            continue

    return results


def load_sourcing_result_by_id(sourcing_id: str) -> dict[str, Any] | None:
    """
    根据选品ID加载详细结果

    Args:
        sourcing_id: 选品ID（如 NS_20260904_180000）

    Returns:
        选品结果详情，不存在返回None
    """
    if not os.path.exists(SOURCING_RESULTS_DIR):
        return None

    # sourcing_id格式: NS_YYYYMMDD_HHMMSS
    timestamp_part = sourcing_id.replace("NS_", "")
    filename = f"newton_sourcing_{timestamp_part}.json"
    filepath = os.path.join(SOURCING_RESULTS_DIR, filename)

    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


async def import_products_to_candidates(
    session: AsyncSession,
    products: list[dict[str, Any]],
    sourcing_id: str = "",
    source_query: str = "",
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    将牛顿找品商品批量导入选品候选库

    事务边界：本 service 只做 flush 与 savepoint 隔离，**不 commit**——
    由调用方（端点）独占 commit/rollback，保证「API 成功 = 事务已提交」。

    Args:
        session: 数据库会话
        products: 商品列表（牛顿找品结果格式）
        sourcing_id: 选品批次ID
        source_query: 来源查询词
        workspace_id: 工作空间ID
        trace_id: 全链路追踪 ID（写入 product_sources / event_log）

    Returns:
        导入结果，包含：
        - total: 总商品数
        - imported: 成功导入数
        - skipped: 跳过数
        - errors: 错误列表
        - candidate_ids: 导入的候选ID列表
        - items: 逐条结果（product_id / candidate_id / source_offer_id / status）
    """
    result = {
        "total": len(products),
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "candidate_ids": [],
        "items": [],
    }

    ws_id = workspace_id or DEFAULT_WORKSPACE_ID

    for i, product in enumerate(products):
        # 转换牛顿商品格式为系统候选格式
        product_name = product.get("subject") or product.get("name") or f"牛顿选品商品_{i+1}"
        product_id_1688 = product.get("product_id") or product.get("ali1688_product_id", "")
        price = product.get("price") or product.get("unit_cost", 0)
        min_order = product.get("min_order_qty") or product.get("moq", 1)
        supplier = product.get("supplier") or product.get("supplier_name", "")
        detail_url = product.get("detail_url") or product.get("url", "")
        score = product.get("score", 0)
        reason = product.get("reason", "")
        images = [
            str(u).strip()
            for u in (product.get("images") or product.get("image_urls") or [])
            if str(u).strip().startswith(("http://", "https://"))
        ]

        # 构建候选产品数据
        # 1688 报价是人民币：必须先把采购价也换算成美元，否则 CNY 数值会被
        # 当作 USD 参与成本/利润率计算（下游只看 currency 字段），导致
        # 落地成本虚高、V10 利润率否决对每个候选都误触发。
        purchase_cost_cny = float(price) if price else 0
        purchase_cost = round(purchase_cost_cny * _CNY_TO_USD, 2)
        # 基于采购价计算建议零售价（采购价 * 3 倍，最低 $5）
        retail_price_usd = max(round(purchase_cost * 3, 2), 5.0)
        
        candidate_data = {
            "name": product_name[:200],
            # 有 1688 商品 ID 时 SKU 由 create_product_candidate 按 SOP 红线
            # NT-<offer_id> 统一派生（跨路径同 offer 同 SKU）；这里不再自带
            # NEWTON_ 前缀，避免与 pipeline 路径的 NT- SKU 分裂。
            "description": f"牛顿AI选品推荐。{reason}"[:500],
            "category": product.get("category", "户外用品"),
            "brand": supplier[:100] if supplier else None,
            "source_url": detail_url,
            "target_market": "US",
            "purchase_cost": purchase_cost,
            "currency": "USD",
            # 零售价（用于决策流程定价检查）
            "retail_price": retail_price_usd,
            # 牛顿选品元数据
            "newton_score": score,
            "newton_reason": reason,
            "newton_sourcing_id": sourcing_id,
            "newton_query": source_query,
            "ali1688_product_id": str(product_id_1688),
            # 显式来源键：让 create_product_candidate 能按 1688 offer 幂等建档
            # （来源键查重；SKU 由 service 按 NT-<offer_id> 统一派生）。
            "source_id": str(product_id_1688) if product_id_1688 else None,
            "min_order_qty": min_order,
            "images": images,
        }

        # 来源键解析（与 create_product_candidate 内部口径一致）：
        # 幂等预检与逐条结果回传都按 source_offer_id，而不是 SKU 字符串。
        offer_id = resolve_source_offer_id(
            source_url=detail_url or None,
            source_id=str(product_id_1688) if product_id_1688 else None,
        )

        # 幂等预检：同来源键已入库则复用既有候选（真正的并发防线是
        # get_or_create_by_source 的 DB 唯一索引，这里只是提前短路）。
        if offer_id:
            existing = (
                await session.execute(
                    select(Product).where(
                        Product.source_offer_id == offer_id,
                        Product.workspace_id == ws_id,
                        Product.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                result["skipped"] += 1
                result["candidate_ids"].append(str(existing.id))
                result["items"].append({
                    "index": i,
                    "status": "exists",
                    "product_id": str(existing.id),
                    "source_offer_id": offer_id,
                })
                logger.info(
                    "商品已存在（来源键命中），复用既有候选: offer=%s, id=%s",
                    offer_id, existing.id,
                )
                continue

        try:
            # 创建选品候选。整条记录包在 savepoint（begin_nested）里：
            # 本条任何 IntegrityError/业务异常只回滚到 savepoint，
            # 不再把整批（含此前已成功的条目）一并撤销——原先直接
            # session.rollback() 会让「16 条里 1 条失败 → 15 条全丢」。
            async with session.begin_nested():
                product_obj, source_obj = await create_product_candidate(
                    session=session,
                    product_data=candidate_data,
                    source_type=NEWTON_SOURCE_TYPE,
                    source_url=detail_url or None,
                    workspace_id=workspace_id,
                    trace_id=f"{NEWTON_SOURCE_PREFIX}_{sourcing_id or int(time.time())}_{trace_id or ''}".rstrip("_"),
                )

            result["candidate_ids"].append(str(product_obj.id))
            result["imported"] += 1
            result["items"].append({
                "index": i,
                "status": "created",
                "product_id": str(product_obj.id),
                "source_offer_id": product_obj.source_offer_id,
            })
            logger.info(
                "商品已导入选品候选库: id=%s, offer=%s, name=%s, score=%s",
                product_obj.id, product_obj.source_offer_id, product_name, score,
            )

        except IntegrityError:
            # 并发写入导致的重复：savepoint 已回滚本条，按来源键回查复用。
            fallback = None
            if offer_id:
                fallback = (
                    await session.execute(
                        select(Product).where(
                            Product.source_offer_id == offer_id,
                            Product.workspace_id == ws_id,
                            Product.deleted_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
            if fallback is not None:
                result["skipped"] += 1
                result["candidate_ids"].append(str(fallback.id))
                result["items"].append({
                    "index": i,
                    "status": "exists",
                    "product_id": str(fallback.id),
                    "source_offer_id": offer_id,
                })
            else:
                result["skipped"] += 1
                result["errors"].append({
                    "index": i,
                    "product": product_name,
                    "error": "来源键冲突且回查失败，本条已跳过",
                })
                result["items"].append({
                    "index": i,
                    "status": "failed",
                    "source_offer_id": offer_id,
                })
            logger.warning(
                "商品已存在（唯一约束冲突），跳过: index=%d, offer=%s",
                i, offer_id,
            )
        except Exception as e:
            # 单条业务失败：savepoint 回滚本条，不影响其他条目。
            result["errors"].append({
                "index": i,
                "product": product_name,
                "error": "商品导入失败，已回滚，不影响其他条目",
            })
            result["skipped"] += 1
            result["items"].append({
                "index": i,
                "status": "failed",
                "source_offer_id": offer_id,
            })
            logger.warning(
                "商品导入失败: index=%d, offer=%s, error=%s",
                i, offer_id, str(e),
            )

    # 事务边界：service 只 flush，不 commit。commit 由端点独占，
    # 保证「API 成功 = 数据库事务已提交」。
    logger.info(
        "批量导入完成（未提交，等待端点 commit）: total=%d, imported=%d, skipped=%d",
        result["total"], result["imported"], result["skipped"],
    )
    return result


async def list_newton_candidates(
    session: AsyncSession,
    status: str | None = "candidate",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    查询牛顿来源的选品候选列表

    Args:
        session: 数据库会话
        status: 候选状态筛选
        limit: 每页条数
        offset: 偏移量

    Returns:
        选品候选列表和分页信息
    """
    from app.models.product import Product

    query = select(Product).where(
        Product.source == "1688",
        Product.candidate_status.isnot(None),
    )

    if status:
        query = query.where(Product.candidate_status == status)

    query = query.order_by(Product.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    products = result.scalars().all()

    candidates = []
    for p in products:
        candidates.append({
            "id": str(p.id),
            "name": p.name,
            "sku": p.sku,
            "category": p.category,
            "status": p.status,
            "candidate_status": p.candidate_status,
            "source": p.source,
            "source_url": p.source_url,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {
        "candidates": candidates,
        "total": len(candidates),
        "limit": limit,
        "offset": offset,
    }


async def get_newton_candidate_stats(
    session: AsyncSession,
) -> dict[str, Any]:
    """
    获取牛顿选品候选统计

    Args:
        session: 数据库会话

    Returns:
        统计信息
    """
    from app.models.product import Product
    from sqlalchemy import func

    # 按状态统计
    query = select(
        Product.candidate_status,
        func.count(Product.id),
    ).where(
        Product.source == "1688",
        Product.candidate_status.isnot(None),
    ).group_by(Product.candidate_status)

    result = await session.execute(query)
    rows = result.all()

    by_status = {row[0]: row[1] for row in rows if row[0]}
    total = sum(by_status.values())

    return {
        "total_candidates": total,
        "by_status": by_status,
        "source": "1688 (牛顿AI选品)",
    }
