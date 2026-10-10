"""0079_backfill_seed_pricing

把种子产品（0076）里缺失的定价数据补齐到闸门真正读取的位置。

Why
---
0078 用 ``attributes->>'batch' = 'first_batch_1'`` 做过滤，但 0076 实际按
**优先级**分批命名：priority 1 -> first_batch_1、priority 2 -> first_batch_2、
priority 3 -> first_batch_3。所以 0078 只覆盖了 priority 1 的 10 个商品，
priority 2/3 的 10 个商品仍然缺定价、仍然过不了闸门。

本迁移改成按「语义」判断而不是按「批次名」判断：只要 ``products.attributes``
里带了目标价键就补，与批次命名解耦。

闸门读的位置（两处都要满足，缺一即 HTTP 400）：

* ``listing_gate.resolve_prices`` 读 ``Product.meta.regular_price``。
* ``product_intelligence._pricing_missing`` 读 ``product_cost.purchase_cost > 0``。

Fix
---
* ``meta.regular_price``  = 零售价区间上界（目标零售价）。
* ``meta.pricing_source`` = 溯源标记，供 downgrade 精确回滚。
* ``product_cost.purchase_cost`` = 采购价区间上界（最坏成本），
  ``currency='CNY'``。不填 ``total_landed_cost``，让上架闸门按配置的物流
  默认值补齐并把 basis 标成 ``estimated``，而不是凭空捏造落地成本。

安全性
------
* 零售价：已有 ``meta.regular_price`` 的一律跳过（0078 已处理的、以及人工
  已录入的都不会被覆盖）。
* 采购成本：**仅当该产品一条 cost 行都没有**才插入。不用 source 标签去重，
  是为了避免在人工已录入成本的产品上追加一条新记录、再用 ``latest_cost_for_product``
  的排序把它顶掉。
* 全部为纯 DML，离线 ``alembic upgrade head --sql`` 可渲染（staging 校验路径）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
SOURCE_TAG = "migration_0079_backfill_seed_pricing"


def _range_upper(field: str, prefix: str = "") -> str:
    """SQL 片段：取 ``attributes->>field`` 区间上界。

    ``"24.99-29.99"`` -> 29.99；``"19.99"`` -> 19.99；空值 -> NULL。

    NULLIF 兜底：空串经 STRING_TO_ARRAY 可能得到含空元素的数组，
    ``''::numeric`` 会直接报错，必须先空值化再转型。
    """
    norm = (
        "REGEXP_REPLACE("
        "COALESCE({prefix}attributes->>'{field}',''), '[^0-9.\\-]+', '', 'g')"
    ).format(prefix=prefix, field=field)
    return (
        "NULLIF("
        "COALESCE("
        "(STRING_TO_ARRAY({norm}, '-'))[2], "
        "(STRING_TO_ARRAY({norm}, '-'))[1]"
        "), '')::numeric"
    ).format(norm=norm)


_RETAIL_UPPER = _range_upper("target_retail_price_usd")
_PURCHASE_UPPER = _range_upper("target_purchase_price_cny", "p.")

_WID_LIT = "'{}'::uuid".format(WORKSPACE_ID)
_SOURCE_LIT = "'{}'".format(SOURCE_TAG)
# jsonb 字符串字面量：'"xxx"'::jsonb。不能用 to_jsonb('xxx')——字面量是 unknown
# 类型，而 to_jsonb 是 any 多态函数，PostgreSQL 无法推断参数类型，直接报
# DatatypeMismatchError: could not determine polymorphic type because input
# has type unknown（staging 离线渲染不会执行，所以只在生产运行时才暴露）。
_SOURCE_JSONB = "'\"{}\"'::jsonb".format(SOURCE_TAG)


def upgrade() -> None:
    """把目标定价落到闸门真正读取的位置（与批次命名解耦）。"""

    # 1. 零售价 -> meta.regular_price（+ pricing_source 溯源标记）
    op.execute(
        sa.text(
            """
            UPDATE products
            SET meta = jsonb_set(
                    jsonb_set(
                        COALESCE(meta, '{{}}'::jsonb),
                        '{{regular_price}}',
                        to_jsonb({retail_upper})
                    ),
                    '{{pricing_source}}',
                    {source_jsonb}
                ),
                updated_at = now()
            WHERE workspace_id = {wid}
              AND attributes ? 'target_retail_price_usd'
              AND (COALESCE(meta, '{{}}'::jsonb)->>'regular_price') IS NULL
              AND {retail_upper} > 0
            """.format(
                retail_upper=_RETAIL_UPPER,
                wid=_WID_LIT,
                source_jsonb=_SOURCE_JSONB,
            )
        )
    )

    # 2. 采购成本 -> product_cost（CNY；仅在完全无成本记录时插入）
    op.execute(
        sa.text(
            """
            INSERT INTO product_cost (
                id, workspace_id, product_id, currency, purchase_cost, notes
            )
            SELECT
                gen_random_uuid(),
                {wid},
                p.id,
                'CNY',
                {purchase_upper},
                jsonb_build_object(
                    'source', {source},
                    'note', 'purchase_cost 取目标采购价区间上界；total_landed_cost 留空由闸门按物流默认值补齐',
                    'target_range_cny', p.attributes->>'target_purchase_price_cny'
                )
            FROM products p
            WHERE p.workspace_id = {wid}
              AND p.attributes ? 'target_purchase_price_cny'
              AND {purchase_upper} > 0
              AND NOT EXISTS (
                  SELECT 1 FROM product_cost c
                  WHERE c.product_id = p.id
                    AND c.workspace_id = {wid}
              )
            """.format(
                wid=_WID_LIT,
                source=_SOURCE_LIT,
                purchase_upper=_PURCHASE_UPPER,
            )
        )
    )


def downgrade() -> None:
    """删除本迁移写入的定价数据。"""
    op.execute(
        sa.text(
            """
            DELETE FROM product_cost
            WHERE workspace_id = {wid}
              AND (notes->>'source') = {source}
            """.format(wid=_WID_LIT, source=_SOURCE_LIT)
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE products
            SET meta = (
                    jsonb_set(COALESCE(meta, '{{}}'::jsonb), '{{pricing_source}}', 'null'::jsonb)
                    - 'regular_price'
                    - 'pricing_source'
                ),
                updated_at = now()
            WHERE workspace_id = {wid}
              AND meta IS NOT NULL
              AND (meta->>'pricing_source') = {source}
            """.format(wid=_WID_LIT, source=_SOURCE_LIT)
        )
    )
