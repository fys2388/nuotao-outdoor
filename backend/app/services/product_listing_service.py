"""
产品上架管理服务
支持：上架队列管理、实验产品跟踪、批量上架WooCommerce、1688数据替换
管制物品自动过滤（刀具/危险品等）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import requests

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# WooCommerce 配置（从 .env 文件读取，通过 config 对象）
settings = get_settings()
WC_URL = settings.woocommerce_url
WC_CONSUMER_KEY = settings.woocommerce_consumer_key
WC_CONSUMER_SECRET = settings.woocommerce_consumer_secret

import io
import hashlib

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


def upload_image_to_woocommerce(image_path: str, alt_text: str = "") -> dict[str, Any]:
    """
    上传本地图片到 WooCommerce 媒体库（使用 WordPress Application Password）
    
    Args:
        image_path: 本地图片路径
        alt_text: 图片替代文本
    
    Returns:
        {"success": bool, "url": str, "id": int} 或 {"success": False, "error": str}
    """
    # 使用 WordPress Application Password（不是 WooCommerce API keys）
    wp_user = settings.wordpress_user
    wp_app_password = settings.wordpress_app_password
    
    if not wp_user or not wp_app_password:
        return {"success": False, "error": "WordPress Application Password 未配置"}
    
    try:
        # WordPress Media API
        url = f"{WC_URL}/wp-json/wp/v2/media"
        
        with open(image_path, 'rb') as f:
            files = {
                'file': (image_path.split('/')[-1], f, 'image/png'),
            }
            data = {
                'title': alt_text or image_path.split('/')[-1],
                'alt_text': alt_text,
            }
            
            resp = requests.post(
                url,
                auth=(wp_user, wp_app_password),  # Application Password 认证
                files=files,
                data=data,
                timeout=60,
            )
        
        if resp.status_code not in [200, 201]:
            return {"success": False, "error": f"Upload failed: {resp.status_code} {resp.text[:200]}"}
        
        result = resp.json()
        return {
            "success": True,
            "url": result.get("source_url", ""),
            "id": result.get("id"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


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
        product: 产品数据（可能包含 woocommerce_data 字段）
        status: 上架状态（publish/draft/pending）

    Returns:
        上架结果
    """
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        return {"success": False, "error": "WooCommerce API 密钥未配置", "sku": product.get("sku")}

    try:
        url = f"{WC_URL}/wp-json/wc/v3/products"
        
        # 优先使用 woocommerce_data 字段（包含英文本地化）
        wc_data = product.get("woocommerce_data", product)
        
        data = {
            "name": wc_data.get("name", product.get("name", "")),
            "type": "simple",
            "regular_price": str(wc_data.get("regular_price", product.get("regular_price", ""))),
            "description": wc_data.get("description", product.get("description", "")),
            "short_description": wc_data.get("short_description", product.get("short_description", "")),
            "sku": wc_data.get("sku", product.get("sku", "")),
            "manage_stock": True,
            "stock_quantity": wc_data.get("stock_quantity", product.get("stock_quantity", 0)),
            "status": status,
            "categories": wc_data.get("categories", product.get("categories", [{"id": 15}])),
            "tags": wc_data.get("tags", product.get("tags", [])),
        }
        if wc_data.get("sale_price"):
            data["sale_price"] = str(wc_data["sale_price"])
        
        # 图片处理：优先上传本地图片到 WooCommerce 媒体库
        images = wc_data.get("images", [])
        if images:
            wc_images = []
            for img in images[:5]:  # 最多上传 5 张
                if isinstance(img, dict):
                    img_url = img.get("src") or img.get("url") or img.get("source_url")
                else:
                    img_url = img
                
                if img_url and img_url.startswith("http"):
                    # 外部 URL 直接使用
                    wc_images.append({"src": img_url})
                elif img_url and img_url.startswith("/static/"):
                    # 本地静态文件，上传到 WooCommerce
                    from pathlib import Path
                    backend_dir = Path(__file__).resolve().parents[2]
                    local_path = backend_dir / img_url.replace("/static/ai_images/", "data/ai_generated_images/")
                    
                    if local_path.exists():
                        upload_result = upload_image_to_woocommerce(str(local_path), alt_text=wc_data.get("name", ""))
                        if upload_result["success"]:
                            wc_images.append({"src": upload_result["url"]})
                        else:
                            logger.warning("Failed to upload local image %s: %s", img_url, upload_result.get("error"))
                    else:
                        logger.warning("Local image not found: %s", local_path)
                elif img_url:
                    # 其他 URL 直接使用
                    wc_images.append({"src": img_url})
            
            if wc_images:
                data["images"] = wc_images
            else:
                logger.warning("No valid image URLs found for product %s", product.get("sku"))
        
        # 品牌（通过产品属性设置）
        brand = wc_data.get("brand", "Nuotao")
        if brand:
            data["attributes"] = [
                {
                    "id": 0,
                    "name": "Brand",
                    "options": [brand],
                    "visible": True,
                    "variation": False,
                }
            ]
        
        # Meta data（包含 SEO 元数据）
        meta_data = wc_data.get("meta_data", [])
        if meta_data:
            data["meta_data"] = meta_data
        
        # RankMath SEO 特定字段
        seo_title = next((m["value"] for m in meta_data if m.get("key") == "seo_title"), wc_data.get("name", ""))
        seo_description = next((m["value"] for m in meta_data if m.get("key") == "seo_description"), wc_data.get("short_description", ""))
        focus_keyword = next((m["value"] for m in meta_data if m.get("key") == "focus_keyword"), "")
        
        if seo_title:
            data["meta_data"].append({"key": "_rank_math_seo_title", "value": seo_title})
        if seo_description:
            data["meta_data"].append({"key": "_rank_math_seo_description", "value": seo_description})
        if focus_keyword:
            data["meta_data"].append({"key": "_rank_math_focus_keyword", "value": focus_keyword})
        
        # 确保 meta_data 存在
        if "meta_data" not in data:
            data["meta_data"] = []
        # 添加品牌到 meta_data
        data["meta_data"].append({"key": "brand", "value": brand})

        resp = requests.post(
            url,
            auth=(WC_CONSUMER_KEY, WC_CONSUMER_SECRET),
            json=data,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        product_id = result.get("id")

        return {
            "success": True,
            "sku": wc_data.get("sku", product.get("sku")),
            "woocommerce_id": product_id,
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


def upload_image_to_wordpress(image_url: str, alt_text: str = "") -> dict[str, Any]:
    """
    上传图片到 WordPress 媒体库
    
    Args:
        image_url: 图片 URL
        alt_text: 图片替代文本
    
    Returns:
        {"success": True, "attachment_id": id, "url": url} 或 {"success": False, "error": msg}
    """
    try:
        # 下载图片
        resp = requests.get(image_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        
        # 获取图片内容
        image_data = resp.content
        
        # 获取文件名
        url_path = image_url.split("?")[0]
        filename = url_path.split("/")[-1] if url_path.split("/")[-1] else "product_image.jpg"
        
        # 通过 WordPress Media API 上传
        wp_url = f"{WC_URL}/wp-json/wp/v2/media"
        headers = {
            "Authorization": f"Basic {WC_CONSUMER_KEY}:{WC_CONSUMER_SECRET}",
        }
        files = {
            "file": (filename, image_data, "image/jpeg"),
        }
        data = {
            "title": alt_text or "Product Image",
            "alt": alt_text or "Product Image",
        }
        
        upload_resp = requests.post(
            wp_url,
            headers=headers,
            files=files,
            data=data,
            timeout=60,
        )
        
        if upload_resp.status_code in (200, 201):
            result = upload_resp.json()
            return {
                "success": True,
                "attachment_id": result.get("id"),
                "url": result.get("source_url"),
            }
        else:
            return {"success": False, "error": f"Upload failed: {upload_resp.text[:200]}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_or_create_brand(brand_name: str) -> dict[str, Any]:
    """
    获取或创建品牌术语
    
    Args:
        brand_name: 品牌名称
    
    Returns:
        {"success": True, "brand_id": id} 或 {"success": False, "error": msg}
    """
    try:
        # 尝试获取现有品牌
        wp_url = f"{WC_URL}/wp-json/wp/v2/product_brand"
        headers = {
            "Authorization": f"Basic {WC_CONSUMER_KEY}:{WC_CONSUMER_SECRET}",
        }
        
        # 获取品牌列表
        resp = requests.get(wp_url, headers=headers, params={"slug": brand_name.lower().replace(" ", "-")}, timeout=30)
        
        if resp.status_code == 200:
            brands = resp.json()
            if brands:
                return {"success": True, "brand_id": brands[0].get("id")}
        
        # 创建新品牌
        create_resp = requests.post(
            wp_url,
            headers=headers,
            json={"name": brand_name},
            timeout=30,
        )
        
        if create_resp.status_code in (200, 201):
            brand = create_resp.json()
            return {"success": True, "brand_id": brand.get("id")}
        else:
            return {"success": False, "error": f"Create brand failed: {create_resp.text[:200]}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


def set_product_brand(product_id: int, brand_id: int) -> dict[str, Any]:
    """
    设置产品品牌
    
    Args:
        product_id: 产品 ID
        brand_id: 品牌 ID
    
    Returns:
        {"success": True} 或 {"success": False, "error": msg}
    """
    try:
        wc_url = f"{WC_URL}/wp-json/wc/v3/products/{product_id}"
        headers = {
            "Authorization": f"Basic {WC_CONSUMER_KEY}:{WC_CONSUMER_SECRET}",
        }
        
        # 获取产品信息
        resp = requests.get(wc_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return {"success": False, "error": f"Get product failed: {resp.text[:200]}"}
        
        product = resp.json()
        
        # 更新产品品牌
        data = {
            "product_brands": [brand_id],
        }
        
        update_resp = requests.put(
            wc_url,
            headers=headers,
            json=data,
            timeout=30,
        )
        
        if update_resp.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": f"Update brand failed: {update_resp.text[:200]}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


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
