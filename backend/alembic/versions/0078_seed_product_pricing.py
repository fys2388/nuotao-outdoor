"""0078_seed_product_pricing

补齐第一批种子产品（0076）的定价数据，让候选状态机的定价闸门能通过。

Why
---
0076 把零售价/采购价写进了 ``products.attributes``（区间字符串，如
``"24.99-29.99"``），但两处真实校验读的是别的位置：

* ``listing_gate.resolve_prices`` 从 ``Product.meta`` 找
  ``regular_price / price / retail_price / sale_price``，区间字符串取不到，
  ``_pricing_missing`` 判定「零售价」缺失。
* ``product_intelligence._pricing_missing`` 从 ``product_cost`` 表找
  ``purchase_cost > 0``，而 0076 只插了 ``products`` 表、没有 cost 行，
  判定「采购成本」缺失。

结果：种子商品永远无法 ``candidate -> approved``（HTTP 400），
选品 → 上架的闭环在第一步就断掉。

Fix
---
* ``meta.regular_price`` 取零售价区间上界（目标零售价）。
* ``product_cost.purchase_cost`` 取采购价区间上界（最坏成本），
  ``currency='CNY'``。不填 ``total_landed_cost``，让上架闸门按配置的物流
  默认值补齐并把 basis 标成 ``estimated``，而不是凭空捏造落地成本。

常量直接内联为 SQL 字面量（不是绑定参数）：这些片段引用的是被操作表自身的
列，无法作为参数绑定；同时同一条语句里重复的参数名 asyncpg 会直接报错。

幂等：只在缺失时写入，可重复执行。全部为纯 DML，离线
``alembic upgrade head --sql`` 也能渲染（本仓库 staging 校验即走该路径）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
BATCH = "first_batch_1"
SOURCE_TAG = "migration_0078_seed_product_pricing"


def _range_upper(field: str, prefix: str = "") -> str:
    """SQL 片段：取 ``attributes->>field`` 区间上界。

    ``"24.99-29.99"`` -> 29.99；``"19.99"`` -> 19.99；空值 -> NULL。
    """
    norm = (
        "REGEXP_REPLACE("
        "COALESCE({prefix}attributes->>'{field}',''), '[^0-9.\\-]+', '', 'g')"
    ).format(prefix=prefix, field=field)
    # NULLIF 兜底：空值经 STRING_TO_ARRAY 可能得到含空串的数组，''::numeric 会报错。
    return (
        "NULLIF("
        "COALESCE("
        "(STRING_TO_ARRAY({norm}, '-'))[2], "
        "(STRING_TO_ARRAY({norm}, '-'))[1]"
        "), '')::numeric"
    ).format(norm=norm)


_RETAIL_UPPER = _range_upper("target_retail_price_usd")
_PURCHASE_UPPER = _range_upper("target_purchase_price_cny", "p.")

_BATCH_LIT = "'{}'".format(BATCH)
_SOURCE_LIT = "'{}'".format(SOURCE_TAG)
_WID_LIT = "'{}'::uuid".format(WORKSPACE_ID)


def upgrade() -> None:
    """把种子产品的目标定价落到闸门真正读取的位置。"""

    # 1. 零售价 -> meta.regular_price
    op.execute(
        sa.text(
            """
            UPDATE products
            SET meta = jsonb_set(
                    COALESCE(meta, '{{}}'::jsonb),
                    '{{regular_price}}',
                    to_jsonb({retail_upper})
                ),
                updated_at = now()
            WHERE attributes->>'batch' = {batch}
              AND (COALESCE(meta, '{{}}'::jsonb)->>'regular_price') IS NULL
              AND {retail_upper} > 0
            """.format(retail_upper=_RETAIL_UPPER, batch=_BATCH_LIT)
        )
    )

    # 2. 采购成本 -> product_cost（CNY，notes 打标以便幂等与回滚）
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
                    'batch', {batch},
                    'note', 'purchase_cost 取目标采购价区间上界；total_landed_cost 留空由闸门按物流默认值补齐'
                )
            FROM products p
            WHERE p.workspace_id = {wid}
              AND p.attributes->>'batch' = {batch}
              AND {purchase_upper} > 0
              AND NOT EXISTS (
                  SELECT 1 FROM product_cost c
                  WHERE c.product_id = p.id
                    AND c.workspace_id = {wid}
                    AND (c.notes->>'source') = {source}
              )
            """.format(
                wid=_WID_LIT,
                source=_SOURCE_LIT,
                batch=_BATCH_LIT,
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
            SET meta = COALESCE(meta, '{{}}'::jsonb) - 'regular_price',
                updated_at = now()
            WHERE attributes->>'batch' = {batch}
              AND meta IS NOT NULL
              AND (meta->>'regular_price') IS NOT NULL
            """.format(batch=_BATCH_LIT)
        )
    )
