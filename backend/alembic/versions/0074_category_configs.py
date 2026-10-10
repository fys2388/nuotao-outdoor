"""0074_category_configs

插入品类配置到 strategy_versions 表：Phase 1 核心品类 + 探索品类的
完整配置（Brand Fit 基础分、毛利率目标、重量上限、季节性权重、
禁售子品类、合规要求等）。

每个品类对应一条 strategy_versions 记录，strategy_type 格式为
"category_{name}"（如 "category_camping_lighting"）。

Revision ID: 0074
Revises: 0073
Create Date: 2026-10-06
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
CHANGED_BY = "migration_0074_category_configs"

# --------------------------------------------------------------------------- #
# 品类配置定义
# --------------------------------------------------------------------------- #

CATEGORY_CONFIGS: list[dict] = [
    {
        "strategy_type": "category_camping_lighting",
        "name": "露营照明",
        "priority": "core_a",
        "brand_fit_base": 9.5,
        "target_margin": 0.45,
        "max_weight_kg": 0.5,
        "sku_target_min": 8,
        "sku_target_max": 12,
        "seasonal_weight": {"Q1": 0.8, "Q2": 0.9, "Q3": 1.2, "Q4": 1.3},
        "compliance_requirements": ["UN38.3 电池运输", "CE 认证", "FCC 认证"],
        "banned_subcategories": ["太阳能灯(>100Wh电池)", "大功率投影灯"],
        "hero_candidates": [
            {"name": "LED 感应头灯（强光远射）", "cost_range_cny": [15, 25], "price_range_usd": [19.99, 24.99], "weight_kg": 0.15, "margin": 0.675},
            {"name": "便携 LED 露营灯（可充电）", "cost_range_cny": [20, 35], "price_range_usd": [24.99, 29.99], "weight_kg": 0.30, "margin": 0.625},
        ],
        "content_angles": [
            "头灯选购指南（光源/续航/防水/重量对比）",
            "露营照明方案推荐（按场景：帐篷/徒步/应急）",
            "头灯 vs 手电筒 vs 营地灯 对比测评",
            "露营灯光色温选择（暖光/冷光/自然光场景）",
            "冬季露营照明装备清单",
        ],
        "keywords_1688": [
            "LED感应头灯 强光远射 充电 户外",
            "露营灯 便携 充电 LED 超长续航",
            "头灯 防水 IPX6 红光 夜视",
            "户外手电筒 USB充电 长续航",
        ],
    },
    {
        "strategy_type": "category_camping_cooking",
        "name": "露营炊具",
        "priority": "core_b",
        "brand_fit_base": 9.0,
        "target_margin": 0.40,
        "max_weight_kg": 1.5,
        "sku_target_min": 6,
        "sku_target_max": 10,
        "seasonal_weight": {"Q1": 0.7, "Q2": 1.2, "Q3": 1.3, "Q4": 1.0},
        "compliance_requirements": ["FDA 食品接触材料认证"],
        "banned_subcategories": ["含PFAS涂层锅具", "含铅漆厨具"],
        "hero_candidates": [
            {"name": "户外便携炉具（一体式）", "cost_range_cny": [20, 35], "price_range_usd": [24.99, 34.99], "weight_kg": 0.30, "margin": 0.575},
        ],
        "content_angles": [
            "露营炊具选购指南（按人数/场景/预算）",
            "炉具对比测评（一体式/分体式/燃油/燃气）",
            "露营厨房收纳方案",
            "3-4 人露营炊具清单推荐",
            "轻量化露营炊具方案（<1kg）",
        ],
        "keywords_1688": [
            "户外炉具 便携 一体式 折叠 防风",
            "户外锅具套装 便携 野营 炊具 铝合金",
            "露营餐具 不锈钢 折叠 便携",
            "户外折叠水壶 硅胶 食品级",
        ],
    },
    {
        "strategy_type": "category_outdoor_storage",
        "name": "户外收纳",
        "priority": "core_c",
        "brand_fit_base": 9.0,
        "target_margin": 0.40,
        "max_weight_kg": 2.0,
        "sku_target_min": 5,
        "sku_target_max": 8,
        "seasonal_weight": {"Q1": 1.0, "Q2": 1.0, "Q3": 1.0, "Q4": 1.0},
        "compliance_requirements": [],
        "banned_subcategories": ["一次性收纳袋", "含致癌染料的尼龙包"],
        "hero_candidates": [
            {"name": "户外防水收纳袋（多尺寸套装）", "cost_range_cny": [10, 20], "price_range_usd": [14.99, 19.99], "weight_kg": 0.20, "margin": 0.625},
        ],
        "content_angles": [
            "露营装备收纳方案（按场景分类）",
            "防水收纳袋选购指南（材质/密封性/承重）",
            "露营背包容量选择指南（30L/40L/60L）",
            "手机防水方案对比（袋/壳/全包）",
            "轻量化露营收纳系统",
        ],
        "keywords_1688": [
            "防水收纳袋 户外 漂流 游泳 干湿分离",
            "户外背包 40L 防水 登山 露营",
            "露营装备收纳箱 便携 折叠",
            "防水手机袋 透明 TPU 触屏",
        ],
    },
    {
        "strategy_type": "category_hydration",
        "name": "水具/Hydration",
        "priority": "explore",
        "brand_fit_base": 8.0,
        "target_margin": 0.35,
        "max_weight_kg": 0.5,
        "sku_target_min": 4,
        "sku_target_max": 6,
        "seasonal_weight": {"Q1": 0.9, "Q2": 1.1, "Q3": 1.2, "Q4": 0.9},
        "compliance_requirements": ["FDA 食品接触材料认证"],
        "banned_subcategories": ["含BPA塑料水壶", "普通玻璃水壶(非户外)"],
        "hero_candidates": [
            {"name": "3L 战术水袋背包", "cost_range_cny": [25, 35], "price_range_usd": [29.99, 34.99], "weight_kg": 0.30, "margin": 0.575},
        ],
        "content_angles": [
            "户外水具选购指南（水壶/水袋/净水器）",
            "水袋背包 vs 双肩包 容量对比",
            "户外饮水方案（便携/大容量/净水）",
            "保温瓶容量选择（500ml/750ml/1L）",
            "夏季户外补水方案",
        ],
        "keywords_1688": [
            "户外水袋 3L 战术 背包式",
            "保温瓶 不锈钢 真空 户外 便携",
            "折叠水壶 硅胶 食品级 便携",
            "水具配件 吸管 杯盖 背带",
        ],
    },
    {
        "strategy_type": "category_hiking_accessories",
        "name": "徒步配件",
        "priority": "explore",
        "brand_fit_base": 9.0,
        "target_margin": 0.35,
        "max_weight_kg": 0.5,
        "sku_target_min": 4,
        "sku_target_max": 6,
        "seasonal_weight": {"Q1": 0.7, "Q2": 1.2, "Q3": 1.3, "Q4": 0.8},
        "compliance_requirements": [],
        "banned_subcategories": ["含石棉的登山杖把套", "无资质的急救药品"],
        "hero_candidates": [
            {"name": "铝合金登山杖（折叠款）", "cost_range_cny": [25, 40], "price_range_usd": [29.99, 39.99], "weight_kg": 0.50, "margin": 0.575},
        ],
        "content_angles": [
            "登山杖选购指南（材质/长度/折叠/锁扣）",
            "徒步装备清单（按难度：新手/进阶/专家）",
            "急救包配置指南（户外/车载/家庭）",
            "多功能工具卡评测（户外/EDC/生存）",
            "徒步杖配件选择（杖尖/雪托/腕带）",
        ],
        "keywords_1688": [
            "登山杖 铝合金 折叠 便携 户外",
            "多功能工具卡 不锈钢 户外 便携",
            "急救包 便携 户外 迷你 旅行",
            "户外指南针 战术 防水 夜光",
            "登山杖配件 杖尖 雪托 替换",
        ],
    },
]

# 排除品类配置（用于一票否决 V5）
EXCLUDED_CATEGORIES: list[dict] = [
    {"name": "服装服饰", "reason": "尺码问题、退货率高、库存风险", "veto_rules": ["V5", "V12"]},
    {"name": "儿童产品", "reason": "合规负担重（CPSIA/CPC）、召回风险", "veto_rules": ["V2", "V3"]},
    {"name": "大型装备(>3kg)", "reason": "物流成本吃掉利润", "veto_rules": ["V9"]},
    {"name": "含锂电池>100Wh", "reason": "国际运输限制", "veto_rules": ["V4"]},
    {"name": "城市时尚品", "reason": "与户外品牌定位不符", "veto_rules": ["V5"]},
    {"name": "纯泳装", "reason": "与户外定位不符", "veto_rules": ["V5"]},
    {"name": "玩具", "reason": "低价杂货感、品牌不符", "veto_rules": ["V5", "V6"]},
    {"name": "一次性用品", "reason": "低价杂货感、品牌不符", "veto_rules": ["V6"]},
]


def upgrade() -> None:
    """插入品类配置到 strategy_versions 表。"""
    for cfg in CATEGORY_CONFIGS:
        new_config = {
            "name": cfg["name"],
            "priority": cfg["priority"],
            "brand_fit_base": cfg["brand_fit_base"],
            "target_margin": cfg["target_margin"],
            "max_weight_kg": cfg["max_weight_kg"],
            "sku_target_min": cfg["sku_target_min"],
            "sku_target_max": cfg["sku_target_max"],
            "seasonal_weight": cfg["seasonal_weight"],
            "compliance_requirements": cfg["compliance_requirements"],
            "banned_subcategories": cfg["banned_subcategories"],
            "hero_candidates": cfg["hero_candidates"],
            "content_angles": cfg["content_angles"],
            "keywords_1688": cfg["keywords_1688"],
        }
        reason = f"初始品类配置: {cfg['name']} ({cfg['priority']})"
        op.execute(
            sa.text(
                """
                INSERT INTO strategy_versions (
                    strategy_type, version, old_config, new_config,
                    reason, changed_by, change_type, workspace_id,
                    created_at, updated_at
                ) VALUES (
                    :strategy_type, 1, '{}'::jsonb, CAST(:new_config AS jsonb),
                    :reason, :changed_by, 'update', CAST(:workspace_id AS uuid),
                    now(), now()
                )
                """
            ).bindparams(
                strategy_type=cfg["strategy_type"],
                new_config=json.dumps(new_config, ensure_ascii=False),
                reason=reason,
                changed_by=CHANGED_BY,
                workspace_id=WORKSPACE_ID,
            )
        )

    # 插入排除品类配置（用于 V5 品牌聚焦否决）
    excluded_config = {
        "excluded_categories": EXCLUDED_CATEGORIES,
        "veto_rule": "V5",
        "description": "与 Nuotao 户外品牌定位不符的品类，一票否决",
    }
    op.execute(
        sa.text(
            """
            INSERT INTO strategy_versions (
                strategy_type, version, old_config, new_config,
                reason, changed_by, change_type, workspace_id,
                created_at, updated_at
            ) VALUES (
                :strategy_type, 1, '{}'::jsonb, CAST(:new_config AS jsonb),
                :reason, :changed_by, 'update', CAST(:workspace_id AS uuid),
                now(), now()
            )
            """
        ).bindparams(
            strategy_type="category_excluded",
            new_config=json.dumps(excluded_config, ensure_ascii=False),
            reason="初始排除品类配置（V5 品牌聚焦否决）",
            changed_by=CHANGED_BY,
            workspace_id=WORKSPACE_ID,
        )
    )


def downgrade() -> None:
    """删除本迁移插入的品类配置。"""
    # 删除所有 category_* 类型的策略版本
    op.execute(
        sa.text(
            """
            DELETE FROM strategy_versions
            WHERE strategy_type LIKE 'category_%'
              AND changed_by = :changed_by
            """
        ).bindparams(changed_by=CHANGED_BY)
    )
