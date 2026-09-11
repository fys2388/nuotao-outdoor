"""产品映射服务（占位模块，待实现）。

用于 WooCommerce 产品与本地产品的映射关系管理。
"""

from typing import Any


def get_all_mappings() -> dict[str, Any]:
    """获取所有产品映射关系（占位实现，返回空结果）。"""
    return {"success": False, "data": {"mappings": []}, "error": "产品映射服务尚未实现"}


def get_mapping_by_woocommerce_id(woocommerce_id: int) -> dict[str, Any] | None:
    """根据 WooCommerce 产品 ID 获取映射（占位实现）。"""
    return None


def create_mapping(woocommerce_id: int, local_product_id: int) -> dict[str, Any]:
    """创建产品映射（占位实现）。"""
    return {"success": False, "error": "产品映射服务尚未实现"}
