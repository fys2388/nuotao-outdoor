"""1688 来源标识：提取规范化 offer id，并按来源键做幂等建档。

## 为什么需要这个模块

同一个 1688 链接被重复导入时，系统会把它建成多条候选，进而在 WooCommerce 里推成
多个商品。根因有两条：

1. ``products`` 上唯一的唯一性保障是 ``(workspace_id, sku)``，对**来源链接**没有任何
   约束，全库也不存在任何按 ``source_url`` / ``offer_id`` 查重的查询；
2. pipeline 生成的 SKU 由「LLM 生成标题 + 分钟级时间戳」构成，同一链接换个时间导入
   必然拿到不同 SKU，于是连 SKU 查重也一起失效。

因此这里把「来源」变成一等公民：从链接或 ID 中提取规范化的数字 offer id，写入
``products.source_offer_id``，并由数据库的部分唯一索引
``uq_products_workspace_source_offer`` 保证同一 workspace 内同一个 offer 只有一条活行。

**应用层查重只是友好提示，真正的防线是那个索引**：并发场景下「先 SELECT 再 INSERT」
必然存在竞态窗口（两个请求都查不到、都插入），数据库约束没有。

完整设计见 ``docs/1688_source_dedup_design.md``。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.product import Product

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 1688 的 offer id 是 9–13 位纯数字。下限放宽到 6 位以容纳测试与历史短 ID，
# 上限 32 与 Product.source_offer_id 的列长度一致。
_OFFER_ID_RE = re.compile(r"^\d{6,32}$")

# 与 product_pipeline_service.parse_1688_url 保持完全一致的模式集合，
# 这样「链接 → offer id」在整个系统里只有一个答案。
_URL_PATTERNS = (
    re.compile(r"/offer/(\d+)\.html"),
    re.compile(r"offerId=(\d+)"),
    re.compile(r"offer/(\d+)"),
)

# meta 里可能存放来源 ID 的键名（历史代码用过多个名字，牛顿选品用 ali1688_product_id）。
_META_ID_KEYS = (
    "source_id",
    "offer_id",
    "source_offer_id",
    "product_id_1688",
    "ali1688_product_id",
)


def normalize_offer_id(value: Any) -> str | None:
    """把候选值规范化为 offer id；不是合理的数字 ID 时返回 ``None``。

    拒绝空串、含空格、含查询参数或非数字的值——脏值一旦写进唯一索引列，会把
    「同一来源」拆成多个不同键，反而绕过约束。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if _OFFER_ID_RE.match(text) else None


def extract_1688_offer_id(url: str | None) -> str | None:
    """从 1688 链接（或纯 ID）中提取 offer id；无法识别时返回 ``None``。"""
    if not url:
        return None
    text = str(url).strip()
    direct = normalize_offer_id(text)
    if direct:
        return direct
    for pattern in _URL_PATTERNS:
        match = pattern.search(text)
        if match:
            found = normalize_offer_id(match.group(1))
            if found:
                return found
    return None


def resolve_source_offer_id(
    *,
    source_url: str | None = None,
    source_id: Any = None,
    meta: dict[str, Any] | None = None,
) -> str | None:
    """尽最大努力解析出 1688 offer id。

    优先级：显式 ``source_id`` → ``source_url`` → ``meta`` 里的历史键。
    任一步得到合法 ID 就返回，全部失败返回 ``None``（表示这不是 1688 来源，
    或来源信息不足以建立唯一键）。
    """
    direct = normalize_offer_id(source_id)
    if direct:
        return direct

    from_url = extract_1688_offer_id(source_url)
    if from_url:
        return from_url

    if isinstance(meta, dict):
        for key in _META_ID_KEYS:
            found = normalize_offer_id(meta.get(key))
            if found:
                return found
        return extract_1688_offer_id(meta.get("source_url"))
    return None


async def find_live_by_source(
    session: AsyncSession, *, workspace_id: UUID, source_offer_id: str
) -> Product | None:
    """按来源键查一条活行（``deleted_at IS NULL``）。"""
    return (
        (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.source_offer_id == source_offer_id,
                    Product.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )


async def _find_live_by_sku(
    session: AsyncSession, *, workspace_id: UUID, sku: str
) -> Product | None:
    return (
        (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.sku == sku,
                    Product.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )


async def get_or_create_by_source(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    source_offer_id: str | None,
    build: Callable[[], Product],
    fallback_sku: str | None = None,
) -> tuple[Product, bool]:
    """按来源键幂等建档，返回 ``(product, created)``。

    查找顺序：

    1. ``source_offer_id``（有值时才用）——来源身份的主判据；
    2. ``fallback_sku``——兼容历史数据：在 ``source_offer_id`` 列存在之前建立的候选
       没有来源键，只能靠 SKU 认领，否则同一个 offer 还会再建一条。

    命中历史行时会顺手把来源键补上，让它下次直接命中来源查重。

    并发安全：插入包在 savepoint 里，撞唯一索引时只回滚这次插入并回查已存在的行。
    没有 savepoint 的话，``IntegrityError`` 会让整个请求事务进入 aborted 状态，
    同一事务里后续所有语句都会失败。
    """
    if source_offer_id:
        existing = await find_live_by_source(
            session, workspace_id=workspace_id, source_offer_id=source_offer_id
        )
        if existing is not None:
            return existing, False

    if fallback_sku:
        existing = await _find_live_by_sku(
            session, workspace_id=workspace_id, sku=fallback_sku
        )
        if existing is not None:
            # 认领历史行：补上来源键，下次就直接命中来源查重。
            if source_offer_id and not existing.source_offer_id:
                existing.source_offer_id = source_offer_id
                logger.info(
                    "为历史候选补写来源键 sku=%s offer=%s", fallback_sku, source_offer_id
                )
            return existing, False

    product = build()
    if source_offer_id and not product.source_offer_id:
        product.source_offer_id = source_offer_id

    try:
        async with session.begin_nested():
            session.add(product)
            await session.flush()
        return product, True
    except IntegrityError:
        # 并发下另一个请求先建好了：回查取用，而不是把冲突抛给用户。
        logger.info(
            "来源键冲突，回查已存在候选 workspace=%s offer=%s sku=%s",
            workspace_id, source_offer_id, fallback_sku,
        )
        if source_offer_id:
            existing = await find_live_by_source(
                session, workspace_id=workspace_id, source_offer_id=source_offer_id
            )
            if existing is not None:
                return existing, False
        if fallback_sku:
            existing = await _find_live_by_sku(
                session, workspace_id=workspace_id, sku=fallback_sku
            )
            if existing is not None:
                return existing, False
        raise
