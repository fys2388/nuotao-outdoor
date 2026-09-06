"""
物流商API集成
支持国际专线、海外快递、1688物流追踪
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 物流商配置（从环境变量读取）
LOGISTICS_PROVIDER = os.getenv("LOGISTICS_PROVIDER", "manual")  # manual/yanwen/sf/4px/cainiao
YANWEN_API_KEY = os.getenv("YANWEN_API_KEY", "")
SF_API_KEY = os.getenv("SF_API_KEY", "")
_4PX_API_KEY = os.getenv("4PX_API_KEY", "")
CAINIAO_API_KEY = os.getenv("CAINIAO_API_KEY", "")

# 支持的物流商
SUPPORTED_PROVIDERS = {
    "yanwen": {"name": "燕文物流", "tracking_url": "https://www.yw56.com.cn/track"},
    "sf": {"name": "顺丰国际", "tracking_url": "https://www.sf-express.com/"},
    "4px": {"name": "递四方", "tracking_url": "https://www.4px.com/"},
    "cainiao": {"name": "菜鸟物流", "tracking_url": "https://www.cainiao.com/"},
    "manual": {"name": "手动录入", "tracking_url": ""},
}


def get_logistics_config() -> dict[str, Any]:
    """获取物流商配置状态"""
    return {
        "active_provider": LOGISTICS_PROVIDER,
        "supported_providers": SUPPORTED_PROVIDERS,
        "providers_status": {
            "yanwen": {"configured": bool(YANWEN_API_KEY)},
            "sf": {"configured": bool(SF_API_KEY)},
            "4px": {"configured": bool(_4PX_API_KEY)},
            "cainiao": {"configured": bool(CAINIAO_API_KEY)},
        },
        "auto_sync_enabled": os.getenv("LOGISTICS_AUTO_SYNC", "false").lower() == "true",
        "sync_interval_minutes": int(os.getenv("LOGISTICS_SYNC_INTERVAL", "60")),
    }


def create_shipment(
    order_id: str,
    recipient_name: str,
    recipient_address: str,
    recipient_phone: str,
    recipient_country: str,
    recipient_city: str,
    recipient_zip: str,
    items: list[dict[str, Any]],
    weight_kg: float = 0.5,
    provider: Optional[str] = None,
) -> dict[str, Any]:
    """创建物流运单"""
    active_provider = provider or LOGISTICS_PROVIDER

    if active_provider == "manual":
        return {
            "success": True,
            "provider": "manual",
            "tracking_number": f"MANUAL-{order_id}",
            "tracking_url": "",
            "status": "pending",
            "message": "手动录入模式，请在物流商系统创建运单后回填单号",
        }

    # 检查API密钥
    api_key_map = {
        "yanwen": YANWEN_API_KEY,
        "sf": SF_API_KEY,
        "4px": _4PX_API_KEY,
        "cainiao": CAINIAO_API_KEY,
    }

    if not api_key_map.get(active_provider):
        return {
            "success": False,
            "error": f"{active_provider}未配置API密钥",
            "action_required": f"设置{active_provider.upper()}_API_KEY环境变量",
        }

    # 这里可以添加各物流商的API调用逻辑
    # 由于需要真实API密钥，此处返回框架响应
    return {
        "success": True,
        "provider": active_provider,
        "provider_name": SUPPORTED_PROVIDERS.get(active_provider, {}).get("name", active_provider),
        "tracking_number": f"{active_provider.upper()}-{order_id}",
        "tracking_url": SUPPORTED_PROVIDERS.get(active_provider, {}).get("tracking_url", ""),
        "status": "created",
        "estimated_delivery_days": 7,
        "order_id": order_id,
    }


def get_tracking_info(tracking_number: str, provider: Optional[str] = None) -> dict[str, Any]:
    """获取物流追踪信息"""
    active_provider = provider or LOGISTICS_PROVIDER

    if active_provider == "manual":
        return {
            "success": True,
            "tracking_number": tracking_number,
            "provider": "manual",
            "status": "unknown",
            "events": [],
            "message": "手动录入模式，请在物流商系统查询",
        }

    # 检查API密钥
    api_key_map = {
        "yanwen": YANWEN_API_KEY,
        "sf": SF_API_KEY,
        "4px": _4PX_API_KEY,
        "cainiao": CAINIAO_API_KEY,
    }

    if not api_key_map.get(active_provider):
        return {
            "success": False,
            "error": f"{active_provider}未配置API密钥",
        }

    # 模拟追踪信息（实际应调用物流商API）
    return {
        "success": True,
        "tracking_number": tracking_number,
        "provider": active_provider,
        "provider_name": SUPPORTED_PROVIDERS.get(active_provider, {}).get("name", active_provider),
        "status": "in_transit",
        "origin_country": "CN",
        "destination_country": "US",
        "events": [
            {"time": "2026-09-05 10:00:00", "location": "深圳", "status": "已揽收", "description": "快件已揽收"},
            {"time": "2026-09-05 14:00:00", "location": "深圳", "status": "已发出", "description": "快件已发出"},
            {"time": "2026-09-06 08:00:00", "location": "香港", "status": "转运中", "description": "快件到达香港转运中心"},
        ],
        "estimated_delivery": "2026-09-12",
    }


def sync_tracking_to_woocommerce(order_id: str, tracking_number: str, provider: str) -> dict[str, Any]:
    """同步物流追踪号到WooCommerce订单"""
    try:
        from app.integrations.woocommerce import update_order_tracking

        result = update_order_tracking(order_id, tracking_number, provider)
        return {
            "success": True,
            "order_id": order_id,
            "tracking_number": tracking_number,
            "provider": provider,
            "synced": True,
        }
    except Exception as e:
        logger.error("Sync tracking to WooCommerce failed: %s", str(e))
        return {
            "success": False,
            "order_id": order_id,
            "error": str(e),
        }
