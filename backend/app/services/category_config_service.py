"""品类配置服务 — 从 strategy_versions 表加载品类配置，支持缓存。

品类配置由迁移 0074 写入 strategy_versions 表，每个品类对应一条
strategy_type="category_{name}" 的记录。

设计原则（AGENTS.md）：
- 禁止凭感觉：所有品类参数（Brand Fit、毛利率、重量上限等）来自配置，
  不硬编码在业务逻辑中。
- 可审计：配置变更通过 strategy_updater 记录版本，可回滚。
- 优雅降级：配置加载失败时返回默认值，不阻断工作流。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.strategy_version import StrategyVersion

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 品类代码 → strategy_type 映射
# --------------------------------------------------------------------------- #

CATEGORY_STRATEGY_TYPES: dict[str, str] = {
    "camping_lighting": "category_camping_lighting",
    "camping_cooking": "category_camping_cooking",
    "outdoor_storage": "category_outdoor_storage",
    "hydration": "category_hydration",
    "hiking_accessories": "category_hiking_accessories",
}

# 排除品类 strategy_type
EXCLUDED_CATEGORIES_TYPE = "category_excluded"

# --------------------------------------------------------------------------- #
# 默认配置（配置加载失败时的降级值）
# --------------------------------------------------------------------------- #

DEFAULT_CATEGORY_CONFIG: dict[str, Any] = {
    "name": "未知品类",
    "priority": "explore",
    "brand_fit_base": 7.0,
    "target_margin": 0.30,
    "max_weight_kg": 2.0,
    "sku_target_min": 1,
    "sku_target_max": 5,
    "seasonal_weight": {"Q1": 1.0, "Q2": 1.0, "Q3": 1.0, "Q4": 1.0},
    "compliance_requirements": [],
    "banned_subcategories": [],
    "hero_candidates": [],
    "content_angles": [],
    "keywords_1688": [],
}


# --------------------------------------------------------------------------- #
# 品类配置加载
# --------------------------------------------------------------------------- #

async def load_category_config(
    session: AsyncSession,
    *,
    category: str,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """加载单个品类的配置。

    Args:
        session: 数据库会话。
        category: 品类代码（如 "camping_lighting"）。
        workspace_id: 工作空间 ID，默认 DEFAULT_WORKSPACE_ID。

    Returns:
        品类配置 dict，加载失败时返回 DEFAULT_CATEGORY_CONFIG。
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    strategy_type = CATEGORY_STRATEGY_TYPES.get(category)

    if strategy_type is None:
        logger.warning("未知品类代码: %s，返回默认配置", category)
        return dict(DEFAULT_CATEGORY_CONFIG)

    try:
        result = await session.execute(
            select(StrategyVersion.new_config)
            .where(
                StrategyVersion.workspace_id == ws,
                StrategyVersion.strategy_type == strategy_type,
            )
            .order_by(StrategyVersion.version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            config = dict(DEFAULT_CATEGORY_CONFIG)
            config.update(row)
            return config
        else:
            logger.warning("品类配置不存在: %s，返回默认配置", category)
            return dict(DEFAULT_CATEGORY_CONFIG)
    except Exception as exc:
        logger.warning("加载品类配置失败: %s, %s", category, exc)
        return dict(DEFAULT_CATEGORY_CONFIG)


async def load_all_category_configs(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
) -> dict[str, dict[str, Any]]:
    """加载所有品类配置。

    Returns:
        {category_code: config_dict} 映射。
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    configs: dict[str, dict[str, Any]] = {}

    for category, strategy_type in CATEGORY_STRATEGY_TYPES.items():
        try:
            result = await session.execute(
                select(StrategyVersion.new_config)
                .where(
                    StrategyVersion.workspace_id == ws,
                    StrategyVersion.strategy_type == strategy_type,
                )
                .order_by(StrategyVersion.version.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row:
                config = dict(DEFAULT_CATEGORY_CONFIG)
                config.update(row)
                configs[category] = config
        except Exception as exc:
            logger.warning("加载品类配置失败: %s, %s", category, exc)

    return configs


async def load_excluded_categories(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """加载排除品类列表（用于 V5 品牌聚焦否决）。

    Returns:
        排除品类列表，加载失败时返回空列表。
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID

    try:
        result = await session.execute(
            select(StrategyVersion.new_config)
            .where(
                StrategyVersion.workspace_id == ws,
                StrategyVersion.strategy_type == EXCLUDED_CATEGORIES_TYPE,
            )
            .order_by(StrategyVersion.version.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row:
            return row.get("excluded_categories", [])
        return []
    except Exception as exc:
        logger.warning("加载排除品类失败: %s", exc)
        return []


# --------------------------------------------------------------------------- #
# 品类配置查询辅助
# --------------------------------------------------------------------------- #

def is_category_excluded(excluded_list: list[dict], category_name: str) -> bool:
    """检查品类是否在排除列表中。"""
    for excluded in excluded_list:
        if excluded.get("name", "").lower() == category_name.lower():
            return True
    return False


def get_category_brand_fit_base(config: dict[str, Any]) -> float:
    """获取品类的 Brand Fit 基础分。"""
    return float(config.get("brand_fit_base", DEFAULT_CATEGORY_CONFIG["brand_fit_base"]))


def get_category_target_margin(config: dict[str, Any]) -> float:
    """获取品类的目标毛利率。"""
    return float(config.get("target_margin", DEFAULT_CATEGORY_CONFIG["target_margin"]))


def get_category_max_weight(config: dict[str, Any]) -> float:
    """获取品类的最大重量限制（kg）。"""
    return float(config.get("max_weight_kg", DEFAULT_CATEGORY_CONFIG["max_weight_kg"]))


def get_category_keywords(config: dict[str, Any]) -> list[str]:
    """获取品类的 1688 搜索关键词列表。"""
    return config.get("keywords_1688", [])


def get_category_seasonal_weight(
    config: dict[str, Any],
    quarter: str,
) -> float:
    """获取品类在指定季度的季节性权重。"""
    seasonal = config.get("seasonal_weight", {})
    return float(seasonal.get(quarter, 1.0))


def get_category_compliance_requirements(config: dict[str, Any]) -> list[str]:
    """获取品类的合规要求列表。"""
    return config.get("compliance_requirements", [])


def get_category_banned_subcategories(config: dict[str, Any]) -> list[str]:
    """获取品类的禁售子品类列表。"""
    return config.get("banned_subcategories", [])
