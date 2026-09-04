# -*- coding: utf-8 -*-
"""
采购单服务（半自动代采）
流程: WooCommerce出单 → 自动生成采购单草稿 → 人工确认 → 1688网页端下单 → 回填物流单号 → 更新WooCommerce订单

状态机: pending(待确认) → confirmed(已确认) → ordered(已下单) → shipped(已发货) → completed(已完成)
                                    ↘ cancelled(已取消)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import requests

# 数据文件路径（backend/data/）
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
MAPPING_FILE = os.path.join(DATA_DIR, "supplier_product_mapping.json")
PURCHASE_ORDERS_FILE = os.path.join(DATA_DIR, "purchase_orders.json")

# WooCommerce API配置
# 密钥必须从环境变量 WOOCOMMERCE_CONSUMER_KEY / WOOCOMMERCE_CONSUMER_SECRET 读取。
# 禁止硬编码密钥到源码——会被提交到 git 并泄露。
WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
WC_AUTH = (
    os.getenv("WOOCOMMERCE_CONSUMER_KEY"),
    os.getenv("WOOCOMMERCE_CONSUMER_SECRET"),
)

# 采购单状态
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_ORDERED = "ordered"
STATUS_SHIPPED = "shipped"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

VALID_STATUSES = [STATUS_PENDING, STATUS_CONFIRMED, STATUS_ORDERED,
                  STATUS_SHIPPED, STATUS_COMPLETED, STATUS_CANCELLED]

# 状态流转规则
STATUS_TRANSITIONS = {
    STATUS_PENDING: [STATUS_CONFIRMED, STATUS_CANCELLED],
    STATUS_CONFIRMED: [STATUS_ORDERED, STATUS_CANCELLED],
    STATUS_ORDERED: [STATUS_SHIPPED, STATUS_CANCELLED],
    STATUS_SHIPPED: [STATUS_COMPLETED],
    STATUS_COMPLETED: [],
    STATUS_CANCELLED: [],
}


def _ensure_data_dir():
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_mappings() -> list[dict[str, Any]]:
    """加载商品映射配置"""
    if not os.path.exists(MAPPING_FILE):
        return []
    with open(MAPPING_FILE, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data.get("mappings", [])


def find_mapping_by_woo_id(woo_product_id: int) -> dict[str, Any] | None:
    """根据WooCommerce产品ID查找1688映射"""
    mappings = load_mappings()
    for m in mappings:
        if m.get("woo_product_id") == woo_product_id and m.get("status") == "active":
            return m
    return None


def load_purchase_orders() -> list[dict[str, Any]]:
    """加载所有采购单"""
    _ensure_data_dir()
    if not os.path.exists(PURCHASE_ORDERS_FILE):
        return []
    with open(PURCHASE_ORDERS_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_purchase_orders(orders: list[dict[str, Any]]):
    """保存采购单"""
    _ensure_data_dir()
    with open(PURCHASE_ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)


def generate_purchase_order_id() -> str:
    """生成采购单号 PO-YYYYMMDD-XXXX"""
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = uuid4().hex[:4].upper()
    return f"PO-{date_str}-{random_str}"


def create_purchase_order_from_wc_order(wc_order: dict[str, Any]) -> dict[str, Any]:
    """
    从WooCommerce订单生成采购单草稿

    Args:
        wc_order: WooCommerce订单数据（从webhook或API获取）

    Returns:
        采购单信息
    """
    order_id = wc_order.get("id")
    order_number = wc_order.get("number", str(order_id))

    # 按商品拆分，查找1688映射
    items = []
    unmapped_items = []
    total_cost = 0.0

    for line_item in wc_order.get("line_items", []):
        product_id = line_item.get("product_id")
        quantity = line_item.get("quantity", 1)
        product_name = line_item.get("name", "")

        mapping = find_mapping_by_woo_id(product_id)
        if mapping and mapping.get("ali1688_url"):
            cost = mapping.get("ali1688_cost", 0) or 0
            item_total = float(cost) * quantity
            total_cost += item_total
            items.append({
                "woo_product_id": product_id,
                "woo_sku": mapping.get("woo_sku", ""),
                "woo_name": product_name,
                "quantity": quantity,
                "ali1688_product_id": mapping.get("ali1688_product_id", ""),
                "ali1688_url": mapping.get("ali1688_url", ""),
                "ali1688_supplier": mapping.get("ali1688_supplier", ""),
                "ali1688_sku": mapping.get("ali1688_sku", ""),
                "unit_cost": float(cost),
                "item_total": round(item_total, 2),
                "shipping_method": mapping.get("shipping_method", ""),
            })
        else:
            unmapped_items.append({
                "woo_product_id": product_id,
                "woo_name": product_name,
                "quantity": quantity,
                "reason": "未找到1688商品映射",
            })

    # 客户收货信息
    billing = wc_order.get("billing", {})
    shipping = wc_order.get("shipping", {})

    purchase_order = {
        "purchase_order_id": generate_purchase_order_id(),
        "wc_order_id": order_id,
        "wc_order_number": order_number,
        "status": STATUS_PENDING,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "customer": {
            "name": f"{shipping.get('first_name', '')} {shipping.get('last_name', '')}".strip(),
            "email": billing.get("email", ""),
            "phone": billing.get("phone", ""),
            "address": f"{shipping.get('address_1', '')} {shipping.get('address_2', '')}".strip(),
            "city": shipping.get("city", ""),
            "state": shipping.get("state", ""),
            "postcode": shipping.get("postcode", ""),
            "country": shipping.get("country", ""),
        },
        "items": items,
        "unmapped_items": unmapped_items,
        "total_cost": round(total_cost, 2),
        "total_quantity": sum(item["quantity"] for item in items),
        "ali1688_order_id": "",
        "ali1688_order_url": "",
        "tracking_number": "",
        "tracking_carrier": "",
        "tracking_url": "",
        "notes": "",
        "history": [
            {
                "timestamp": datetime.now().isoformat(),
                "action": "created",
                "description": f"从WooCommerce订单#{order_id}自动生成采购单草稿",
            }
        ],
    }

    # 保存
    orders = load_purchase_orders()
    orders.append(purchase_order)
    save_purchase_orders(orders)

    return purchase_order


def get_purchase_order(po_id: str) -> dict[str, Any] | None:
    """根据采购单号获取采购单"""
    orders = load_purchase_orders()
    for po in orders:
        if po.get("purchase_order_id") == po_id:
            return po
    return None


def update_purchase_order_status(po_id: str, new_status: str, notes: str = "") -> dict[str, Any] | None:
    """
    更新采购单状态

    Args:
        po_id: 采购单号
        new_status: 新状态
        notes: 备注

    Returns:
        更新后的采购单
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"无效状态: {new_status}，有效状态: {VALID_STATUSES}")

    orders = load_purchase_orders()
    for i, po in enumerate(orders):
        if po.get("purchase_order_id") == po_id:
            current_status = po.get("status")
            # 检查状态流转是否合法
            if new_status not in STATUS_TRANSITIONS.get(current_status, []):
                raise ValueError(
                    f"状态流转不合法: {current_status} -> {new_status}，"
                    f"允许的流转: {STATUS_TRANSITIONS.get(current_status, [])}"
                )

            po["status"] = new_status
            po["updated_at"] = datetime.now().isoformat()
            if notes:
                po["notes"] = notes

            po["history"].append({
                "timestamp": datetime.now().isoformat(),
                "action": f"status_changed_to_{new_status}",
                "description": notes or f"状态变更为 {new_status}",
            })

            orders[i] = po
            save_purchase_orders(orders)
            return po
    return None


