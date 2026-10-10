"""本地商品 ↔ WooCommerce 商品的关联管理。

## 背景

系统里此前并存两套映射机制，口径完全不一致：

- ``products.meta["woocommerce_id"]`` —— 推送路径**实际使用**的唯一判据；
- ``product_mappings`` 表 —— 它有 ``uq_nuotao_product_id`` / ``uq_woocommerce_id``
  唯一约束，但除 ``product_workbench`` 的只读查询外**从未被写入**，推送路径既不读
  也不写。

后果：旧推送通道只认 ``meta``、没有 SKU 反查。一旦 meta 丢失（例如创建请求在
Cloudflare 断连中丢掉响应，WooCommerce 其实已经建好了商品），下一次推送就会再
POST 一次。同 SKU 时 WooCommerce 会用 ``product_invalid_sku`` 拒绝，但**SKU 一旦
不同就会真的建出第二个商品**。

本模块把「认领已有商品」与「记录关联」收敛到一处，供推送、下架、彻底删除共用。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.product_mapping import ProductMapping
from app.services.wc_unpublish_service import WcCallBudget, find_wc_id_by_sku

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.product import Product

logger = logging.getLogger(__name__)


def resolve_wc_product_id(
    product: Product,
    *,
    auth: Any,
    headers: dict[str, str],
    budget: WcCallBudget | None = None,
) -> tuple[int | None, bool]:
    """解析商品在 WooCommerce 中的 ID。

    Returns:
        ``(wc_id, adopted)``。``adopted=True`` 表示 ``meta`` 里没有记录、这个 ID 是
        按 SKU 从 WooCommerce 反查回来的——调用方应把它写回本地，避免下次再查。
    """
    meta = product.meta if isinstance(product.meta, dict) else {}
    raw = meta.get("woocommerce_id")
    if raw not in (None, ""):
        try:
            return int(raw), False
        except (TypeError, ValueError):
            logger.warning("忽略无效的 woocommerce_id=%r，回退到 SKU 反查", raw)

    found = find_wc_id_by_sku(
        str(getattr(product, "sku", "") or ""),
        auth=auth,
        headers=headers,
        budget=budget,
    )
    if found:
        logger.info(
            "按 SKU 认领已有 WooCommerce 商品 id=%s sku=%s（meta 里没有记录）",
            found, product.sku,
        )
        return found, True
    return None, False


async def remember_wc_product(
    session: AsyncSession,
    *,
    product: Product,
    wc_id: int,
    slug: str | None = None,
) -> None:
    """把 WooCommerce 商品 ID 同时记到 ``meta`` 与 ``product_mappings``（幂等）。

    只调用 ``session.add`` / 改属性，不 commit——事务边界由调用方决定。

    ``product_mappings`` 的写入包在 savepoint 里：该表的 ``woocommerce_id`` 是唯一
    的，并发或历史脏数据可能让 upsert 撞约束，此时只回滚这次写入并记日志，**不能**
    让整个推送事务进入 aborted 状态。
    """
    from sqlalchemy.orm.attributes import flag_modified

    meta = product.meta if isinstance(product.meta, dict) else {}
    if meta.get("woocommerce_id") != wc_id:
        meta["woocommerce_id"] = wc_id
        if slug:
            meta["woocommerce_slug"] = slug
        product.meta = meta
        # meta 是普通 JSON 列（没有 MutableDict），直接赋值不会标脏，flush 时不发
        # UPDATE，id 会被静默丢掉。必须显式 flag_modified。
        flag_modified(product, "meta")

    try:
        async with session.begin_nested():
            existing = (
                await session.execute(
                    select(ProductMapping).where(
                        ProductMapping.nuotao_product_id == product.id
                    )
                )
            ).scalars().first()

            if existing is None:
                session.add(
                    ProductMapping(
                        workspace_id=product.workspace_id,
                        nuotao_product_id=product.id,
                        woocommerce_id=wc_id,
                        woocommerce_slug=slug,
                        sync_status="synced",
                    )
                )
            else:
                existing.woocommerce_id = wc_id
                if slug:
                    existing.woocommerce_slug = slug
                existing.sync_status = "synced"
            await session.flush()
    except IntegrityError:
        # 该 WC 商品已经挂在另一条本地记录上：保留 meta 回写（那是推送路径的判据），
        # 映射表冲突只记录，不阻断推送。
        logger.warning(
            "product_mappings 写入冲突，已跳过 mapping 行 product=%s wc_id=%s",
            product.id, wc_id,
        )
