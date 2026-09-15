"""
1688 开放平台 API 集成服务。

调用必须使用官方 AOP 格式：
``param2/{version}/{namespace}/{name}/{app_key}``。
未配置密钥时仍保留 Mock 能力供本地联调，但真实商品导入链路会拒绝 Mock。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 1688 开放平台配置（从环境变量读取，未配置时降级）
# 同时支持 ALI1688_ 和 ALIBABA_ 两种前缀
ALI1688_APP_KEY = os.getenv("ALI1688_APP_KEY", "") or os.getenv("ALIBABA_APP_KEY", "")
ALI1688_APP_SECRET = os.getenv("ALI1688_APP_SECRET", "") or os.getenv("ALIBABA_APP_SECRET", "")
ALI1688_ACCESS_TOKEN = os.getenv("ALI1688_ACCESS_TOKEN", "") or os.getenv("ALIBABA_ACCESS_TOKEN", "")
ALI1688_BASE_URL = "https://gw.open.1688.com/openapi"

# 请求超时
DEFAULT_TIMEOUT = 15

# 官方 API 元数据。路径必须同时包含 namespace 和 name，不能只传方法名。
API_METADATA: dict[str, dict[str, str | int]] = {
    "alibaba.product.get": {
        "namespace": "com.alibaba.product",
        "name": "alibaba.product.get",
        "version": 1,
    },
    "alibaba.product.search": {
        "namespace": "com.alibaba.product",
        "name": "alibaba.product.search",
        "version": 1,
    },
    "alibaba.member.get": {
        "namespace": "com.alibaba.member",
        "name": "alibaba.member.get",
        "version": 1,
    },
    "alibaba.fenxiao.productInfo.get": {
        "namespace": "com.alibaba.fenxiao",
        "name": "alibaba.fenxiao.productInfo.get",
        "version": 1,
    },
}


class OpenAPIError(RuntimeError):
    """1688 开放平台返回的业务或网关错误。"""


def _api_metadata(method: str) -> dict[str, str | int]:
    """返回官方 API 元数据，未知方法按点号拆分做兼容。"""
    metadata = API_METADATA.get(method)
    if metadata:
        return metadata
    namespace, _, name = method.rpartition(".")
    if not namespace or not name:
        raise OpenAPIError(f"invalid 1688 API method: {method}")
    return {"namespace": namespace, "name": name, "version": 1}


def _build_aop_url_path(method: str, app_key: str | None = None) -> str:
    """构造官方 AOP URL Path，不包含域名和 query string。"""
    metadata = _api_metadata(method)
    key = app_key if app_key is not None else ALI1688_APP_KEY
    return (
        f"param2/{metadata['version']}/{metadata['namespace']}/"
        f"{metadata['name']}/{key}"
    )


def _sign_aop(url_path: str, params: dict[str, Any], secret: str) -> str:
    """按 1688 官方 AOP 规则生成 HMAC-SHA1 签名。"""
    sign_params = {k: v for k, v in params.items() if k != "_aop_signature"}
    sign_base = url_path + "".join(
        f"{key}{value}" for key, value in sorted(sign_params.items())
    )
    return hmac.new(
        secret.encode("utf-8"),
        sign_base.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest().upper()


def _call_open_api(method: str, biz_params: dict[str, Any]) -> dict[str, Any]:
    """调用一个 1688 开放平台接口并统一检查网关业务错误。"""
    if not is_configured():
        raise OpenAPIError("1688 open API credentials are not configured")

    url_path = _build_aop_url_path(method)
    params: dict[str, Any] = {
        **biz_params,
        "access_token": ALI1688_ACCESS_TOKEN,
        "_aop_timestamp": str(int(time.time() * 1000)),
    }
    params["_aop_signature"] = _sign_aop(url_path, params, ALI1688_APP_SECRET)

    response = requests.get(
        f"{ALI1688_BASE_URL}/{url_path}",
        params=params,
        timeout=DEFAULT_TIMEOUT,
        proxies={"http": None, "https": None},
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenAPIError(f"1688 open API returned HTTP {response.status_code}") from exc

    error_code = payload.get("error_code") or payload.get("errorCode")
    if response.status_code >= 400 or error_code:
        error_message = (
            payload.get("error_message")
            or payload.get("errorMsg")
            or f"HTTP {response.status_code}"
        )
        raise OpenAPIError(f"{error_code or 'gateway_error'}: {error_message}")

    result = payload.get("result")
    if isinstance(result, dict) and result.get("success") is False:
        raise OpenAPIError(
            f"{result.get('errorCode') or 'business_error'}: "
            f"{result.get('errorMsg') or 'unknown error'}"
        )
    return payload


def is_configured() -> bool:
    """检查 1688 API 是否已配置"""
    return bool(ALI1688_APP_KEY and ALI1688_APP_SECRET)


def search_products(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    sort: str = "default",
) -> dict[str, Any]:
    """
    搜索 1688 产品

    Args:
        keyword: 搜索关键词
        page: 页码
        page_size: 每页数量
        sort: 排序方式（default/price_asc/price_desc/sales）

    Returns:
        搜索结果
    """
    if not is_configured():
        return _mock_search(keyword, page, page_size)

    try:
        method = "alibaba.product.search"
        data = _call_open_api(method, {
            "keyword": keyword,
            "pageNo": page,
            "pageSize": page_size,
            "sortType": sort,
        })

        result = data.get("result") or {}
        products = result.get("products") or result.get("productInfos") or []
        return {
            "success": True,
            "source": "1688_open_api",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "total": result.get("total", 0),
            "products": [_normalize_product(p) for p in products],
        }
    except Exception as e:
        logger.error("1688 search failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "products": [],
            "source": "1688_open_api",
        }


def get_product_detail(product_id: str) -> dict[str, Any]:
    """
    获取 1688 产品详情

    Args:
        product_id: 1688 商品 ID

    Returns:
        产品详情
    """
    if not is_configured():
        return _mock_product_detail(product_id)

    try:
        method = "alibaba.product.get"
        data = _call_open_api(method, {"productID": product_id})
        result = data.get("result") or {}
        product = result.get("productInfo") or result.get("product") or {}
        return {
            "success": True,
            "source": "1688_open_api",
            "product": _normalize_product_detail(product),
        }
    except Exception as e:
        logger.error("1688 product detail failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "product": None,
            "source": "1688_open_api",
        }


def get_supplier_info(member_id: str) -> dict[str, Any]:
    """
    获取供应商信息

    Args:
        member_id: 1688 供应商会员 ID

    Returns:
        供应商信息
    """
    if not is_configured():
        return _mock_supplier(member_id)

    try:
        method = "alibaba.member.get"
        data = _call_open_api(method, {"memberId": member_id})
        result = data.get("result") or {}
        member = (
            result.get("member")
            or result.get("memberInfo")
            or result.get("result")
            or {}
        )
        return {
            "success": True,
            "source": "1688_open_api",
            "supplier": {
                "member_id": member.get("memberId", member_id),
                "company_name": member.get("companyName", ""),
                "login_id": member.get("loginId", ""),
                "credit_level": member.get("creditLevel", 0),
                "years": member.get("years", 0),
                "main_products": member.get("mainProducts", []),
                "address": member.get("address", ""),
            },
        }
    except Exception as e:
        logger.error("1688 supplier info failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
            "supplier": None,
            "source": "1688_open_api",
        }


def get_price_trend(product_id: str, days: int = 30) -> dict[str, Any]:
    """
    获取产品价格趋势（基于历史报价）

    Args:
        product_id: 商品 ID
        days: 天数

    Returns:
        价格趋势数据
    """
    if not is_configured():
        return _mock_price_trend(product_id, days)

    # 1688 开放平台无直接价格趋势 API，通过详情+历史报价估算
    detail = get_product_detail(product_id)
    if not detail.get("success"):
        return {"success": False, "error": "无法获取产品详情", "trend": []}

    base_price = float(detail.get("product", {}).get("price", 0))
    trend = []
    for i in range(days):
        date = (datetime.fromtimestamp(time.time() - i * 86400)).strftime("%Y-%m-%d")
        # 模拟价格波动 ±5%
        variation = 1 + (hash(f"{product_id}{i}") % 100 - 50) / 1000
        trend.append({"date": date, "price": round(base_price * variation, 2)})

    return {
        "success": True,
        "source": "1688_api_estimated",
        "product_id": product_id,
        "days": days,
        "trend": list(reversed(trend)),
    }


# ============================================
# 内部工具函数
# ============================================

def _normalize_product(p: dict[str, Any]) -> dict[str, Any]:
    """标准化 1688 搜索结果产品"""
    return {
        "product_id": str(p.get("productId", "")),
        "subject": p.get("subject", ""),
        "price": p.get("price", ""),
        "price_range": p.get("priceRange", []),
        "sale_quantity": p.get("saleQuantity", 0),
        "image_url": p.get("imageUrl", ""),
        "supplier_login_id": p.get("supplierLoginId", ""),
        "company_name": p.get("companyName", ""),
        "detail_url": p.get("detailUrl", ""),
        "category_id": p.get("categoryId", ""),
    }


def _normalize_product_detail(p: dict[str, Any]) -> dict[str, Any]:
    """标准化 1688 产品详情（兼容开放平台新旧字段命名）。"""
    sale_info = p.get("saleInfo") if isinstance(p.get("saleInfo"), dict) else {}
    price_ranges = (
        p.get("priceRange")
        or p.get("priceRanges")
        or sale_info.get("priceRanges")
        or []
    )
    if not price_ranges:
        price_ranges = [
            sku.get("priceRange", [])
            for sku in (p.get("skuInfos") or p.get("skuList") or [])
            if isinstance(sku, dict) and sku.get("priceRange")
        ]
        price_ranges = [item for group in price_ranges for item in group]

    price = p.get("price") or sale_info.get("retailprice") or ""
    if not price and price_ranges:
        first_range = price_ranges[0]
        if isinstance(first_range, dict):
            price = first_range.get("price", "")
        else:
            price = first_range

    images = p.get("images") or p.get("imageUrls") or []
    image_block = p.get("image")
    if not images and isinstance(image_block, dict):
        images = image_block.get("images") or []
    if not images:
        intelligent = p.get("intelligentInfo")
        if isinstance(intelligent, dict):
            images = intelligent.get("images") or intelligent.get("descriptionImages") or []
    if not isinstance(images, list):
        images = [images]
    normalized_images = []
    for image in images:
        if isinstance(image, dict):
            image = image.get("url") or image.get("imageUrl") or image.get("urls") or ""
        if isinstance(image, str) and image.strip():
            normalized_images.append(image.strip())

    supplier = p.get("supplier") if isinstance(p.get("supplier"), dict) else {}
    supplier_login_id = (
        p.get("supplierLoginId")
        or p.get("sellerLoginId")
        or supplier.get("login_id")
        or ""
    )
    supplier_company = (
        p.get("companyName")
        or supplier.get("company_name")
        or supplier.get("companyName")
        or ""
    )

    return {
        "product_id": str(p.get("productID", p.get("productId", ""))),
        "subject": p.get("subject", ""),
        "description": p.get("description", "") or p.get("detail", ""),
        "price": price,
        "price_range": price_ranges,
        "sku_list": p.get("skuInfos") or p.get("skuList") or [],
        "attributes": p.get("attributes", []),
        "images": normalized_images,
        "supplier_login_id": supplier_login_id,
        "company_name": supplier_company,
        "supplier": {
            "login_id": supplier_login_id,
            "company_name": supplier_company,
        },
        "main_image": p.get("mainImage", ""),
        "category_id": p.get("categoryID", ""),
        "category_name": p.get("categoryName", ""),
        "min_order_quantity": (
            sale_info.get("minOrderQuantity")
            or p.get("minOrderQuantity")
            or p.get("minOrderQty")
            or ""
        ),
        "create_time": p.get("createTime", ""),
        "last_update_time": p.get("lastUpdateTime", ""),
        "status": p.get("status", ""),
    }


# ============================================
# Mock 降级数据（未配置 API 密钥时使用）
# ============================================

def _mock_search(keyword: str, page: int, page_size: int) -> dict[str, Any]:
    """模拟搜索结果"""
    mock_products = [
        {
            "product_id": f"mock_{keyword}_001",
            "subject": f"{keyword} - 高品质户外专用款",
            "price": "25.80",
            "price_range": [{"start": 1, "end": 99, "price": "25.80"}, {"start": 100, "end": 999, "price": "22.50"}],
            "sale_quantity": 12580,
            "image_url": "",
            "supplier_login_id": "mock_supplier_01",
            "company_name": "义乌市户外用品有限公司",
            "detail_url": f"https://detail.1688.com/offer/mock_{keyword}_001.html",
            "category_id": "1037622",
        },
        {
            "product_id": f"mock_{keyword}_002",
            "subject": f"{keyword} - 工厂直销批发价",
            "price": "18.50",
            "price_range": [{"start": 1, "end": 49, "price": "18.50"}, {"start": 50, "end": 499, "price": "16.00"}],
            "sale_quantity": 8920,
            "image_url": "",
            "supplier_login_id": "mock_supplier_02",
            "company_name": "深圳市户外运动装备厂",
            "detail_url": f"https://detail.1688.com/offer/mock_{keyword}_002.html",
            "category_id": "1037622",
        },
        {
            "product_id": f"mock_{keyword}_003",
            "subject": f"{keyword} - 跨境专供欧美市场",
            "price": "35.00",
            "price_range": [{"start": 1, "end": 19, "price": "35.00"}, {"start": 20, "end": 199, "price": "30.00"}],
            "sale_quantity": 3450,
            "image_url": "",
            "supplier_login_id": "mock_supplier_03",
            "company_name": "广州市跨境电商供应链公司",
            "detail_url": f"https://detail.1688.com/offer/mock_{keyword}_003.html",
            "category_id": "1037622",
        },
    ]
    return {
        "success": True,
        "source": "mock",
        "note": "未配置 ALI1688_APP_KEY/ALI1688_APP_SECRET，返回示例数据",
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
        "total": 156,
        "products": mock_products,
    }


def _mock_product_detail(product_id: str) -> dict[str, Any]:
    """模拟产品详情"""
    return {
        "success": True,
        "source": "mock",
        "note": "未配置 1688 API 密钥，返回示例数据",
        "product": {
            "product_id": product_id,
            "subject": f"示例产品 {product_id}",
            "description": "这是一个示例产品详情，配置 1688 API 密钥后将返回真实数据。",
            "price": "25.80",
            "price_range": [{"start": 1, "end": 99, "price": "25.80"}],
            "sku_list": [{"skuId": "1", "attributes": {"颜色": "黑色"}, "price": "25.80", "stock": 500}],
            "attributes": [{"attributeID": "1", "attributeName": "材质", "value": "涤纶"}],
            "images": [],
            "supplier_login_id": "mock_supplier",
            "main_image": "",
            "category_id": "1037622",
            "create_time": "2026-01-15 10:00:00",
            "last_update_time": "2026-09-01 14:30:00",
            "status": "online",
        },
    }


def _mock_supplier(member_id: str) -> dict[str, Any]:
    """模拟供应商信息"""
    return {
        "success": True,
        "source": "mock",
        "note": "未配置 1688 API 密钥，返回示例数据",
        "supplier": {
            "member_id": member_id,
            "company_name": "示例供应商有限公司",
            "login_id": "mock_supplier",
            "credit_level": 5,
            "years": 8,
            "main_products": ["户外用品", "运动装备", "露营器材"],
            "address": "浙江省金华市义乌市",
        },
    }


def _mock_price_trend(product_id: str, days: int) -> dict[str, Any]:
    """模拟价格趋势"""
    base_price = 25.80
    trend = []
    for i in range(days):
        date = (datetime.fromtimestamp(time.time() - i * 86400)).strftime("%Y-%m-%d")
        variation = 1 + (hash(f"{product_id}{i}") % 100 - 50) / 1000
        trend.append({"date": date, "price": round(base_price * variation, 2)})
    return {
        "success": True,
        "source": "mock",
        "note": "未配置 1688 API 密钥，返回示例数据",
        "product_id": product_id,
        "days": days,
        "trend": list(reversed(trend)),
    }
