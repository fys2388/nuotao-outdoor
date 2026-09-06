"""
WooCommerce 数据同步服务
从 WooCommerce API 获取订单、产品、客户数据，转换为系统内部格式
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "woocommerce_sync",
)

# WooCommerce API 配置（从环境变量或配置文件读取）
WC_URL = os.getenv("WOOCOMMERCE_URL", "https://nuotaooutdoor.com")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _get_wc_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
    }


def _get_wc_auth() -> tuple[str, str]:
    return (WC_CONSUMER_KEY, WC_CONSUMER_SECRET)


def fetch_woocommerce_orders(
    per_page: int = 100,
    page: int = 1,
    status: str = "any",
    date_after: str | None = None,
    date_before: str | None = None,
) -> dict[str, Any]:
    """
    从 WooCommerce 获取订单列表

    Args:
        per_page: 每页数量（最大 100）
        page: 页码
        status: 订单状态（any/pending/processing/on-hold/completed/cancelled/refunded/failed）
        date_after: 开始日期（YYYY-MM-DD）
        date_before: 结束日期（YYYY-MM-DD）

    Returns:
        订单数据和分页信息
    """
    url = f"{WC_URL}/wp-json/wc/v3/orders"
    params = {
        "per_page": min(per_page, 100),
        "page": page,
        "status": status,
    }
    if date_after:
        params["date_after"] = date_after
    if date_before:
        params["date_before"] = date_before

    try:
        response = requests.get(
            url,
            auth=_get_wc_auth(),
            headers=_get_wc_headers(),
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        orders = response.json()
        total_pages = int(response.headers.get("X-WP-TotalPages", 1))
        total_orders = int(response.headers.get("X-WP-Total", 0))

        return {
            "success": True,
            "orders": orders,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages,
                "total_orders": total_orders,
            },
        }
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch WooCommerce orders: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "orders": [],
            "pagination": {"page": page, "per_page": per_page, "total_pages": 0, "total_orders": 0},
        }


def fetch_woocommerce_order_by_id(order_id: int) -> dict[str, Any]:
    """
    根据订单ID从WooCommerce获取单个订单详情

    Args:
        order_id: WooCommerce订单ID

    Returns:
        订单详情数据
    """
    url = f"{WC_URL}/wp-json/wc/v3/orders/{order_id}"

    try:
        response = requests.get(
            url,
            auth=_get_wc_auth(),
            headers=_get_wc_headers(),
            timeout=30,
        )
        response.raise_for_status()

        order = response.json()
        return {
            "success": True,
            "order": order,
        }
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return {
                "success": False,
                "error": f"WooCommerce订单 {order_id} 不存在",
                "order": None,
            }
        logger.error("Failed to fetch WooCommerce order %s: %s", order_id, str(e))
        return {
            "success": False,
            "error": str(e),
            "order": None,
        }
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch WooCommerce order %s: %s", order_id, str(e))
        return {
            "success": False,
            "error": str(e),
            "order": None,
        }


def fetch_woocommerce_products(
    per_page: int = 100,
    page: int = 1,
    status: str = "publish",
) -> dict[str, Any]:
    """从 WooCommerce 获取产品列表"""
    url = f"{WC_URL}/wp-json/wc/v3/products"
    params = {"per_page": min(per_page, 100), "page": page, "status": status}

    try:
        response = requests.get(url, auth=_get_wc_auth(), headers=_get_wc_headers(), params=params, timeout=30)
        response.raise_for_status()
        products = response.json()
        total_pages = int(response.headers.get("X-WP-TotalPages", 1))
        total_products = int(response.headers.get("X-WP-Total", 0))

        return {
            "success": True,
            "products": products,
            "pagination": {"page": page, "per_page": per_page, "total_pages": total_pages, "total_products": total_products},
        }
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch WooCommerce products: %s", str(e))
        return {"success": False, "error": str(e), "products": [], "pagination": {"page": page, "per_page": per_page, "total_pages": 0, "total_products": 0}}


def convert_wc_order_to_internal(wc_order: dict[str, Any]) -> dict[str, Any]:
    """
    将 WooCommerce 订单转换为系统内部格式

    Args:
        wc_order: WooCommerce 订单数据

    Returns:
        系统内部格式的订单数据
    """
    line_items = wc_order.get("line_items", [])
    total_items = sum(item.get("quantity", 0) for item in line_items)
    total_amount = float(wc_order.get("total", 0))
    customer_email = wc_order.get("billing", {}).get("email", "")
    customer_id = wc_order.get("customer_id", 0)
    is_new_customer = customer_id == 0  # 简化判断：guest checkout 视为新客户

    return {
        "order_id": str(wc_order.get("id", "")),
        "order_number": wc_order.get("number", ""),
        "status": wc_order.get("status", ""),
        "currency": wc_order.get("currency", "USD"),
        "total_amount": total_amount,
        "subtotal": float(wc_order.get("subtotal", 0)),
        "total_tax": float(wc_order.get("total_tax", 0)),
        "shipping_total": float(wc_order.get("shipping_total", 0)),
        "discount_total": float(wc_order.get("discount_total", 0)),
        "items_count": total_items,
        "line_items": [
            {
                "product_id": item.get("product_id"),
                "name": item.get("name"),
                "sku": item.get("sku", ""),
                "quantity": item.get("quantity", 0),
                "price": float(item.get("price", 0)),
                "total": float(item.get("total", 0)),
            }
            for item in line_items
        ],
        "customer": {
            "customer_id": customer_id,
            "email": customer_email,
            "first_name": wc_order.get("billing", {}).get("first_name", ""),
            "last_name": wc_order.get("billing", {}).get("last_name", ""),
            "phone": wc_order.get("billing", {}).get("phone", ""),
            "country": wc_order.get("billing", {}).get("country", ""),
            "city": wc_order.get("billing", {}).get("city", ""),
        },
        "shipping_address": {
            "first_name": wc_order.get("shipping", {}).get("first_name", ""),
            "last_name": wc_order.get("shipping", {}).get("last_name", ""),
            "address_1": wc_order.get("shipping", {}).get("address_1", ""),
            "city": wc_order.get("shipping", {}).get("city", ""),
            "state": wc_order.get("shipping", {}).get("state", ""),
            "postcode": wc_order.get("shipping", {}).get("postcode", ""),
            "country": wc_order.get("shipping", {}).get("country", ""),
        },
        "payment_method": wc_order.get("payment_method", ""),
        "payment_method_title": wc_order.get("payment_method_title", ""),
        "date_created": wc_order.get("date_created", ""),
        "date_modified": wc_order.get("date_modified", ""),
        "date_completed": wc_order.get("date_completed", ""),
        "is_new_customer": is_new_customer,
    }


def sync_orders_to_dashboard(
    days: int = 30,
    max_orders: int = 500,
) -> dict[str, Any]:
    """
    同步 WooCommerce 订单到经营看板格式

    Args:
        days: 同步最近多少天的订单
        max_orders: 最大同步订单数

    Returns:
        同步结果和统计数据
    """
    _ensure_data_dir()
    now = datetime.utcnow()
    date_after = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    all_orders = []
    page = 1
    total_fetched = 0

    while total_fetched < max_orders:
        result = fetch_woocommerce_orders(
            per_page=100,
            page=page,
            status="completed",
            date_after=date_after,
        )

        if not result["success"]:
            break

        orders = result["orders"]
        if not orders:
            break

        all_orders.extend(orders)
        total_fetched += len(orders)
        page += 1

        if page > result["pagination"]["total_pages"]:
            break

    # 转换为内部格式
    internal_orders = [convert_wc_order_to_internal(order) for order in all_orders]

    # 计算统计数据
    total_revenue = sum(o["total_amount"] for o in internal_orders)
    total_orders_count = len(internal_orders)
    total_items = sum(o["items_count"] for o in internal_orders)
    avg_order_value = total_revenue / total_orders_count if total_orders_count > 0 else 0
    new_customers = sum(1 for o in internal_orders if o["is_new_customer"])
    refunded_orders = sum(1 for o in internal_orders if o["status"] == "refunded")

    # 按国家统计
    country_stats: dict[str, dict[str, Any]] = {}
    for order in internal_orders:
        country = order["customer"]["country"] or "Unknown"
        if country not in country_stats:
            country_stats[country] = {"orders": 0, "revenue": 0}
        country_stats[country]["orders"] += 1
        country_stats[country]["revenue"] += order["total_amount"]

    # 按产品统计
    product_stats: dict[str, dict[str, Any]] = {}
    for order in internal_orders:
        for item in order["line_items"]:
            sku = item["sku"] or item["name"]
            if sku not in product_stats:
                product_stats[sku] = {"name": item["name"], "quantity": 0, "revenue": 0}
            product_stats[sku]["quantity"] += item["quantity"]
            product_stats[sku]["revenue"] += item["total"]

    # 保存同步数据
    sync_id = str(uuid4())
    sync_data = {
        "id": sync_id,
        "sync_time": now.isoformat(),
        "date_range": {"start": date_after, "end": now.strftime("%Y-%m-%d")},
        "total_orders": total_orders_count,
        "total_revenue": round(total_revenue, 2),
        "total_items": total_items,
        "avg_order_value": round(avg_order_value, 2),
        "new_customers": new_customers,
        "refunded_orders": refunded_orders,
        "country_stats": country_stats,
        "top_products": sorted(product_stats.values(), key=lambda x: x["revenue"], reverse=True)[:10],
        "orders": internal_orders,
    }

    path = os.path.join(DATA_DIR, f"sync_{sync_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sync_data, f, indent=2, ensure_ascii=False, default=str)

    logger.info("WooCommerce orders synced: id=%s, orders=%d, revenue=%.2f", sync_id, total_orders_count, total_revenue)

    return {
        "success": True,
        "sync_id": sync_id,
        "total_orders": total_orders_count,
        "total_revenue": round(total_revenue, 2),
        "total_items": total_items,
        "avg_order_value": round(avg_order_value, 2),
        "new_customers": new_customers,
        "countries_count": len(country_stats),
        "products_count": len(product_stats),
        "message": f"成功同步 {total_orders_count} 个订单，总收入 ${total_revenue:,.2f}",
    }


def get_sync_status() -> dict[str, Any]:
    """获取 WooCommerce 数据同步状态"""
    return {
        "status": "ready",
        "woocommerce_url": WC_URL,
        "features": [
            "order_sync",
            "product_sync",
            "customer_sync",
            "revenue_analytics",
            "product_performance",
            "country_breakdown",
            "dashboard_integration",
        ],
        "note": "WooCommerce data sync service is ready. Syncs real order data from WooCommerce to dashboard, weekly report, and alert system.",
    }



# --------------------------------------------------------------------------- #
# 产品同步到数据库
# --------------------------------------------------------------------------- #

def convert_wc_product_to_internal(wc_product: dict[str, Any]) -> dict[str, Any]:
    """将 WooCommerce 产品转换为系统内部格式。

    Args:
        wc_product: WooCommerce 产品数据

    Returns:
        系统内部格式的产品数据
    """
    # 提取类别
    categories = wc_product.get("categories", [])
    category = categories[0].get("name", "") if categories else None

    # 提取标签
    tags = [tag.get("name", "") for tag in wc_product.get("tags", []) if tag.get("name")]

    # 提取属性
    attributes = {}
    for attr in wc_product.get("attributes", []):
        attr_name = attr.get("name", "")
        attr_options = attr.get("options", [])
        if attr_name:
            attributes[attr_name] = attr_options if len(attr_options) > 1 else attr_options[0] if attr_options else ""

    # 提取尺寸
    dimensions = wc_product.get("dimensions", {})
    dim_dict = {}
    if dimensions.get("length"):
        dim_dict["length"] = dimensions["length"]
    if dimensions.get("width"):
        dim_dict["width"] = dimensions["width"]
    if dimensions.get("height"):
        dim_dict["height"] = dimensions["height"]

    # 提取重量（WooCommerce 默认单位可能是 kg 或 g，这里假设是 kg）
    weight = wc_product.get("weight")
    weight_kg = None
    if weight:
        try:
            weight_kg = float(weight)
        except (ValueError, TypeError):
            weight_kg = None

    # 状态映射
    wc_status = wc_product.get("status", "draft")
    status_map = {
        "publish": "active",
        "draft": "draft",
        "pending": "draft",
        "private": "draft",
    }
    status = status_map.get(wc_status, "draft")

    # 元数据（价格、库存等）
    meta = {
        "woocommerce_id": wc_product.get("id"),
        "woocommerce_slug": wc_product.get("slug"),
        "price": wc_product.get("price"),
        "regular_price": wc_product.get("regular_price"),
        "sale_price": wc_product.get("sale_price"),
        "stock_quantity": wc_product.get("stock_quantity"),
        "in_stock": wc_product.get("in_stock"),
        "total_sales": wc_product.get("total_sales"),
        "average_rating": wc_product.get("average_rating"),
        "rating_count": wc_product.get("rating_count"),
        "product_type": wc_product.get("type"),
    }

    # 清理空值
    meta = {k: v for k, v in meta.items() if v is not None}

    return {
        "sku": wc_product.get("sku", f"wc-{wc_product.get('id', '')}"),
        "name": wc_product.get("name", ""),
        "description": (wc_product.get("description") or "")[:2000],
        "category": category,
        "brand": None,  # WooCommerce 默认没有品牌字段，可从 meta_data 提取
        "status": status,
        "source": "woocommerce",
        "source_url": wc_product.get("permalink"),
        "tags": tags,
        "attributes": attributes,
        "meta": meta,
        "weight_kg": weight_kg,
        "dimensions": dim_dict if dim_dict else None,
        "target_market": "US",
    }


async def sync_products_to_db(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    per_page: int = 100,
    max_pages: int | None = None,
) -> dict[str, Any]:
    """从 WooCommerce 同步产品到本地数据库（upsert by workspace + sku）。

    Args:
        session: 数据库会话
        workspace_id: 工作区 ID
        per_page: 每页获取数量
        max_pages: 最大同步页数（None 表示全部同步）

    Returns:
        同步结果统计
    """
    from app.models.product import Product
    from sqlalchemy import select

    imported = 0
    updated = 0
    failed = 0
    errors: list[str] = []
    page = 1

    while True:
        if max_pages and page > max_pages:
            break

        logger.info("同步 WooCommerce 产品: 第 %d 页", page)
        result = fetch_woocommerce_products(per_page=per_page, page=page)

        if not result.get("success"):
            error_msg = result.get("error", "未知错误")
            logger.error("获取 WooCommerce 产品失败: %s", error_msg)
            errors.append(f"第 {page} 页: {error_msg}")
            break

        products = result.get("products", [])
        if not products:
            logger.info("第 %d 页无产品，同步完成", page)
            break

        for wc_product in products:
            try:
                data = convert_wc_product_to_internal(wc_product)

                # 按 workspace + sku 查找现有产品
                existing = (
                    await session.execute(
                        select(Product).where(
                            Product.workspace_id == workspace_id,
                            Product.sku == data["sku"],
                        )
                    )
                ).scalar_one_or_none()

                if existing is None:
                    # 新建产品
                    product = Product(
                        workspace_id=workspace_id,
                        sku=data["sku"],
                        name=data["name"],
                        description=data["description"],
                        category=data["category"],
                        brand=data["brand"],
                        status=data["status"],
                        source=data["source"],
                        source_url=data["source_url"],
                        tags=data["tags"],
                        attributes=data["attributes"],
                        meta=data["meta"],
                        weight_kg=data["weight_kg"],
                        dimensions=data["dimensions"],
                        target_market=data["target_market"],
                    )
                    session.add(product)
                    imported += 1
                else:
                    # 更新产品
                    existing.name = data["name"]
                    existing.description = data["description"]
                    existing.category = data["category"]
                    existing.status = data["status"]
                    existing.source_url = data["source_url"]
                    existing.tags = data["tags"]
                    existing.attributes = data["attributes"]
                    existing.meta = data["meta"]
                    existing.weight_kg = data["weight_kg"]
                    existing.dimensions = data["dimensions"]
                    updated += 1

            except Exception as e:
                failed += 1
                error_msg = f"产品 ID {wc_product.get('id')}: {str(e)}"
                logger.error("同步产品失败: %s", error_msg)
                errors.append(error_msg)

        # 每批提交一次
        await session.commit()

        pagination = result.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    logger.info(
        "WooCommerce 产品同步完成: 新增 %d, 更新 %d, 失败 %d",
        imported, updated, failed,
    )

    return {
        "success": failed == 0,
        "imported": imported,
        "updated": updated,
        "failed": failed,
        "errors": errors,
        "total_processed": imported + updated + failed,
    }
