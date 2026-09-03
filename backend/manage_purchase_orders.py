# -*- coding: utf-8 -*-
"""
采购单CLI管理工具（半自动代采）

用法:
  python manage_purchase_orders.py list [--status pending] [--limit 20]
  python manage_purchase_orders.py show <PO-ID>
  python manage_purchase_orders.py confirm <PO-ID> [--notes "备注"]
  python manage_purchase_orders.py ordered <PO-ID> [--ali-order-id 1688订单号] [--ali-order-url 链接] [--notes "备注"]
  python manage_purchase_orders.py tracking <PO-ID> --tracking 物流单号 [--carrier 承运商] [--tracking-url 查询链接] [--notes "备注"]
  python manage_purchase_orders.py complete <PO-ID> [--notes "备注"]
  python manage_purchase_orders.py cancel <PO-ID> [--reason "取消原因"]
  python manage_purchase_orders.py stats
  python manage_purchase_orders.py generate-from-wc <WC-ORDER-ID>  # 从WooCommerce订单生成采购单
"""
import sys
import os
import json
import argparse

sys.path.insert(0, '.')

from app.services.purchase_order_service import (
    list_purchase_orders, get_purchase_order, get_purchase_order_stats,
    confirm_purchase_order, mark_ordered, add_tracking,
    complete_purchase_order, cancel_purchase_order,
    create_purchase_order_from_wc_order,
    STATUS_PENDING, STATUS_CONFIRMED, STATUS_ORDERED,
    STATUS_SHIPPED, STATUS_COMPLETED, STATUS_CANCELLED,
    VALID_STATUSES,
)

import requests

WC_URL = "https://nuotaooutdoor.com/wp-json/wc/v3"
WC_AUTH = (
    os.getenv("WOOCOMMERCE_CONSUMER_KEY", "***REMOVED_WOOCOMMERCE_KEY***"),
    os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "***REMOVED_WOOCOMMERCE_SECRET***"),
)

STATUS_LABELS = {
    STATUS_PENDING: "待确认",
    STATUS_CONFIRMED: "已确认",
    STATUS_ORDERED: "已下单",
    STATUS_SHIPPED: "已发货",
    STATUS_COMPLETED: "已完成",
    STATUS_CANCELLED: "已取消",
}

STATUS_COLORS = {
    STATUS_PENDING: "\033[93m",      # 黄色
    STATUS_CONFIRMED: "\033[94m",    # 蓝色
    STATUS_ORDERED: "\033[96m",      # 青色
    STATUS_SHIPPED: "\033[92m",      # 绿色
    STATUS_COMPLETED: "\033[92m",    # 绿色
    STATUS_CANCELLED: "\033[91m",    # 红色
}
RESET = "\033[0m"


def cmd_list(args):
    """列出采购单"""
    orders = list_purchase_orders(status=args.status, limit=args.limit)
    if not orders:
        print("暂无采购单")
        return

    print(f"\n{'采购单号':<20} {'Woo订单':<10} {'状态':<8} {'商品数':<6} {'成本':<10} {'创建时间':<20}")
    print("-" * 90)
    for po in orders:
        status = po.get("status", "")
        color = STATUS_COLORS.get(status, "")
        status_label = STATUS_LABELS.get(status, status)
        print(f"{po.get('purchase_order_id', ''):<20} "
              f"#{po.get('wc_order_id', ''):<9} "
              f"{color}{status_label}{RESET:<8} "
              f"{po.get('total_quantity', 0):<6} "
              f"${po.get('total_cost', 0):<9.2f} "
              f"{po.get('created_at', '')[:19]:<20}")
    print(f"\n共 {len(orders)} 条采购单")