def confirm_purchase_order(po_id: str, notes: str = "") -> dict[str, Any] | None:
    """确认采购单（人工确认后可以去1688下单）"""
    return update_purchase_order_status(po_id, STATUS_CONFIRMED, notes)


def mark_ordered(po_id: str, ali1688_order_id: str = "", ali1688_order_url: str = "", notes: str = "") -> dict[str, Any] | None:
    """标记已在1688下单"""
    orders = load_purchase_orders()
    for i, po in enumerate(orders):
        if po.get("purchase_order_id") == po_id:
            if po.get("status") != STATUS_CONFIRMED:
                raise ValueError(f"采购单状态必须是confirmed才能标记ordered，当前: {po.get('status')}")

            po["status"] = STATUS_ORDERED
            po["ali1688_order_id"] = ali1688_order_id
            po["ali1688_order_url"] = ali1688_order_url
            po["updated_at"] = datetime.now().isoformat()
            if notes:
                po["notes"] = notes
            po["history"].append({
                "timestamp": datetime.now().isoformat(),
                "action": "marked_ordered",
                "description": f"已在1688下单，订单号: {ali1688_order_id or '未填写'}",
            })
            orders[i] = po
            save_purchase_orders(orders)
            return po
    return None


def add_tracking(po_id: str, tracking_number: str, carrier: str = "", tracking_url: str = "", notes: str = "") -> dict[str, Any] | None:
    """
    添加物流跟踪号，并自动更新WooCommerce订单

    Args:
        po_id: 采购单号
        tracking_number: 物流单号
        carrier: 承运商
        tracking_url: 物流查询链接
        notes: 备注

    Returns:
        更新后的采购单
    """
    orders = load_purchase_orders()
    for i, po in enumerate(orders):
        if po.get("purchase_order_id") == po_id:
            if po.get("status") not in (STATUS_ORDERED, STATUS_SHIPPED):
                raise ValueError(f"采购单状态必须是ordered或shipped才能添加物流，当前: {po.get('status')}")

            po["status"] = STATUS_SHIPPED
            po["tracking_number"] = tracking_number
            po["tracking_carrier"] = carrier
            po["tracking_url"] = tracking_url
            po["updated_at"] = datetime.now().isoformat()
            if notes:
                po["notes"] = notes
            po["history"].append({
                "timestamp": datetime.now().isoformat(),
                "action": "tracking_added",
                "description": f"物流单号: {tracking_number}, 承运商: {carrier or '未填写'}",
            })
            orders[i] = po
            save_purchase_orders(orders)

            # 自动更新WooCommerce订单（添加物流备注）
            wc_order_id = po.get("wc_order_id")
            if wc_order_id:
                _update_wc_order_with_tracking(wc_order_id, tracking_number, carrier, tracking_url)

            return po
    return None


