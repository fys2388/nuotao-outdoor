"""0075_category_operational_weights

插入品类级 11 维运营评分权重到 strategy_versions 表。

不同品类的权重分布不同：
- 露营照明：margin_rate + market_heat 权重高（高毛利 + 上升趋势）
- 露营炊具：compliance_risk + product_quality 权重高（食品安全）
- 户外收纳：product_quality + differentiation 权重高（低竞争）
- 水具/Hydration：compliance_risk + differentiation 权重高（FDA + 品牌溢价）
- 徒步配件：market_heat + margin_rate 权重高（高毛利 + 内容潜力）

Revision ID: 0075
Revises: 0074
Create Date: 2026-10-06
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
CHANGED_BY = "migration_0075_category_weights"

# --------------------------------------------------------------------------- #
# 品类级 11 维权重配置
# --------------------------------------------------------------------------- #

# 基准权重（V2.0 勘误后，合计 100%）
BASE_WEIGHTS = {
    "supplier_quality": 0.15,
    "sales_validation": 0.10,
    "margin_rate": 0.15,
    "product_quality": 0.10,
    "logistics_support": 0.05,
    "differentiation": 0.05,
    "market_heat": 0.15,
    "amazon_competition": 0.10,
    "seasonality": 0.05,
    "ai_image_difficulty": 0.05,
    "compliance_risk": 0.05,
}

# 每个品类的权重调整（相对于基准的增减）
CATEGORY_WEIGHT_ADJUSTMENTS: dict[str, dict[str, float]] = {
    # 露营照明：高毛利 + 上升趋势
    "camping_lighting": {
        "margin_rate": +0.05,       # 0.15 → 0.20（高毛利品类）
        "market_heat": +0.05,       # 0.15 → 0.20（上升趋势）
        "supplier_quality": -0.03,  # 0.15 → 0.12
        "sales_validation": -0.02,  # 0.10 → 0.08
        "ai_image_difficulty": -0.05,  # 0.05 → 0.00（照明产品 AI 生图简单）
    },
    # 露营炊具：食品安全 + 产品质量
    "camping_cooking": {
        "compliance_risk": +0.05,   # 0.05 → 0.10（FDA 食品接触）
        "product_quality": +0.05,   # 0.10 → 0.15（材质安全）
        "margin_rate": -0.03,       # 0.15 → 0.12
        "market_heat": -0.02,       # 0.15 → 0.13
        "logistics_support": -0.05, # 0.05 → 0.00（炊具较重，物流影响大但已考虑）
    },
    # 户外收纳：低竞争 + 差异化
    "outdoor_storage": {
        "differentiation": +0.05,   # 0.05 → 0.10（低竞争品类）
        "product_quality": +0.05,   # 0.10 → 0.15（防水/耐用性关键）
        "margin_rate": +0.05,       # 0.15 → 0.20（保持高毛利）
        "amazon_competition": -0.05,  # 0.10 → 0.05（竞争度影响小）
        "supplier_quality": -0.05,  # 0.15 → 0.10
        "ai_image_difficulty": -0.05,  # 0.05 → 0.00
    },
    # 水具/Hydration：合规 + 差异化
    "hydration": {
        "compliance_risk": +0.05,   # 0.05 → 0.10（FDA）
        "differentiation": +0.05,   # 0.05 → 0.10（品牌溢价）
        "margin_rate": -0.05,       # 0.15 → 0.10
        "market_heat": -0.03,       # 0.15 → 0.12
        "amazon_competition": -0.02,  # 0.10 → 0.08
    },
    # 徒步配件：高毛利 + 市场热度
    "hiking_accessories": {
        "margin_rate": +0.05,       # 0.15 → 0.20（高毛利小件）
        "market_heat": +0.05,       # 0.15 → 0.20（上升趋势）
        "supplier_quality": -0.03,  # 0.15 → 0.12
        "product_quality": -0.02,   # 0.10 → 0.08
        "ai_image_difficulty": -0.05,  # 0.05 → 0.00
    },
}


def upgrade() -> None:
    """插入品类级权重配置到 strategy_versions 表。"""
    for category, adjustments in CATEGORY_WEIGHT_ADJUSTMENTS.items():
        # 计算品类级权重
        weights = {}
        for dim, base_val in BASE_WEIGHTS.items():
            weights[dim] = base_val + adjustments.get(dim, 0)

        # 验证权重合计为 1.0
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Category {category} weights sum to {total}, expected 1.0"
            )

        new_config = {
            "category": category,
            "category_name": {
                "camping_lighting": "露营照明",
                "camping_cooking": "露营炊具",
                "outdoor_storage": "户外收纳",
                "hydration": "水具/Hydration",
                "hiking_accessories": "徒步配件",
            }.get(category, category),
            "operational_weights": weights,
            "weight_adjustments": adjustments,
            "base_weights_version": "v2.0_operational",
            "description": f"{category} 品类级 11 维运营评分权重（基于 V2.0 基准调整）",
        }

        reason = (
            f"初始品类级权重配置: {new_config['category_name']} "
            f"(调整 {len(adjustments)} 个维度权重)"
        )

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
                strategy_type=f"cat_wts_{category}",
                new_config=json.dumps(new_config, ensure_ascii=False),
                reason=reason,
                changed_by=CHANGED_BY,
                workspace_id=WORKSPACE_ID,
            )
        )


def downgrade() -> None:
    """删除本迁移插入的品类级权重配置。"""
    op.execute(
        sa.text(
            """
            DELETE FROM strategy_versions
            WHERE strategy_type LIKE 'category_weights_%'
              AND changed_by = :changed_by
            """
        ).bindparams(changed_by=CHANGED_BY)
    )
