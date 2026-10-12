"""
1688 商品页面解析服务 - 提取 SKU 变体信息

从 1688 商品页面的 JavaScript 变量中提取 SKU 列表和价格信息。
1688 页面的 SKU 数据通常在以下变量中：
- window.offerDetailData
- window.skuInfo
- window.__INIT_DATA__
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)


# 常见的 SKU 数据变量名
SKU_VARIABLES = [
    "window.offerDetailData",
    "window.skuInfo",
    "window.__INIT_DATA__",
    "window.__NUXT__",
    "window.SKU_INFO",
    "window.sku_data",
]

# SKU 数据可能的字段路径
SKU_PATHS = [
    ("skuList",),
    ("skuInfo", "skuList"),
    ("data", "skuList"),
    ("product", "skuList"),
    ("sku", "skuList"),
    ("offers", "skuList"),
    ("offer", "skuList"),
    ("detail", "skuList"),
]

# SKU 数据可能的字段名
SKU_FIELDS = [
    "skuName",
    "sku_name",
    "name",
    "title",
    "specName",
    "propertyValue",
]

PRICE_FIELDS = [
    "price",
    "skuPrice",
    "sku_price",
    "offerPrice",
    "priceInfo",
    "priceRange",
]


def fetch_1688_page(url: str, timeout: int = 30) -> str:
    """
    获取 1688 商品页面 HTML
    
    Args:
        url: 1688 商品 URL
        timeout: 请求超时时间
    
    Returns:
        HTML 内容
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.1688.com/",
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    except Exception as e:
        logger.warning("Failed to fetch 1688 page %s: %s", url, str(e))
        return ""


def extract_js_variables(html: str) -> dict[str, Any]:
    """
    从 HTML 中提取 JavaScript 变量
    
    Args:
        html: HTML 内容
    
    Returns:
        变量名到值的映射
    """
    variables = {}
    
    # 模式 1: var variableName = {...};
    pattern1 = r'var\s+(\w+)\s*=\s*(\{.*?\});'
    matches = re.findall(pattern1, html, re.DOTALL)
    for var_name, var_value in matches:
        if var_name in SKU_VARIABLES or "sku" in var_name.lower():
            variables[var_name] = var_value
    
    # 模式 2: window.variableName = {...}
    pattern2 = r'window\.(\w+)\s*=\s*(\{.*?\});'
    matches = re.findall(pattern2, html, re.DOTALL)
    for var_name, var_value in matches:
        full_name = f"window.{var_name}"
        if full_name in SKU_VARIABLES or "sku" in var_name.lower():
            variables[full_name] = var_value
    
    return variables


def parse_sku_data(sku_json_str: str) -> list[dict[str, Any]]:
    """
    解析 SKU JSON 数据
    
    Args:
        sku_json_str: JSON 字符串
    
    Returns:
        SKU 列表
    """
    import json
    
    try:
        data = json.loads(sku_json_str)
    except (json.JSONDecodeError, TypeError):
        # 尝试修复常见的 JSON 问题
        try:
            # 移除尾部逗号
            cleaned = re.sub(r',\s*}', '}', sku_json_str)
            cleaned = re.sub(r',\s*]', ']', cleaned)
            data = json.loads(cleaned)
        except Exception:
            logger.warning("Failed to parse SKU JSON")
            return []
    
    return _extract_sku_list(data)


