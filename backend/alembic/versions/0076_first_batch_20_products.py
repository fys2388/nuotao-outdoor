"""0076_first_batch_20_products

插入第一批20个产品到 products 表。

数据来源：docs/first_batch_20_products_plan.md
品类映射：docs/product_category_planning.md

Revision ID: 0076
Revises: 0075
Create Date: 2026-10-06
"""

from __future__ import annotations

import json
from uuid import UUID

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

# --------------------------------------------------------------------------- #
# 20个产品数据
# --------------------------------------------------------------------------- #

PRODUCTS: list[dict] = [
    {
        "sku": "NT-LT-001",
        "name": "LED感应头灯（强光远射）",
        "category": "camping_lighting",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "source_url": None,
        "target_market": "US",
        "weight_kg": 0.15,
        "attributes": {
            "subcategory": "headlamp",
            "target_purchase_price_cny": "15-25",
            "target_retail_price_usd": "19.99-24.99",
            "estimated_margin": "65-70%",
            "predicted_v2_score": "85-90",
            "core_features": ["强光远射", "感应开关", "长续航", "IPX6防水"],
            "selection_reason": "超轻小件，物流成本极低，户外刚需，复购率高",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["camping", "lighting", "headlamp", "essential"],
        "meta": {
            "keywords_1688": ["LED感应头灯", "强光远射", "充电", "户外"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-LT-002",
        "name": "便携LED露营灯（可充电）",
        "category": "camping_lighting",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.30,
        "attributes": {
            "subcategory": "camping_lamp",
            "target_purchase_price_cny": "20-35",
            "target_retail_price_usd": "24.99-29.99",
            "estimated_margin": "60-65%",
            "predicted_v2_score": "82-87",
            "core_features": ["三档调光", "超长续航", "可当充电宝", "挂钩设计"],
            "selection_reason": "轻小件，露营必备，多场景使用",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["camping", "lighting", "lamp", "essential"],
        "meta": {
            "keywords_1688": ["露营灯", "便携", "充电", "LED", "超长续航", "户外"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-HY-001",
        "name": "多功能折叠水壶（食品级硅胶）",
        "category": "hydration",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.15,
        "attributes": {
            "subcategory": "foldable_bottle",
            "target_purchase_price_cny": "10-20",
            "target_retail_price_usd": "14.99-19.99",
            "estimated_margin": "65-70%",
            "predicted_v2_score": "83-88",
            "core_features": ["食品级硅胶", "折叠便携", "防漏", "耐高温"],
            "selection_reason": "超轻小件，旅行/户外/健身多场景",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["hydration", "bottle", "foldable", "essential"],
        "meta": {
            "keywords_1688": ["折叠水壶", "硅胶", "食品级", "便携", "户外", "旅行"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-HY-002",
        "name": "不锈钢保温瓶（500ml/750ml）",
        "category": "hydration",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.40,
        "attributes": {
            "subcategory": "thermos",
            "target_purchase_price_cny": "25-40",
            "target_retail_price_usd": "29.99-34.99",
            "estimated_margin": "55-60%",
            "predicted_v2_score": "80-85",
            "core_features": ["24小时保温", "304不锈钢", "防漏", "大容量"],
            "selection_reason": "轻小件，日常+户外双场景，品牌溢价空间大",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["hydration", "thermos", "stainless_steel"],
        "meta": {
            "keywords_1688": ["保温瓶", "不锈钢", "真空", "户外", "便携", "大容量"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-HA-001",
        "name": "户外多功能工具卡（不锈钢）",
        "category": "hiking_accessories",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.05,
        "attributes": {
            "subcategory": "multi_tool",
            "target_purchase_price_cny": "5-12",
            "target_retail_price_usd": "9.99-12.99",
            "estimated_margin": "70-75%",
            "predicted_v2_score": "86-91",
            "core_features": ["18种功能", "不锈钢材质", "信用卡大小", "便携"],
            "selection_reason": "超轻超小，物流成本几乎为零，高利润率，适合做引流款",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["hiking", "accessories", "multi_tool", "essential"],
        "meta": {
            "keywords_1688": ["多功能工具卡", "不锈钢", "户外", "便携", "急救"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-HA-002",
        "name": "户外防水手机袋（TPU透明）",
        "category": "hiking_accessories",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.05,
        "attributes": {
            "subcategory": "phone_pouch",
            "target_purchase_price_cny": "5-10",
            "target_retail_price_usd": "9.99-14.99",
            "estimated_margin": "70-75%",
            "predicted_v2_score": "85-90",
            "core_features": ["IPX8防水", "可触屏", "透明拍照", "挂绳设计"],
            "selection_reason": "超轻小件，夏季水上活动刚需，高利润率",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["hiking", "accessories", "phone_pouch", "essential"],
        "meta": {
            "keywords_1688": ["防水手机袋", "透明", "TPU", "户外", "游泳", "潜水", "触屏"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-HA-003",
        "name": "便携户外急救包（迷你款）",
        "category": "hiking_accessories",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.30,
        "attributes": {
            "subcategory": "first_aid",
            "target_purchase_price_cny": "15-25",
            "target_retail_price_usd": "19.99-24.99",
            "estimated_margin": "55-60%",
            "predicted_v2_score": "82-87",
            "core_features": ["30+件急救用品", "便携收纳", "防水包", "多场景"],
            "selection_reason": "轻小件，户外/车载/旅行刚需，安全意识提升带来需求增长",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["hiking", "accessories", "first_aid", "essential"],
        "meta": {
            "keywords_1688": ["急救包", "便携", "户外", "迷你", "旅行", "车载", "应急"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-HA-004",
        "name": "铝合金登山杖（折叠款）",
        "category": "hiking_accessories",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.50,
        "attributes": {
            "subcategory": "trekking_pole",
            "target_purchase_price_cny": "25-40",
            "target_retail_price_usd": "29.99-39.99",
            "estimated_margin": "55-60%",
            "predicted_v2_score": "80-85",
            "core_features": ["航空铝合金", "折叠便携", "EVA手柄", "钨钢杖尖"],
            "selection_reason": "轻小件，徒步/登山刚需，可做单支/两支套装",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["hiking", "accessories", "trekking_pole"],
        "meta": {
            "keywords_1688": ["登山杖", "铝合金", "折叠", "便携", "户外", "徒步", "伸缩"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CC-001",
        "name": "户外便携炉具（一体式）",
        "category": "camping_cooking",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.30,
        "attributes": {
            "subcategory": "stove",
            "target_purchase_price_cny": "20-35",
            "target_retail_price_usd": "24.99-34.99",
            "estimated_margin": "55-60%",
            "predicted_v2_score": "81-86",
            "core_features": ["一体式折叠", "防风设计", "快速点火", "轻量便携"],
            "selection_reason": "轻小件，露营烹饪刚需，可搭配气罐/锅具组合销售",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["camping", "cooking", "stove", "essential"],
        "meta": {
            "keywords_1688": ["户外炉具", "便携", "一体式", "折叠", "防风", "野营", "气炉"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-OS-001",
        "name": "户外防水收纳袋（多尺寸套装）",
        "category": "outdoor_storage",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.20,
        "attributes": {
            "subcategory": "storage_bags",
            "target_purchase_price_cny": "10-20",
            "target_retail_price_usd": "14.99-19.99",
            "estimated_margin": "60-65%",
            "predicted_v2_score": "83-88",
            "core_features": ["IPX6防水", "多尺寸套装", "干湿分离", "耐磨材质"],
            "selection_reason": "轻小件，户外/旅行/水上活动刚需，套装销售提升客单价",
            "priority": 1,
            "batch": "first_batch_1",
        },
        "tags": ["outdoor", "storage", "waterproof", "essential"],
        "meta": {
            "keywords_1688": ["防水收纳袋", "户外", "漂流", "游泳", "干湿分离", "多尺寸"],
            "predicted_grade": "A",
        },
    },
    {
        "sku": "NT-HY-003",
        "name": "3L战术水袋背包",
        "category": "hydration",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 0.80,
        "attributes": {
            "subcategory": "hydration_pack",
            "target_purchase_price_cny": "25",
            "target_retail_price_usd": "29.99",
            "estimated_margin": "45-50%",
            "predicted_v2_score": "86.75",
            "core_features": ["3L容量", "战术设计", "背负系统"],
            "selection_reason": "已上架产品（WooCommerce ID 907）",
            "priority": 2,
            "batch": "first_batch_2",
        },
        "tags": ["hydration", "hydration_pack"],
        "meta": {
            "keywords_1688": ["战术水袋", "3L", "背包式"],
            "predicted_grade": "A",
            "woocommerce_id": 907,
            "already_listed": True,
        },
    },
    {
        "sku": "NT-CF-001",
        "name": "便携折叠露营月亮椅",
        "category": "camping_furniture",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 2.50,
        "attributes": {
            "subcategory": "chair",
            "target_purchase_price_cny": "40.88",
            "target_retail_price_usd": "39.99",
            "estimated_margin": "25-30%",
            "predicted_v2_score": "80.75",
            "core_features": ["月亮椅设计", "折叠便携", "舒适度高"],
            "selection_reason": "已上架产品（WooCommerce ID 917），重件利润率偏低",
            "priority": 2,
            "batch": "first_batch_2",
        },
        "tags": ["camping", "furniture", "chair"],
        "meta": {
            "keywords_1688": ["月亮椅", "折叠", "露营"],
            "predicted_grade": "B",
            "woocommerce_id": 917,
            "already_listed": True,
            "note": "重件产品，利润率偏低，后续可考虑提价或优化物流",
        },
    },
    {
        "sku": "NT-CF-002",
        "name": "户外便携折叠桌（铝合金）",
        "category": "camping_furniture",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 2.50,
        "attributes": {
            "subcategory": "table",
            "target_purchase_price_cny": "40-60",
            "target_retail_price_usd": "49.99-59.99",
            "estimated_margin": "25-35%",
            "predicted_v2_score": "78-83",
            "core_features": ["铝合金轻量化", "快速折叠", "承重强", "便携收纳"],
            "selection_reason": "露营家具刚需，可与月亮椅组合销售，重件需提价保证利润",
            "priority": 2,
            "batch": "first_batch_2",
        },
        "tags": ["camping", "furniture", "table"],
        "meta": {
            "keywords_1688": ["露营折叠桌", "便携", "铝合金", "户外", "轻量化", "折叠"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CC-002",
        "name": "户外便携锅具套装（3-4人）",
        "category": "camping_cooking",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 1.50,
        "attributes": {
            "subcategory": "cookware_set",
            "target_purchase_price_cny": "40-60",
            "target_retail_price_usd": "49.99-59.99",
            "estimated_margin": "35-45%",
            "predicted_v2_score": "79-84",
            "core_features": ["铝合金材质", "嵌套收纳", "3-4人容量", "含餐具"],
            "selection_reason": "露营烹饪刚需，套装销售提升客单价，可与炉具组合",
            "priority": 2,
            "batch": "first_batch_2",
        },
        "tags": ["camping", "cooking", "cookware_set"],
        "meta": {
            "keywords_1688": ["户外锅具套装", "便携", "野营", "炊具", "铝合金", "折叠"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CS-001",
        "name": "户外天幕（3×3米，涂银防晒）",
        "category": "camping_shelter",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 1.80,
        "attributes": {
            "subcategory": "tarp",
            "target_purchase_price_cny": "60-90",
            "target_retail_price_usd": "69.99-89.99",
            "estimated_margin": "35-45%",
            "predicted_v2_score": "80-85",
            "core_features": ["涂银防晒UPF50+", "防雨", "大空间", "多搭建方式"],
            "selection_reason": "露营热门产品，高客单价，品牌溢价空间大",
            "priority": 2,
            "batch": "first_batch_2",
        },
        "tags": ["camping", "shelter", "tarp"],
        "meta": {
            "keywords_1688": ["户外天幕", "涂银", "防晒", "防雨", "便携", "露营", "遮阳棚"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CS-002",
        "name": "户外自动帐篷（3-4人，速开）",
        "category": "camping_shelter",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 3.00,
        "attributes": {
            "subcategory": "tent",
            "target_purchase_price_cny": "80-120",
            "target_retail_price_usd": "99.99-129.99",
            "estimated_margin": "30-40%",
            "predicted_v2_score": "78-83",
            "core_features": ["3秒速开", "防雨防晒", "3-4人空间", "透气网纱"],
            "selection_reason": "露营核心产品，高客单价，品牌溢价空间大",
            "priority": 3,
            "batch": "first_batch_3",
        },
        "tags": ["camping", "shelter", "tent"],
        "meta": {
            "keywords_1688": ["自动帐篷", "速开", "户外", "3-4人", "防雨", "防晒", "便携"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-OS-002",
        "name": "户外露营背包（40L，防水）",
        "category": "outdoor_storage",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 1.20,
        "attributes": {
            "subcategory": "backpack",
            "target_purchase_price_cny": "40-60",
            "target_retail_price_usd": "49.99-69.99",
            "estimated_margin": "40-50%",
            "predicted_v2_score": "79-84",
            "core_features": ["40L大容量", "防水面料", "人体工学背负", "多隔层"],
            "selection_reason": "户外刚需，日常+户外双场景，品牌溢价空间大",
            "priority": 3,
            "batch": "first_batch_3",
        },
        "tags": ["outdoor", "storage", "backpack"],
        "meta": {
            "keywords_1688": ["户外背包", "40L", "防水", "登山", "露营", "徒步", "大容量"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CF-003",
        "name": "户外折叠躺椅（高背款）",
        "category": "camping_furniture",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 3.00,
        "attributes": {
            "subcategory": "recliner",
            "target_purchase_price_cny": "50-80",
            "target_retail_price_usd": "59.99-79.99",
            "estimated_margin": "25-35%",
            "predicted_v2_score": "76-81",
            "core_features": ["高背设计", "多档调节", "可躺可坐", "便携收纳"],
            "selection_reason": "露营/钓鱼/午休多场景，舒适度高，可做高端款",
            "priority": 3,
            "batch": "first_batch_3",
        },
        "tags": ["camping", "furniture", "recliner"],
        "meta": {
            "keywords_1688": ["折叠躺椅", "户外", "高背", "便携", "露营", "钓鱼", "午休"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CC-003",
        "name": "户外便携烧烤架（折叠款）",
        "category": "camping_cooking",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 2.50,
        "attributes": {
            "subcategory": "grill",
            "target_purchase_price_cny": "40-70",
            "target_retail_price_usd": "49.99-69.99",
            "estimated_margin": "30-40%",
            "predicted_v2_score": "77-82",
            "core_features": ["折叠便携", "不锈钢材质", "易清洁", "适合3-5人"],
            "selection_reason": "户外烧烤热门，庭院+露营双场景，季节性强（Q2-Q3旺季）",
            "priority": 3,
            "batch": "first_batch_3",
        },
        "tags": ["camping", "cooking", "grill"],
        "meta": {
            "keywords_1688": ["烧烤架", "便携", "折叠", "户外", "木炭", "家用", "露营"],
            "predicted_grade": "B",
        },
    },
    {
        "sku": "NT-CF-004",
        "name": "户外充气沙发（便携款）",
        "category": "camping_furniture",
        "status": "candidate",
        "candidate_status": "candidate",
        "funnel_stage": "recalled",
        "source": "1688",
        "target_market": "US",
        "weight_kg": 1.20,
        "attributes": {
            "subcategory": "air_sofa",
            "target_purchase_price_cny": "25-45",
            "target_retail_price_usd": "29.99-44.99",
            "estimated_margin": "40-50%",
            "predicted_v2_score": "78-83",
            "core_features": ["快速充气", "便携收纳", "防水面料", "多场景"],
            "selection_reason": "网红产品，社交媒体传播性强，轻量便携，年轻受众喜爱",
            "priority": 3,
            "batch": "first_batch_3",
        },
        "tags": ["camping", "furniture", "air_sofa"],
        "meta": {
            "keywords_1688": ["充气沙发", "户外", "便携", "空气沙发", "露营", "懒人", "快速充气"],
            "predicted_grade": "B",
        },
    },
]


def upgrade() -> None:
    """插入第一批20个产品到 products 表。"""
    for product in PRODUCTS:
        op.execute(
            sa.text(
                """
                INSERT INTO products (
                    id, workspace_id, sku, name, category, status,
                    candidate_status, funnel_stage, source,
                    target_market, weight_kg, attributes, tags, meta,
                    created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), CAST(:workspace_id AS uuid), :sku, :name, :category, :status,
                    :candidate_status, :funnel_stage, :source,
                    :target_market, :weight_kg, CAST(:attributes AS jsonb), CAST(:tags AS jsonb), CAST(:meta AS jsonb),
                    now(), now()
                )
                """
            ).bindparams(
                workspace_id=WORKSPACE_ID,
                sku=product["sku"],
                name=product["name"],
                category=product["category"],
                status=product["status"],
                candidate_status=product["candidate_status"],
                funnel_stage=product["funnel_stage"],
                source=product["source"],
                target_market=product["target_market"],
                weight_kg=product["weight_kg"],
                attributes=json.dumps(product["attributes"], ensure_ascii=False),
                tags=json.dumps(product["tags"], ensure_ascii=False),
                meta=json.dumps(product["meta"], ensure_ascii=False),
            )
        )


def downgrade() -> None:
    """删除第一批20个产品。"""
    sku_prefixes = ["NT-LT-", "NT-HY-", "NT-HA-", "NT-CC-", "NT-OS-", "NT-CF-", "NT-CS-"]
    for prefix in sku_prefixes:
        op.execute(
            sa.text(
                """
                DELETE FROM products
                WHERE sku LIKE :prefix
                  AND workspace_id = :workspace_id
                """
            ).bindparams(prefix=f"{prefix}%", workspace_id=WORKSPACE_ID)
        )