def cmd_show(args):
    """查看采购单详情"""
    po = get_purchase_order(args.po_id)
    if not po:
        print(f"采购单不存在: {args.po_id}")
        return

    status = po.get("status", "")
    color = STATUS_COLORS.get(status, "")
    status_label = STATUS_LABELS.get(status, status)

    print(f"\n{'='*70}")
    print(f"采购单: {po['purchase_order_id']}")
    print(f"状态: {color}{status_label}{RESET}")
    print(f"WooCommerce订单: #{po.get('wc_order_id')} ({po.get('wc_order_number')})")
    print(f"创建时间: {po.get('created_at', '')[:19]}")
    print(f"更新时间: {po.get('updated_at', '')[:19]}")
    print(f"{'='*70}")

    # 客户信息
    cust = po.get("customer", {})
    print(f"\n--- 客户收货信息 ---")
    print(f"  姓名: {cust.get('name', '')}")
    print(f"  邮箱: {cust.get('email', '')}")
    print(f"  电话: {cust.get('phone', '')}")
    print(f"  地址: {cust.get('address', '')}, {cust.get('city', '')}, "
          f"{cust.get('state', '')} {cust.get('postcode', '')}, {cust.get('country', '')}")

    # 商品明细
    items = po.get("items", [])
    print(f"\n--- 采购商品 ({len(items)}个) ---")
    for i, item in enumerate(items, 1):
        print(f"\n  [{i}] {item.get('woo_name', '')[:50]}")
        print(f"      SKU: {item.get('woo_sku', '')} | 数量: {item.get('quantity')}")
        print(f"      1688商品ID: {item.get('ali1688_product_id', '')}")
        print(f"      1688链接: {item.get('ali1688_url', '')}")
        print(f"      供应商: {item.get('ali1688_supplier', '')}")
        print(f"      单价: ¥{item.get('unit_cost', 0):.2f} | 小计: ¥{item.get('item_total', 0):.2f}")

    # 未映射商品
    unmapped = po.get("unmapped_items", [])
    if unmapped:
        print(f"\n--- ⚠️ 未映射商品 ({len(unmapped)}个，需手动处理) ---")
        for item in unmapped:
            print(f"  - {item.get('woo_name', '')[:50]} (ID:{item.get('woo_product_id')}, x{item.get('quantity')})")
            print(f"    原因: {item.get('reason', '')}")

    # 1688订单信息
    print(f"\n--- 1688订单信息 ---")
    print(f"  1688订单号: {po.get('ali1688_order_id', '未填写')}")
    print(f"  1688订单链接: {po.get('ali1688_order_url', '未填写')}")

    # 物流信息
    print(f"\n--- 物流信息 ---")
    print(f"  物流单号: {po.get('tracking_number', '未填写')}")
    print(f"  承运商: {po.get('tracking_carrier', '未填写')}")
    print(f"  查询链接: {po.get('tracking_url', '未填写')}")

    # 成本汇总
    print(f"\n--- 成本汇总 ---")
    print(f"  商品总成本: ¥{po.get('total_cost', 0):.2f}")
    print(f"  商品总数: {po.get('total_quantity', 0)}")

    # 备注
    if po.get("notes"):
        print(f"\n--- 备注 ---")
        print(f"  {po['notes']}")

    # 操作历史
    history = po.get("history", [])
    if history:
        print(f"\n--- 操作历史 ---")
        for h in history:
            print(f"  [{h.get('timestamp', '')[:19]}] {h.get('action', '')}: {h.get('description', '')}")

    print()


def cmd_confirm(args):
    """确认采购单"""
    try:
        po = confirm_purchase_order(args.po_id, notes=args.notes)
        if po:
            print(f"✅ 采购单 {args.po_id} 已确认")
            print(f"   现在可以去1688网页端下单了")
            print(f"   下单后运行: python manage_purchase_orders.py ordered {args.po_id} --ali-order-id <1688订单号>")
        else:
            print(f"❌ 采购单不存在: {args.po_id}")
    except ValueError as e:
        print(f"❌ 操作失败: {e}")


def cmd_ordered(args):
    """标记已下单"""
    try:
        po = mark_ordered(args.po_id,
                          ali1688_order_id=args.ali_order_id,
                          ali1688_order_url=args.ali_order_url,
                          notes=args.notes)
        if po:
            print(f"✅ 采购单 {args.po_id} 已标记为已下单")
            print(f"   1688订单号: {args.ali_order_id or '未填写'}")
            print(f"   供应商发货后运行: python manage_purchase_orders.py tracking {args.po_id} --tracking <物流单号>")
        else:
            print(f"❌ 采购单不存在: {args.po_id}")
    except ValueError as e:
        print(f"❌ 操作失败: {e}")


def cmd_tracking(args):
    """添加物流跟踪号"""
    if not args.tracking:
        print("❌ 必须指定 --tracking 物流单号")
        return
    try:
        po = add_tracking(args.po_id,
                          tracking_number=args.tracking,
                          carrier=args.carrier,
                          tracking_url=args.tracking_url,
                          notes=args.notes)
        if po:
            print(f"✅ 物流单号已添加: {args.tracking}")
            print(f"   承运商: {args.carrier or '未填写'}")
            print(f"   ✅ WooCommerce订单 #{po.get('wc_order_id')} 已自动更新物流备注")
            print(f"   客户确认收货后运行: python manage_purchase_orders.py complete {args.po_id}")
        else:
            print(f"❌ 采购单不存在: {args.po_id}")
    except ValueError as e:
        print(f"❌ 操作失败: {e}")


def cmd_complete(args):
    """完成采购单"""
    try:
        po = complete_purchase_order(args.po_id, notes=args.notes)
        if po:
            print(f"✅ 采购单 {args.po_id} 已完成")
        else:
            print(f"❌ 采购单不存在: {args.po_id}")
    except ValueError as e:
        print(f"❌ 操作失败: {e}")


def cmd_cancel(args):
    """取消采购单"""
    try:
        po = cancel_purchase_order(args.po_id, reason=args.reason)
        if po:
            print(f"✅ 采购单 {args.po_id} 已取消")
            print(f"   原因: {args.reason or '未填写'}")
        else:
            print(f"❌ 采购单不存在: {args.po_id}")
    except ValueError as e:
        print(f"❌ 操作失败: {e}")


