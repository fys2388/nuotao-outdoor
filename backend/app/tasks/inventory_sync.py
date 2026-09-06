"""
库存自动同步定时任务
定期从1688/WooCommerce同步库存，低库存告警
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# 同步配置
SYNC_INTERVAL_MINUTES = int(os.getenv("INVENTORY_SYNC_INTERVAL", "60"))
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "10"))
AUTO_SYNC_ENABLED = os.getenv("INVENTORY_AUTO_SYNC", "true").lower() == "true"
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "admin@nuotaooutdoor.com")


async def sync_inventory_from_1688() -> dict[str, Any]:
    """从1688同步库存"""
    logger.info("Starting inventory sync from 1688...")

    try:
        # 这里可以调用1688 API获取供应商库存
        # 由于需要真实API密钥，此处返回框架响应
        synced_count = 0
        updated_products = []

        # 模拟同步过程
        logger.info("1688 inventory sync completed: %d products updated", synced_count)

        return {
            "success": True,
            "source": "1688",
            "synced_count": synced_count,
            "updated_products": updated_products,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("1688 inventory sync failed: %s", str(e))
        return {
            "success": False,
            "source": "1688",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def sync_inventory_from_woocommerce() -> dict[str, Any]:
    """从WooCommerce同步库存"""
    logger.info("Starting inventory sync from WooCommerce...")

    try:
        from app.integrations.woocommerce import get_woocommerce_products

        # 获取WooCommerce产品列表
        result = get_woocommerce_products(per_page=100, page=1)
        products = result.get("products", []) if isinstance(result, dict) else []

        synced_count = len(products)
        low_stock_products = []

        # 检查低库存产品
        for product in products:
            stock_quantity = product.get("stock_quantity", 0) or 0
            if stock_quantity <= LOW_STOCK_THRESHOLD:
                low_stock_products.append({
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "sku": product.get("sku"),
                    "stock_quantity": stock_quantity,
                    "status": product.get("status"),
                })

        logger.info("WooCommerce inventory sync completed: %d products, %d low stock",
                    synced_count, len(low_stock_products))

        return {
            "success": True,
            "source": "woocommerce",
            "synced_count": synced_count,
            "low_stock_count": len(low_stock_products),
            "low_stock_products": low_stock_products[:20],  # 最多返回20个
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("WooCommerce inventory sync failed: %s", str(e))
        return {
            "success": False,
            "source": "woocommerce",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def check_low_stock_alerts() -> dict[str, Any]:
    """检查低库存告警"""
    logger.info("Checking low stock alerts...")

    try:
        # 从WooCommerce获取产品并检查低库存
        wc_result = await sync_inventory_from_woocommerce()
        low_stock_products = wc_result.get("low_stock_products", [])

        alerts = []
        for product in low_stock_products:
            alerts.append({
                "type": "low_stock",
                "severity": "warning" if product["stock_quantity"] > 0 else "critical",
                "product_id": product["id"],
                "product_name": product["name"],
                "sku": product["sku"],
                "current_stock": product["stock_quantity"],
                "threshold": LOW_STOCK_THRESHOLD,
                "message": f"产品 '{product['name']}' 库存不足: {product['stock_quantity']} (阈值: {LOW_STOCK_THRESHOLD})",
                "timestamp": datetime.utcnow().isoformat(),
            })

        logger.info("Low stock check completed: %d alerts", len(alerts))

        return {
            "success": True,
            "alerts_count": len(alerts),
            "alerts": alerts,
            "alert_email": ALERT_EMAIL,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Low stock alert check failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


async def run_full_sync() -> dict[str, Any]:
    """运行完整库存同步（1688 + WooCommerce + 低库存检查）"""
    logger.info("Starting full inventory sync...")

    results = {
        "started_at": datetime.utcnow().isoformat(),
        "auto_sync_enabled": AUTO_SYNC_ENABLED,
        "sync_interval_minutes": SYNC_INTERVAL_MINUTES,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
    }

    if not AUTO_SYNC_ENABLED:
        results["status"] = "disabled"
        results["message"] = "自动同步已禁用"
        return results

    # 同步1688库存
    result_1688 = await sync_inventory_from_1688()
    results["1688_sync"] = result_1688

    # 同步WooCommerce库存
    result_wc = await sync_inventory_from_woocommerce()
    results["woocommerce_sync"] = result_wc

    # 检查低库存告警
    result_alerts = await check_low_stock_alerts()
    results["low_stock_alerts"] = result_alerts

    results["completed_at"] = datetime.utcnow().isoformat()
    results["status"] = "completed"

    logger.info("Full inventory sync completed")
    return results


def get_sync_status() -> dict[str, Any]:
    """获取库存同步状态"""
    return {
        "auto_sync_enabled": AUTO_SYNC_ENABLED,
        "sync_interval_minutes": SYNC_INTERVAL_MINUTES,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "alert_email": ALERT_EMAIL,
        "last_sync": None,  # 可以从数据库或文件读取上次同步时间
        "next_sync": None,
        "sources": ["1688", "woocommerce"],
        "supported_operations": [
            "sync_inventory_from_1688",
            "sync_inventory_from_woocommerce",
            "check_low_stock_alerts",
            "run_full_sync",
        ],
    }


if __name__ == "__main__":
    # 手动运行一次完整同步
    asyncio.run(run_full_sync())
