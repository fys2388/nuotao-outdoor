"""
产品上架管理服务
支持：上架队列管理、实验产品跟踪、批量上架WooCommerce、1688数据替换
管制物品自动过滤（刀具/危险品等）
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)

# WooCommerce 配置（从环境变量读取）
WC_URL = os.getenv("WOOCOMMERCE_URL", "https://nuotaooutdoor.com")
WC_CONSUMER_KEY = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
WC_CONSUMER_SECRET = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")

# 管制物品关键词（自动过滤，不上架）
RESTRICTED_KEYWORDS = [
    "knife", "刀", "weapon", "武器", "firearm", "枪支",
    "explosive", "爆炸", "flammable", "易燃", "aerosol", "气雾剂",
    "butane", "丁烷", "gas canister", "气罐",
]

# 实验产品配置
EXPERIMENT_PRODUCTS = {
    "NT-BOTTLE-001": {
        "name": "Stainless Steel Insulated Water Bottle - 1L",
        "experiment_start": "2026-09-03",
        "experiment_end": "2026-09-17",
        "experiment_days": 14,
        "hypothesis": "测试保温水壶在欧美户外市场的接受度",
        "status": "experiment_running",
    },
}


def is_restricted(product_name: str, sku: str = "") -> tuple[bool, str]:
    """
    检查产品是否为管制物品

    Returns:
        (is_restricted, reason)
    """
    name_lower = product_name.lower()
    sku_lower = sku.lower()
    for kw in RESTRICTED_KEYWORDS:
        if kw.lower() in name_lower or kw.lower() in sku_lower:
            return True, f"包含管制关键词: {kw}"
    return False, ""


# 上架图片齐套标准（硬约束）：主图 5 张 1:1 + 详情图 6 张 3:4
REQUIRED_MAIN_IMAGES = 5
REQUIRED_DETAIL_IMAGES = 6


# --------------------------------------------------------------------------- #
# 内部分类 → WooCommerce 真实分类 term id 映射
# （WC 站点 term id 与内部 id 无关；此前硬编码 15 恰好是 WC 的 Uncategorized，
#  导致所有商品落到"未分类"。id 取自 WC GET /products/categories。）
# --------------------------------------------------------------------------- #
WC_CATEGORY_KEYWORD_MAP: list[tuple[tuple[str, ...], int]] = [
    # 露营家具：椅 / 桌 / 床
    (("椅", "月亮椅", "折叠椅", "板凳", "凳", "chair", "stool", "lounger", "cot"), 119),  # Camping Chairs
    (("桌", "table", "desk"), 120),  # Camping Tables
    (("收纳柜", "置物架", "储物", "收纳", "storage", "organizer"), 121),  # Storage & Organizers
    (("家具", "furniture"), 55),  # Camping Furniture
    # 帐篷 / 遮蔽
    (("帐篷", "天幕", "遮阳", "防潮垫", "tent", "tarp", "shelter", "canopy"), 53),  # Tents & Shelters
    # 睡眠
    (("睡袋", "sleeping bag"), 17),
    (("睡垫", "防潮垫", "充气垫", "气垫", "枕头", "枕", "mattress", "pad", "pillow", "cot bed"), 54),  # Sleeping Gear
    # 照明 / 电源
    (("头灯", "headlamp"), 130),
    (("营地灯", "露营灯", "台灯", "lantern"), 129),
    (("灯", "照明", "手电", "充电宝", "电源", "light", "lamp", "flashlight", "power bank"), 22),  # Lighting & Power
    # 炊具 / 餐具 / 厨房
    (("烧烤", "烤炉", "烤网", "bbq", "grill", "barbecue"), 102),  # Cooking & Grills
    (("锅", "炉", "灶", "炊具", "厨房", "cookware", "stove", "pot", "pan", "kettle"), 21),  # Cooking
    (("餐具", "杯", "碗", "壶", "餐", "刀叉", "筷", "spoon", "bowl", "cup", "mug", "bottle", "tableware", "picnic"), 56),  # Cookware & Picnic
    # 水具
    (("水杯", "水壶", "水瓶", "保温杯", "water bottle", "tumbler", "hydration"), 94),  # Sports Bottles
    # 背包 / 徒步
    (("背包", "登山包", "双肩包", "腰包", "backpack", "rucksack", "daypack", "hydration pack"), 57),  # Backpacks & Hiking Gear
    # 配件兜底
    (("配件", "accessory", "gear"), 58),  # Outdoor Accessories
]

# 无法判断品类时的户外兜底分类（避免落入 Uncategorized=15）
WC_DEFAULT_CATEGORY_ID = 58  # Outdoor Accessories


def map_category_to_wc(product_name: str = "", internal_category: str = "") -> list[dict[str, int]]:
    """按商品名 + 内部类目关键词映射到 WooCommerce 分类 term id。

    命中第一个关键词组即返回；都不命中返回户外兜底分类，绝不返回 Uncategorized。
    """
    haystack = f"{product_name} {internal_category}".lower()
    for keywords, wc_id in WC_CATEGORY_KEYWORD_MAP:
        for kw in keywords:
            if kw.lower() in haystack:
                return [{"id": wc_id}]
    return [{"id": WC_DEFAULT_CATEGORY_ID}]





def _is_real_image_url(src: Any) -> bool:
    """真实可上架图片：http(s) 远程图；排除 mock 的 data: SVG 占位图与空值。"""
    if not isinstance(src, str):
        return False
    s = src.strip()
    if not s:
        return False
    if s.startswith(("http://", "https://")):
        return True
    return False


def _extract_src(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("src") or item.get("url") or item.get("image_url") or ""
    return ""


def check_image_gate(listing_data: dict[str, Any]) -> dict[str, Any]:
    """
    上架图片齐套门禁。

    统计主图 / 详情图中的真实远程图片数量（mock 占位图、data: URI 不计）。
    主图取 main_images/main_image_urls，详情图取 detail_images/detail_image_urls/
    gallery_images；若都没有则回退到扁平 images（按总数 5+6=11 判定）。

    Returns:
        {"passed", "main_count", "detail_count", "reasons"}
    """
    def collect(*keys: str) -> list[str]:
        for k in keys:
            v = listing_data.get(k)
            if isinstance(v, list) and v:
                return [_extract_src(x) for x in v]
        return []

    main_raw = collect("main_images", "main_image_urls")
    detail_raw = collect("detail_images", "detail_image_urls", "gallery_images")

    main_count = sum(1 for s in main_raw if _is_real_image_url(s))
    detail_count = sum(1 for s in detail_raw if _is_real_image_url(s))

    categorized = bool(main_raw or detail_raw)
    reasons: list[str] = []

    if categorized:
        if main_count < REQUIRED_MAIN_IMAGES:
            reasons.append(f"主图不足：{main_count}/{REQUIRED_MAIN_IMAGES}（需 1:1 主图 5 张）")
        if detail_count < REQUIRED_DETAIL_IMAGES:
            reasons.append(f"详情图不足：{detail_count}/{REQUIRED_DETAIL_IMAGES}（需 3:4 详情图 6 张）")
        passed = main_count >= REQUIRED_MAIN_IMAGES and detail_count >= REQUIRED_DETAIL_IMAGES
    else:
        flat = collect("images", "image_urls")
        total = sum(1 for s in flat if _is_real_image_url(s))
        main_count = min(total, REQUIRED_MAIN_IMAGES)
        detail_count = max(0, total - REQUIRED_MAIN_IMAGES)
        required_total = REQUIRED_MAIN_IMAGES + REQUIRED_DETAIL_IMAGES
        if total < required_total:
            reasons.append(
                f"商品图不足：{total}/{required_total}（需主图 {REQUIRED_MAIN_IMAGES} 张 + 详情图 {REQUIRED_DETAIL_IMAGES} 张）"
            )
        passed = total >= required_total

    return {
        "passed": passed,
        "main_count": main_count,
        "detail_count": detail_count,
        "reasons": reasons,
    }


def create_listing_queue(
    products: list[dict[str, Any]],
    auto_filter_restricted: bool = True,
) -> dict[str, Any]:
    """
    创建上架队列

    Args:
        products: 产品列表
        auto_filter_restricted: 是否自动过滤管制物品

    Returns:
        上架队列
    """
    queue_id = str(uuid4())
    queued = []
    filtered = []

    for p in products:
        name = p.get("name", "")
        sku = p.get("sku", "")

        # 检查是否为实验产品（实验期内不上架）
        if sku in EXPERIMENT_PRODUCTS:
            exp = EXPERIMENT_PRODUCTS[sku]
            filtered.append({
                "sku": sku,
                "name": name,
                "reason": f"实验产品，实验期至 {exp['experiment_end']}",
                "experiment_info": exp,
            })
            continue

        # 检查管制物品
        restricted, reason = is_restricted(name, sku)
        if restricted and auto_filter_restricted:
            filtered.append({"sku": sku, "name": name, "reason": reason})
            continue

        queued.append({
            "queue_item_id": str(uuid4()),
            "sku": sku,
            "name": name,
            "regular_price": p.get("regular_price"),
            "sale_price": p.get("sale_price"),
            "description": p.get("description", ""),
            "short_description": p.get("short_description", ""),
            "stock_quantity": p.get("stock_quantity", 0),
            "categories": p.get("categories", []),
            "tags": p.get("tags", []),
            "images": p.get("images", []),
            "status": "pending",
            "added_at": datetime.utcnow().isoformat(),
        })

    return {
        "queue_id": queue_id,
        "created_at": datetime.utcnow().isoformat(),
        "total_input": len(products),
        "queued_count": len(queued),
        "filtered_count": len(filtered),
        "queued": queued,
        "filtered": filtered,
    }


def list_to_woocommerce(
    product: dict[str, Any],
    status: str = "publish",
) -> dict[str, Any]:
    """
    单个产品上架到 WooCommerce

    Args:
        product: 产品数据
        status: 上架状态（publish/draft/pending）

    Returns:
        上架结果
    """
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        return {"success": False, "error": "WooCommerce API 密钥未配置", "sku": product.get("sku")}

    try:
        url = f"{WC_URL}/wp-json/wc/v3/products"
        data = {
            "name": product["name"],
            "type": "simple",
            "regular_price": str(product.get("regular_price", "")),
            "description": product.get("description", ""),
            "short_description": product.get("short_description", ""),
            "sku": product.get("sku", ""),
            "manage_stock": True,
            "stock_quantity": product.get("stock_quantity", 0),
            "status": status,
            "categories": product.get("categories", [{"id": 15}]),
            "tags": product.get("tags", []),
        }
        if product.get("sale_price"):
            data["sale_price"] = str(product["sale_price"])
        if product.get("images"):
            data["images"] = product["images"]

        resp = requests.post(
            url,
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        return {
            "success": True,
            "sku": product.get("sku"),
            "woocommerce_id": result.get("id"),
            "name": result.get("name"),
            "status": result.get("status"),
            "permalink": result.get("permalink"),
        }
    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json().get("message", str(e))
        except Exception:
            error_detail = str(e)
        logger.error("WooCommerce listing failed for %s: %s", product.get("sku"), error_detail)
        return {"success": False, "sku": product.get("sku"), "error": error_detail}
    except Exception as e:
        logger.error("WooCommerce listing error for %s: %s", product.get("sku"), str(e))
        return {"success": False, "sku": product.get("sku"), "error": str(e)}


def batch_list_to_woocommerce(
    products: list[dict[str, Any]],
    status: str = "publish",
    auto_filter: bool = True,
) -> dict[str, Any]:
    """
    批量上架到 WooCommerce

    Args:
        products: 产品列表
        status: 上架状态
        auto_filter: 是否自动过滤管制物品

    Returns:
        批量上架结果
    """
    # 创建队列（自动过滤）
    queue = create_listing_queue(products, auto_filter_restricted=auto_filter)

    results = []
    success_count = 0
    fail_count = 0

    for item in queue["queued"]:
        result = list_to_woocommerce(item, status=status)
        results.append(result)
        if result["success"]:
            success_count += 1
        else:
            fail_count += 1

    return {
        "batch_id": queue["queue_id"],
        "total_input": queue["total_input"],
        "queued": queue["queued_count"],
        "filtered": queue["filtered_count"],
        "success": success_count,
        "failed": fail_count,
        "results": results,
        "filtered_items": queue["filtered"],
    }


def check_experiment_status() -> dict[str, Any]:
    """
    检查实验产品状态

    Returns:
        实验状态
    """
    now = datetime.utcnow()
    experiments = []

    for sku, exp in EXPERIMENT_PRODUCTS.items():
        start = datetime.fromisoformat(exp["experiment_start"])
        end = datetime.fromisoformat(exp["experiment_end"])
        days_remaining = max(0, (end - now).days)
        days_elapsed = (now - start).days
        progress = min(100, round(days_elapsed / exp["experiment_days"] * 100, 1))

        if now < start:
            status = "not_started"
        elif now <= end:
            status = "running"
        else:
            status = "completed"

        experiments.append({
            "sku": sku,
            "name": exp["name"],
            "status": status,
            "start_date": exp["experiment_start"],
            "end_date": exp["experiment_end"],
            "days_remaining": days_remaining,
            "days_elapsed": days_elapsed,
            "progress_pct": progress,
            "hypothesis": exp["hypothesis"],
            "can_list": status == "completed",
            "action_required": "实验进行中，等待到期后评估" if status == "running" else
                               "实验已结束，建议评估后决定是否上架" if status == "completed" else
                               "实验未开始",
        })

    return {
        "checked_at": now.isoformat(),
        "total_experiments": len(experiments),
        "running": sum(1 for e in experiments if e["status"] == "running"),
        "completed": sum(1 for e in experiments if e["status"] == "completed"),
        "experiments": experiments,
    }


def replace_1688_mock_data(
    product_id: str,
    real_data: dict[str, Any],
) -> dict[str, Any]:
    """
    替换产品的示例 1688 数据为真实数据

    Args:
        product_id: 产品 ID
        real_data: 真实 1688 数据（来自 1688 API）

    Returns:
        替换结果
    """
    if not real_data:
        return {"success": False, "error": "真实数据为空", "product_id": product_id}

    # 验证真实数据结构
    required_fields = ["product_id", "subject", "price"]
    missing = [f for f in required_fields if f not in real_data]
    if missing:
        return {
            "success": False,
            "error": f"真实数据缺少必要字段: {missing}",
            "product_id": product_id,
        }

    # 构建替换后的数据
    replaced = {
        "success": True,
        "product_id": product_id,
        "replaced_at": datetime.utcnow().isoformat(),
        "source": "1688_api_real",
        "original_mock_replaced": True,
        "real_1688_data": {
            "product_id": real_data.get("product_id"),
            "subject": real_data.get("subject"),
            "price": real_data.get("price"),
            "price_range": real_data.get("price_range", []),
            "sale_quantity": real_data.get("sale_quantity", 0),
            "supplier": real_data.get("company_name", real_data.get("supplier_login_id", "")),
            "detail_url": real_data.get("detail_url", ""),
            "images": real_data.get("images", []),
            "attributes": real_data.get("attributes", []),
        },
    }

    logger.info("Replaced mock 1688 data for product %s", product_id)
    return replaced


def get_listing_status() -> dict[str, Any]:
    """
    获取上架状态总览

    Returns:
        上架状态
    """
    # 检查 WooCommerce 连接
    wc_connected = bool(WC_CONSUMER_KEY and WC_CONSUMER_SECRET)

    # 实验状态
    exp_status = check_experiment_status()

    return {
        "woocommerce_connected": wc_connected,
        "woocommerce_url": WC_URL,
        "experiment_status": exp_status,
        "restricted_keywords": RESTRICTED_KEYWORDS,
        "note": "管制物品自动过滤；实验产品在实验期内不上架；1688真实数据替换需配置ALI1688_APP_KEY",
    }