def _extract_sku_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从数据字典中提取 SKU 列表
    
    支持多种嵌套结构：
    - data.skuList
    - data.skuInfo.skuList
    - data.data.skuList
    - 等等
    """
    if not isinstance(data, dict):
        return []
    
    # 直接返回如果是列表
    if isinstance(data.get("skuList"), list):
        return data["skuList"]
    if isinstance(data.get("sku_list"), list):
        return data["sku_list"]
    
    # 递归搜索 skuList
    for path in SKU_PATHS:
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                current = None
                break
        if isinstance(current, list):
            return current
    
    # 搜索所有嵌套的列表
    def find_sku_list(obj, depth=0):
        if depth > 5:
            return []
        if isinstance(obj, list):
            # 检查是否是 SKU 列表
            if obj and isinstance(obj[0], dict):
                first = obj[0]
                # 检查是否有 SKU 相关字段
                if any(f in first for f in SKU_FIELDS):
                    return obj
            # 检查列表中的每个元素
            for item in obj[:10]:
                result = find_sku_list(item, depth + 1)
                if result:
                    return result
            return []
        elif isinstance(obj, dict):
            # 检查当前字典
            if "skuList" in obj and isinstance(obj["skuList"], list):
                return obj["skuList"]
            if "sku_list" in obj and isinstance(obj["sku_list"], list):
                return obj["sku_list"]
            # 递归搜索
            for key in ["skuList", "skuInfo", "data", "product", "offer", "detail"]:
                if key in obj:
                    result = find_sku_list(obj[key], depth + 1)
                    if result:
                        return result
            # 搜索所有值
            for value in obj.values():
                if isinstance(value, (dict, list)):
                    result = find_sku_list(value, depth + 1)
                    if result:
                        return result
        return []
    
    return find_sku_list(data)


def normalize_sku_item(sku: dict[str, Any]) -> dict[str, Any]:
    """
    标准化 SKU 项，提取名称和价格
    
    Args:
        sku: 原始 SKU 字典
    
    Returns:
        标准化后的 SKU 字典
    """
    # 提取名称
    name = ""
    for field in SKU_FIELDS:
        if field in sku and sku[field]:
            name = str(sku[field])
            break
    
    # 如果没有名称，尝试从嵌套字段提取
    if not name:
        # 尝试从 propertyValue 或 similar 提取
        for key in ["propertyValue", "specName", "spec", "attribute"]:
            if key in sku and sku[key]:
                val = sku[key]
                if isinstance(val, str):
                    name = val
                elif isinstance(val, dict):
                    name = str(val.get("name", "") or val.get("value", ""))
                break
    
    # 提取价格
    price = 0.0
    for field in PRICE_FIELDS:
        if field in sku and sku[field]:
            val = sku[field]
            if isinstance(val, (int, float)):
                price = float(val)
                break
            elif isinstance(val, str):
                try:
                    price = float(val.replace("¥", "").replace(",", "").strip())
                    break
                except (ValueError, TypeError):
                    pass
    
    return {
        "name": name,
        "price": str(price) if price > 0 else "",
        "sku": sku.get("skuId", sku.get("sku_id", sku.get("id", ""))),
        "stock": sku.get("stock", sku.get("stockCount", 100)),
    }


def extract_variations_from_url(url: str) -> list[dict[str, Any]]:
    """
    从 1688 URL 提取 SKU 变体
    
    Args:
        url: 1688 商品 URL
    
    Returns:
        标准化的 SKU 变体列表
    """
    html = fetch_1688_page(url)
    if not html:
        return []
    
    variables = extract_js_variables(html)
    sku_list = []
    
    for var_name, var_value in variables.items():
        parsed = parse_sku_data(var_value)
        if parsed:
            sku_list = parsed
            break
    
    if not sku_list:
        logger.warning("No SKU list found in 1688 page for %s", url)
        return []
    
    # 标准化
    variations = []
    for sku in sku_list[:20]:  # 最多 20 个变体
        normalized = normalize_sku_item(sku)
        if normalized["name"]:
            variations.append(normalized)
    
    logger.info("Extracted %d variations from 1688 page: %s", len(variations), url)
    return variations


def find_best_price(variations: list[dict[str, Any]], 
                    keywords: list[str] | None = None) -> float:
    """
    从变体列表中找到最佳价格
    
    优先级：
    1. 包含指定关键词的变体（如太阳能、充电）
    2. 最高价变体
    
    Args:
        variations: 变体列表
        keywords: 优先关键词
    
    Returns:
        最佳价格
    """
    if not variations:
        return 0.0
    
    # 默认关键词：太阳能、充电相关
    if keywords is None:
        keywords = ["太阳能", "充电", "solar", "charging", "USB", "usb"]
    
    best_price = 0.0
    best_sku = None
    
    for var in variations:
        name = var.get("name", "").lower()
        is_preferred = any(kw.lower() in name for kw in keywords)
        
        try:
            price = float(var.get("price", 0) or 0)
        except (ValueError, TypeError):
            price = 0.0
        
        # 优先选择包含关键词的变体，且价格最高
        if is_preferred and price > best_price:
            best_price = price
            best_sku = var
        elif price > best_price:
            best_price = price
            best_sku = var
    
    return best_price
