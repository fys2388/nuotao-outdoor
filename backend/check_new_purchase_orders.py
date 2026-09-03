# -*- coding: utf-8 -*-
"""
新采购单提醒脚本

功能: 检查pending状态的采购单，只提醒新增的（基于上次检查时间）
用法: python check_new_purchase_orders.py
配置: 可通过cron/Windows任务计划定期运行（建议每小时一次）
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.purchase_order_service import (
    load_purchase_orders, STATUS_PENDING,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LAST_CHECK_FILE = os.path.join(DATA_DIR, "purchase_order_last_check.json")


def load_last_check() -> dict:
    """加载上次检查记录"""
    if not os.path.exists(LAST_CHECK_FILE):
        return {"last_check_time": None, "notified_po_ids": []}
    try:
        with open(LAST_CHECK_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {"last_check_time": None, "notified_po_ids": []}


def save_last_check(check_data: dict):
    """保存检查记录"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LAST_CHECK_FILE, "w", encoding="utf-8") as f:
        json.dump(check_data, f, ensure_ascii=False, indent=2)


def main():
    now = datetime.now().isoformat()
    print(f"=== 采购单提醒检查 [{now[:19]}] ===")
    print()

    # 加载所有pending采购单
    all_orders = load_purchase_orders()
    pending_orders = [po for po in all_orders if po.get("status") == STATUS_PENDING]

    print(f"当前待确认采购单: {len(pending_orders)}个")
    print()

    # 加载上次检查记录
    last_check = load_last_check()
    notified_ids = set(last_check.get("notified_po_ids", []))

    # 筛选新增的pending采购单（未提醒过的）
    new_orders = [po for po in pending_orders if po.get("purchase_order_id") not in notified_ids]

    if not new_orders:
        print("✅ 没有新增待确认采购单")
        # 更新检查时间
        last_check["last_check_time"] = now
        save_last_check(last_check)
        return

    # 输出新增采购单提醒
    print(f"🔔 发现 {len(new_orders)} 个新增待确认采购单:")
    print("-" * 70)

    total_cost = 0
    for po in new_orders:
        po_id = po.get("purchase_order_id", "")
        wc_order_id = po.get("wc_order_id", "")
        items = po.get("items", [])
        unmapped = po.get("unmapped_items", [])
        cost = po.get("total_cost", 0)
        total_cost += cost

        # 商品摘要
        item_summary = ", ".join(
            f"{item.get('woo_sku', item.get('woo_name', '?'))}x{item.get('quantity', 1)}"
            for item in items[:3]
        )
        if len(items) > 3:
            item_summary += f" 等{len(items)}个商品"

        print(f"  采购单: {po_id}")
        print(f"  Woo订单: #{wc_order_id}")
        print(f"  商品: {item_summary}")
        print(f"  采购成本: ¥{cost:.2f}")
        if unmapped:
            print(f"  ⚠️ 未映射商品: {len(unmapped)}个（需手动处理）")
        print(f"  操作: python manage_purchase_orders.py show {po_id}")
        print(f"        python manage_purchase_orders.py confirm {po_id}")
        print()

    print("-" * 70)
    print(f"新增采购单总成本: ¥{total_cost:.2f}")
    print()
    print("请及时确认采购单并去1688下单！")

    # 更新检查记录
    notified_ids.update(po.get("purchase_order_id") for po in new_orders)
    last_check["last_check_time"] = now
    last_check["notified_po_ids"] = list(notified_ids)
    save_last_check(last_check)

    print()
    print(f"检查记录已更新，下次检查将忽略以上 {len(new_orders)} 个采购单")


if __name__ == "__main__":
    main()