def _update_wc_order_with_tracking(wc_order_id: int, tracking_number: str, carrier: str = "", tracking_url: str = ""):
    """更新WooCommerce订单，添加物流跟踪备注"""
    try:
        note_text = f"订单已发货 | 承运商: {carrier or '未知'} | 追踪号: {tracking_number}"
        if tracking_url:
            note_text += f" | 查询: {tracking_url}"

        note_data = {
            "note": note_text,
            "customer_note": True,
        }
        resp = requests.post(
            f"{WC_URL}/orders/{wc_order_id}/notes",
            json=note_data,
            auth=WC_AUTH,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            return True
    except Exception as e:
        print(f"  ⚠️ 更新WooCommerce订单物流备注失败: {e}")
    return False


def complete_purchase_order(po_id: str, notes: str = "") -> dict[str, Any] | None:
    """完成采购单（客户确认收货后）"""
    return update_purchase_order_status(po_id, STATUS_COMPLETED, notes)


def cancel_purchase_order(po_id: str, reason: str = "") -> dict[str, Any] | None:
    """取消采购单"""
    return update_purchase_order_status(po_id, STATUS_CANCELLED, reason)


def list_purchase_orders(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """
    列出采购单

    Args:
        status: 按状态筛选（None=全部）
        limit: 返回数量限制

    Returns:
        采购单列表（按创建时间倒序）
    """
    orders = load_purchase_orders()
    if status:
        orders = [po for po in orders if po.get("status") == status]
    orders.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return orders[:limit]


def get_purchase_order_stats() -> dict[str, Any]:
    """获取采购单统计"""
    orders = load_purchase_orders()
    stats = {
        "total": len(orders),
        "by_status": {},
        "total_cost": 0.0,
        "pending_count": 0,
    }
    for status in VALID_STATUSES:
        count = sum(1 for po in orders if po.get("status") == status)
        stats["by_status"][status] = count
    stats["total_cost"] = round(sum(po.get("total_cost", 0) for po in orders), 2)
    stats["pending_count"] = stats["by_status"].get(STATUS_PENDING, 0)
    return stats