def cmd_stats(args):
    """采购单统计"""
    stats = get_purchase_order_stats()
    print(f"\n{'='*50}")
    print(f"采购单统计")
    print(f"{'='*50}")
    print(f"  总数: {stats['total']}")
    print(f"  待确认: {stats['by_status'].get(STATUS_PENDING, 0)}")
    print(f"  已确认: {stats['by_status'].get(STATUS_CONFIRMED, 0)}")
    print(f"  已下单: {stats['by_status'].get(STATUS_ORDERED, 0)}")
    print(f"  已发货: {stats['by_status'].get(STATUS_SHIPPED, 0)}")
    print(f"  已完成: {stats['by_status'].get(STATUS_COMPLETED, 0)}")
    print(f"  已取消: {stats['by_status'].get(STATUS_CANCELLED, 0)}")
    print(f"  采购总成本: ¥{stats['total_cost']:.2f}")
    print()


def cmd_generate_from_wc(args):
    """从WooCommerce订单生成采购单"""
    wc_order_id = args.wc_order_id
    print(f"正在获取WooCommerce订单 #{wc_order_id} ...")

    try:
        resp = requests.get(f"{WC_URL}/orders/{wc_order_id}", auth=WC_AUTH, timeout=30)
        if resp.status_code != 200:
            print(f"❌ 获取WooCommerce订单失败: HTTP {resp.status_code}")
            print(resp.text[:200])
            return
        wc_order = resp.json()
    except Exception as e:
        print(f"❌ 获取WooCommerce订单异常: {e}")
        return

    print(f"  订单状态: {wc_order.get('status')}")
    print(f"  商品数: {len(wc_order.get('line_items', []))}")
    print(f"  总额: ${wc_order.get('total')}")

    po = create_purchase_order_from_wc_order(wc_order)

    print(f"\n✅ 采购单已生成: {po['purchase_order_id']}")
    print(f"   状态: {STATUS_LABELS.get(po['status'], po['status'])}")
    print(f"   映射商品: {len(po.get('items', []))}个")
    print(f"   未映射商品: {len(po.get('unmapped_items', []))}个")
    print(f"   采购成本: ¥{po.get('total_cost', 0):.2f}")
    print(f"\n   查看详情: python manage_purchase_orders.py show {po['purchase_order_id']}")
    print(f"   确认采购单: python manage_purchase_orders.py confirm {po['purchase_order_id']}")


def main():
    parser = argparse.ArgumentParser(description="采购单CLI管理工具（半自动代采）")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # list
    p_list = subparsers.add_parser("list", help="列出采购单")
    p_list.add_argument("--status", choices=VALID_STATUSES, help="按状态筛选")
    p_list.add_argument("--limit", type=int, default=20, help="返回数量")

    # show
    p_show = subparsers.add_parser("show", help="查看采购单详情")
    p_show.add_argument("po_id", help="采购单号")

    # confirm
    p_confirm = subparsers.add_parser("confirm", help="确认采购单")
    p_confirm.add_argument("po_id", help="采购单号")
    p_confirm.add_argument("--notes", default="", help="备注")

    # ordered
    p_ordered = subparsers.add_parser("ordered", help="标记已在1688下单")
    p_ordered.add_argument("po_id", help="采购单号")
    p_ordered.add_argument("--ali-order-id", default="", help="1688订单号")
    p_ordered.add_argument("--ali-order-url", default="", help="1688订单链接")
    p_ordered.add_argument("--notes", default="", help="备注")

    # tracking
    p_tracking = subparsers.add_parser("tracking", help="添加物流跟踪号")
    p_tracking.add_argument("po_id", help="采购单号")
    p_tracking.add_argument("--tracking", required=True, help="物流单号")
    p_tracking.add_argument("--carrier", default="", help="承运商")
    p_tracking.add_argument("--tracking-url", default="", help="物流查询链接")
    p_tracking.add_argument("--notes", default="", help="备注")

    # complete
    p_complete = subparsers.add_parser("complete", help="完成采购单")
    p_complete.add_argument("po_id", help="采购单号")
    p_complete.add_argument("--notes", default="", help="备注")

    # cancel
    p_cancel = subparsers.add_parser("cancel", help="取消采购单")
    p_cancel.add_argument("po_id", help="采购单号")
    p_cancel.add_argument("--reason", default="", help="取消原因")

    # stats
    subparsers.add_parser("stats", help="采购单统计")

    # generate-from-wc
    p_gen = subparsers.add_parser("generate-from-wc", help="从WooCommerce订单生成采购单")
    p_gen.add_argument("wc_order_id", type=int, help="WooCommerce订单ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "list": cmd_list,
        "show": cmd_show,
        "confirm": cmd_confirm,
        "ordered": cmd_ordered,
        "tracking": cmd_tracking,
        "complete": cmd_complete,
        "cancel": cmd_cancel,
        "stats": cmd_stats,
        "generate-from-wc": cmd_generate_from_wc,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
