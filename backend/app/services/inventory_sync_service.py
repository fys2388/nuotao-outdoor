"""
库存同步服务
同步 Nuotao 库存变更到 WooCommerce
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

WC_URL = os.getenv("WOOCOMMERCE_URL", "https://nuotaooutdoor.com")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")


async def sync_stock_to_woocommerce(
    woocommerce_product_id: int,
    stock_quantity: int,
    in_stock: bool = True,
) -> dict[str, Any]:
    """
    同步库存到 WooCommerce

    Args:
        woocommerce_product_id: WooCommerce 产品 ID
        stock_quantity: 库存数量
        in_stock: 是否有货

    Returns:
        同步结果
    """
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        return {"success": False, "error": "WooCommerce API 密钥未配置"}

    try:
        url = f"{WC_URL}/wp-json/wc/v3/products/{woocommerce_product_id}"
        data = {
            "manage_stock": True,
            "stock_quantity": stock_quantity,
            "in_stock": in_stock,
        }

        resp = requests.put(
            url,
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        logger.info(
            f"Stock synced to WooCommerce: product={woocommerce_product_id}, "
            f"qty={stock_quantity}, in_stock={in_stock}"
        )
        return {
            "success": True,
            "woocommerce_id": woocommerce_product_id,
            "stock_quantity": result.get("stock_quantity"),
            "in_stock": result.get("in_stock"),
        }
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get("message", str(e))
        except Exception:
            error_detail = str(e)
        logger.error(f"Failed to sync stock to WooCommerce: {error_detail}")
        return {"success": False, "error": error_detail}
    except Exception as e:
        logger.error(f"Stock sync error: {e}")
        return {"success": False, "error": str(e)}


async def batch_sync_stock(
    stock_updates: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    批量同步库存到 WooCommerce

    Args:
        stock_updates: [{"woocommerce_id": 123, "stock_quantity": 10, "in_stock": true}]

    Returns:
        批量同步结果
    """
    results = []
    success_count = 0
    fail_count = 0

    for update in stock_updates:
        result = await sync_stock_to_woocommerce(
            woocommerce_product_id=update["woocommerce_id"],
            stock_quantity=update["stock_quantity"],
            in_stock=update.get("in_stock", True),
        )
        results.append(result)
        if result["success"]:
            success_count += 1
        else:
            fail_count += 1

    logger.info(f"Batch stock sync: {success_count} success, {fail_count} failed")
    return {
        "success": fail_count == 0,
        "total": len(stock_updates),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
    }
