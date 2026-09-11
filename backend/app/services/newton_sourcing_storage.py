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

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
SOURCING_RESULTS_DIR = os.path.join(DATA_DIR, "newton_sourcing_results")

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
) -> dict[str, Any]:
    """
    将牛顿找品商品批量导入选品候选库

    Args:
        session: 数据库会话
        products: 商品列表（牛顿找品结果格式）
        sourcing_id: 选品批次ID
        source_query: 来源查询词
        workspace_id: 工作空间ID

    Returns:
        导入结果，包含：
        - total: 总商品数
        - imported: 成功导入数
        - skipped: 跳过数
        - errors: 错误列表
        - candidate_ids: 导入的候选ID列表
    """
    from app.services.sourcing_service import create_product_candidate

    result = {
        "total": len(products),
        "imported": 0,
        "skipped": 0,
        "errors": [],
        "candidate_ids": [],
    }

    for i, product in enumerate(products):
        try:
            # 转换牛顿商品格式为系统候选格式
            product_name = product.get("subject") or product.get("name") or f"牛顿选品商品_{i+1}"
            product_id_1688 = product.get("product_id") or product.get("ali1688_product_id", "")
            price = product.get("price") or product.get("unit_cost", 0)
            min_order = product.get("min_order_qty") or product.get("moq", 1)
            supplier = product.get("supplier") or product.get("supplier_name", "")
            detail_url = product.get("detail_url") or product.get("url", "")
            score = product.get("score", 0)
            reason = product.get("reason", "")

            # 构建候选产品数据
            candidate_data = {
                "name": product_name[:200],
                "sku": f"NEWTON_{product_id_1688 or int(time.time())}_{i}",
                "description": f"牛顿AI选品推荐。{reason}"[:500],
                "category": product.get("category", "户外用品"),
                "brand": supplier[:100] if supplier else None,
                "source_url": detail_url,
                "target_market": "US",
                "purchase_cost": float(price) if price else 0,
                "currency": "CNY",
                # 牛顿选品元数据
                "newton_score": score,
                "newton_reason": reason,
                "newton_sourcing_id": sourcing_id,
                "newton_query": source_query,
                "ali1688_product_id": str(product_id_1688),
                "min_order_qty": min_order,
            }

            # 创建选品候选
            product_obj, source_obj = await create_product_candidate(
                session=session,
                product_data=candidate_data,
                source_type=NEWTON_SOURCE_TYPE,
                source_url=detail_url or None,
                workspace_id=workspace_id,
                trace_id=f"{NEWTON_SOURCE_PREFIX}_{sourcing_id or int(time.time())}",
            )

            result["candidate_ids"].append(str(product_obj.id))
            result["imported"] += 1
            logger.info(
                "商品已导入选品候选库: id=%s, name=%s, score=%s",
                product_obj.id, product_name, score,
            )

        except Exception as e:
            result["errors"].append({
                "index": i,
                "product": product.get("subject", "unknown"),
                "error": str(e),
            })
            result["skipped"] += 1
            logger.warning("商品导入失败: index=%d, error=%s", i, str(e))

    await session.commit()
    logger.info(
        "批量导入完成: total=%d, imported=%d, skipped=%d",
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
