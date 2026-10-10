"""产品生命周期编排：下架（回收站）· 恢复 · 彻底删除。

完整设计见 ``docs/wc_unpublish_design.md``。

三层结构：

- **下架**：WooCommerce 商品进回收站（``status = trash``），本地标 ``deleted_at``。可恢复。
- **恢复**：还原 WC 可见性，本地清 ``deleted_at``。
- **彻底删除**：本地**硬删除**商品行 + WooCommerce ``DELETE ?force=true``（不可逆）。

**执行顺序是设计的一部分：**

- 下架/恢复**先动 WC、再动本地**，失败则中止，保证「系统里的状态不会领先于店铺」。
- 彻底删除**先删本地、再删 WC**：本地被 ``RESTRICT`` 外键挡住是确定性失败，先做可以
  避免在本地删不掉的情况下已经把 WC 商品删了（那样会留下无从追溯的悬空记录）。

分层：本模块只做编排。外部 API 调用在 ``wc_unpublish_service``（集成层），审计在
``event_service``，DB 会话来自请求层。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.product import Product
from app.services import event_service
from app.services.wc_unpublish_service import (
    WcCallBudget,
    delete_wc_product_permanently,
    restore_product_to_wc,
    unpublish_product_from_wc,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 每个需要联动 WooCommerce 的商品会占用数十秒调用预算，批量串行执行（店铺前面是
# Cloudflare，并行不可靠）。与批量推送的 _BATCH_PUSH_MAX 保持一致，避免一次请求把
# 客户端挂死。
WC_BATCH_MAX = 25


class BatchTooLargeError(Exception):
    """单次操作需要联动 WooCommerce 的商品数超过上限。"""

    def __init__(self, count: int, limit: int = WC_BATCH_MAX) -> None:
        self.count = count
        self.limit = limit
        super().__init__(
            f"本次需要联动 {count} 个 WooCommerce 商品，超过单次上限 {limit} 个；"
            f"请分批操作（每个商品最多占用数十秒的 WooCommerce 调用预算）"
        )


def _has_wc_link(product: Product) -> bool:
    meta = product.meta if isinstance(product.meta, dict) else {}
    return bool(meta.get("woocommerce_id"))


def _assert_batch_size(products: Sequence[Product]) -> None:
    linked = [product for product in products if _has_wc_link(product)]
    if len(linked) > WC_BATCH_MAX:
        raise BatchTooLargeError(len(linked))


def _item(
    product: Product, result: dict[str, Any], *, success: bool | None = None
) -> dict[str, Any]:
    return {
        "product_id": str(product.id),
        "sku": product.sku,
        "success": bool(result.get("success")) if success is None else success,
        "action": str(result.get("action") or "failed"),
        "woocommerce_id": result.get("woocommerce_id"),
        "woocommerce_status": result.get("woocommerce_status"),
        "verified": bool(result.get("verified")),
        "error": result.get("error"),
        "message": result.get("message"),
    }


async def _load_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: Sequence[UUID],
    in_recycle_bin: bool | None = None,
) -> list[Product]:
    """按 workspace 取商品行。

    ``in_recycle_bin``：``True`` 只取回收站中的，``False`` 只取正常在用的，
    ``None`` 不限制。
    """
    ids = list(dict.fromkeys(product_ids))
    if not ids:
        return []
    query = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.id.in_(ids),
    )
    if in_recycle_bin is True:
        query = query.where(Product.deleted_at.is_not(None))
    elif in_recycle_bin is False:
        query = query.where(Product.deleted_at.is_(None))
    rows = (await session.execute(query)).scalars().all()
    return list(rows)


# ──────────────────────────────────────────────────────────────────────────── #
# 下架（→ 回收站）
# ──────────────────────────────────────────────────────────────────────────── #


async def _unpublish_one(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product: Product,
    trace_id: str | None,
    force_local: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """下架单个商品：先让 WC 进回收站，成功后再标记本地回收站。

    ``force_local`` 表示运营已明确接受「店铺未下架」，此时本地仍要移入回收站——
    否则返回值说「已移入回收站」而 ``deleted_at`` 仍为空，就是自相矛盾的谎报。
    """
    result = await asyncio.to_thread(
        unpublish_product_from_wc, product, budget=WcCallBudget()
    )
    success = bool(result.get("success"))
    move_to_bin = success or force_local

    if move_to_bin and product.deleted_at is None:
        product.deleted_at = datetime.now(UTC)

    if success:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.unpublished",
            entity_type="product",
            entity_id=str(product.id),
            payload={
                "sku": product.sku,
                "action": result.get("action"),
                "woocommerce_id": result.get("woocommerce_id"),
                "woocommerce_status": result.get("woocommerce_status"),
                "verified": bool(result.get("verified")),
            },
            trace_id=trace_id,
        )
    else:
        logger.warning(
            "WooCommerce 下架失败 sku=%s action=%s error=%s force_local=%s",
            product.sku, result.get("action"), result.get("error"), force_local,
        )
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.wc_unpublish_failed",
            entity_type="product",
            entity_id=str(product.id),
            payload={
                "sku": product.sku,
                "action": result.get("action"),
                "error": result.get("error"),
                "http_status": result.get("http_status"),
                # 记录本地是否仍被移入回收站：审计读者需要能分辨
                # 「店铺未下架 + 本地也没动」与「店铺未下架 + 本地已进回收站」。
                "local_deleted": move_to_bin,
            },
            trace_id=trace_id,
        )

    return result, _item(product, result)


async def unpublish_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: Sequence[UUID],
    force_local: bool = False,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """把商品下架到回收站（WC 进回收站 + 本地 ``deleted_at``）。

    ``force_local=True`` 时，即使 WC 下架失败也仍然把本地移入回收站（并在
    ``wc_unpublish_failed`` 中如实列出未下架的商品）。
    """
    requested_ids = list(dict.fromkeys(product_ids))
    products = await _load_products(
        session, workspace_id=workspace_id, product_ids=requested_ids,
        in_recycle_bin=False,
    )
    found = {product.id for product in products}
    not_found = [pid for pid in requested_ids if pid not in found]
    _assert_batch_size(products)

    wc_unpublished = 0
    failed_items: list[dict[str, Any]] = []
    for product in products:
        result, item = await _unpublish_one(
            session, workspace_id=workspace_id, product=product, trace_id=trace_id,
            force_local=force_local,
        )
        if not result.get("success"):
            failed_items.append(item)
        elif result.get("action") == "unpublished":
            wc_unpublished += 1

    if failed_items and not force_local:
        # 中止是刻意的：本地记录留着，运营才能看到问题并重试。先删本地的话，
        # 店铺里那个仍在售的商品就再没有线索指向它了。
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.unpublish_blocked_by_wc_failure",
            entity_type="product_batch",
            entity_id=str(trace_id or "batch"),
            payload={
                "requested": len(requested_ids),
                "failed": len(failed_items),
                "skus": [item.get("sku") for item in failed_items],
            },
            trace_id=trace_id,
        )
        await session.flush()
        logger.warning(
            "下架已中止：%d 个商品的 WooCommerce 下架失败（requested=%d）",
            len(failed_items), len(requested_ids),
        )
        return {
            "deleted": 0,
            "not_found": not_found,
            "wc_unpublished": wc_unpublished,
            "wc_unpublish_failed": failed_items,
            "blocked": True,
            "message": (
                f"WooCommerce 下架失败（{len(failed_items)} 个），已中止以避免"
                f"「系统已移入回收站、店铺仍在售」。请重试。"
            ),
        }

    await session.flush()
    logger.info(
        "下架完成: %d 个商品移入回收站（本次 WC 状态变更 %d 个，失败 %d 个）",
        len(products), wc_unpublished, len(failed_items),
    )
    return {
        "deleted": len(products),
        "not_found": not_found,
        "wc_unpublished": wc_unpublished,
        "wc_unpublish_failed": failed_items,
        "blocked": False,
        "message": (
            f"已移入回收站 {len(products)} 个商品，可在回收站恢复"
            + (f"；其中 {len(failed_items)} 个未成功下架 WooCommerce" if failed_items else "")
        ),
    }


# ──────────────────────────────────────────────────────────────────────────── #
# 恢复
# ──────────────────────────────────────────────────────────────────────────── #


async def _restore_one(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product: Product,
    trace_id: str | None,
    force_local: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """恢复单个商品：先还原 WC 可见性，成功后再清除本地回收站标记。

    ``force_local`` 表示运营接受「店铺状态未还原」，此时本地仍要移出回收站，
    否则返回值说「已恢复」而 ``deleted_at`` 仍在，同样是自相矛盾的谎报。
    """
    result = await asyncio.to_thread(
        restore_product_to_wc, product, budget=WcCallBudget()
    )
    success = bool(result.get("success"))
    move_out = success or force_local

    if move_out and product.deleted_at is not None:
        product.deleted_at = None

    if success:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.restored",
            entity_type="product",
            entity_id=str(product.id),
            payload={
                "sku": product.sku,
                "action": result.get("action"),
                "woocommerce_id": result.get("woocommerce_id"),
                "woocommerce_status": result.get("woocommerce_status"),
                "verified": bool(result.get("verified")),
            },
            trace_id=trace_id,
        )
    else:
        logger.warning(
            "WooCommerce 恢复失败 sku=%s action=%s error=%s force_local=%s",
            product.sku, result.get("action"), result.get("error"), force_local,
        )
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.restore_wc_failed",
            entity_type="product",
            entity_id=str(product.id),
            payload={
                "sku": product.sku,
                "action": result.get("action"),
                "error": result.get("error"),
                "local_restored": move_out,
            },
            trace_id=trace_id,
        )

    return result, _item(product, result)


async def restore_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: Sequence[UUID],
    force_local: bool = False,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """把商品从回收站恢复。

    WooCommerce 商品若已被 WordPress 自动清空回收站（默认约 30 天），恢复会失败；
    本函数**不会**自动重建 WC 商品，避免意外复活一个已下线的链接。
    """
    requested_ids = list(dict.fromkeys(product_ids))
    products = await _load_products(
        session, workspace_id=workspace_id, product_ids=requested_ids,
        in_recycle_bin=True,
    )
    found = {product.id for product in products}
    not_found = [pid for pid in requested_ids if pid not in found]
    _assert_batch_size(products)

    wc_restored = 0
    failed_items: list[dict[str, Any]] = []
    for product in products:
        result, item = await _restore_one(
            session, workspace_id=workspace_id, product=product, trace_id=trace_id,
            force_local=force_local,
        )
        if not result.get("success"):
            failed_items.append(item)
        elif result.get("action") == "restored":
            wc_restored += 1

    if failed_items and not force_local:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.restore_blocked_by_wc_failure",
            entity_type="product_batch",
            entity_id=str(trace_id or "batch"),
            payload={
                "requested": len(requested_ids),
                "failed": len(failed_items),
                "skus": [item.get("sku") for item in failed_items],
            },
            trace_id=trace_id,
        )
        await session.flush()
        return {
            "restored": 0,
            "not_found": not_found,
            "wc_restored": wc_restored,
            "wc_restore_failed": failed_items,
            "blocked": True,
            "message": (
                f"WooCommerce 恢复失败（{len(failed_items)} 个），已中止以避免"
                f"「系统已恢复上架、店铺仍不可见」。请重试。"
            ),
        }

    await session.flush()
    logger.info("恢复完成: %d 个商品移出回收站（WC 状态变更 %d 个）", len(products), wc_restored)
    return {
        "restored": len(products),
        "not_found": not_found,
        "wc_restored": wc_restored,
        "wc_restore_failed": failed_items,
        "blocked": False,
        "message": (
            f"已恢复 {len(products)} 个商品"
            + (f"；其中 {len(failed_items)} 个 WooCommerce 状态未还原" if failed_items else "")
        ),
    }


# ──────────────────────────────────────────────────────────────────────────── #
# 彻底删除
# ──────────────────────────────────────────────────────────────────────────── #


async def _hard_delete_product(
    session: AsyncSession, product: Product
) -> tuple[bool, str | None]:
    """硬删除商品行，返回 ``(是否成功, 失败原因)``。

    用 savepoint 隔离：被 ``RESTRICT`` 外键拒绝时只回滚这一次删除，session 仍可继续
    处理其余商品。

    商品被 B2B 询价单 / B2B 订单 / 履约记录引用时，数据库会拒绝删除。这是 ``AGENTS.md``
    §1.2「数据是资产」下的刻意保护，必须如实反馈，而不是绕过（例如偷偷改成软删）。
    """
    try:
        async with session.begin_nested():
            await session.delete(product)
            await session.flush()
        return True, None
    except IntegrityError as exc:
        raw = str(getattr(exc, "orig", exc))
        lowered = raw.lower()
        if "foreign key" in lowered or "violates" in lowered:
            reason = (
                "该商品已被业务单据引用（B2B 询价单 / B2B 订单 / 履约记录），"
                "数据库拒绝删除。有交易凭证的商品不可抹除，请改用下架（回收站）。"
            )
        else:
            reason = f"本地删除失败：{raw[:300]}"
        logger.warning("硬删除被拒绝 product=%s: %s", product.id, raw[:200])
        return False, reason


async def _purge_one(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product: Product,
    trace_id: str | None,
) -> tuple[str, dict[str, Any]]:
    """彻底删除单个商品：先本地硬删，成功后再永久删除 WC 商品。

    Returns:
        ``(outcome, item)``，outcome 取值 ``purged`` / ``blocked`` / ``wc_delete_failed``。
    """
    # 先把 WC 需要的数据快照出来：本地行删除后对象属性不应再依赖。
    snapshot = SimpleNamespace(
        id=product.id,
        sku=product.sku,
        meta=product.meta if isinstance(product.meta, dict) else {},
    )
    wc_linked = _has_wc_link(product)

    deleted, reason = await _hard_delete_product(session, product)
    if not deleted:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.purge_blocked",
            entity_type="product",
            entity_id=str(snapshot.id),
            payload={"sku": snapshot.sku, "reason": reason},
            trace_id=trace_id,
        )
        return "blocked", {
            "product_id": str(snapshot.id),
            "sku": snapshot.sku,
            "success": False,
            "action": "blocked",
            "error": reason,
        }

    # 本地已删。WC 商品必须一并永久删除，否则店铺里会留下无人认领的在售链接。
    wc_result = await asyncio.to_thread(
        delete_wc_product_permanently, snapshot, budget=WcCallBudget()
    )
    wc_success = bool(wc_result.get("success"))

    if wc_success:
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.purged",
            entity_type="product",
            entity_id=str(snapshot.id),
            payload={
                "sku": snapshot.sku,
                "action": wc_result.get("action"),
                "woocommerce_id": wc_result.get("woocommerce_id"),
                "woocommerce_linked": wc_linked,
            },
            trace_id=trace_id,
        )
        return "purged", {
            "product_id": str(snapshot.id),
            "sku": snapshot.sku,
            "success": True,
            "action": "deleted",
            "woocommerce_id": wc_result.get("woocommerce_id"),
            "verified": bool(wc_result.get("verified")),
            "message": wc_result.get("message"),
        }

    # 本地已删但 WC 没删掉：必须如实上报，并在审计里留下 wc_id 供人工清理。
    logger.error(
        "本地已删除但 WooCommerce 永久删除失败 sku=%s wc_id=%s error=%s",
        snapshot.sku, wc_result.get("woocommerce_id"), wc_result.get("error"),
    )
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.purge_wc_failed",
        entity_type="product",
        entity_id=str(snapshot.id),
        payload={
            "sku": snapshot.sku,
            "woocommerce_id": wc_result.get("woocommerce_id"),
            "error": wc_result.get("error"),
            "note": "本地记录已删除，WooCommerce 商品仍在，需人工清理",
        },
        trace_id=trace_id,
    )
    return "wc_delete_failed", {
        "product_id": str(snapshot.id),
        "sku": snapshot.sku,
        "success": False,
        "action": "failed",
        "woocommerce_id": wc_result.get("woocommerce_id"),
        "error": wc_result.get("error"),
        "message": "本地已删除，但 WooCommerce 商品未能永久删除，需人工清理",
    }


async def purge_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_ids: Sequence[UUID],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """彻底删除商品（不可逆）：本地硬删除 + WooCommerce 永久删除。

    被业务单据引用的商品会被数据库拒绝，返回 ``blocked`` 且 **WooCommerce 完全不动**。
    """
    requested_ids = list(dict.fromkeys(product_ids))
    products = await _load_products(
        session, workspace_id=workspace_id, product_ids=requested_ids,
        in_recycle_bin=None,
    )
    found = {product.id for product in products}
    not_found = [pid for pid in requested_ids if pid not in found]
    _assert_batch_size(products)

    purged = 0
    blocked = 0
    wc_delete_failed = 0
    items: list[dict[str, Any]] = []
    for product in products:
        outcome, item = await _purge_one(
            session, workspace_id=workspace_id, product=product, trace_id=trace_id
        )
        items.append(item)
        if outcome == "purged":
            purged += 1
        elif outcome == "blocked":
            blocked += 1
        else:
            wc_delete_failed += 1

    await session.flush()
    logger.info(
        "彻底删除完成: %d 已删除, %d 被业务单据阻止, %d 本地已删但 WC 未删",
        purged, blocked, wc_delete_failed,
    )

    if blocked and not purged:
        message = f"{blocked} 个商品被业务单据引用，无法彻底删除（已保持原状）"
    else:
        parts = [f"已彻底删除 {purged} 个"]
        if blocked:
            parts.append(f"{blocked} 个被业务单据引用未删除")
        if wc_delete_failed:
            parts.append(f"{wc_delete_failed} 个 WooCommerce 商品未删除，需人工清理")
        message = "，".join(parts)

    return {
        "purged": purged,
        "blocked": blocked,
        "wc_delete_failed": wc_delete_failed,
        "not_found": not_found,
        "items": items,
        "message": message,
    }


# ──────────────────────────────────────────────────────────────────────────── #
# 回收站列表
# ──────────────────────────────────────────────────────────────────────────── #


async def list_recycled_products(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Product], int]:
    """列出回收站中的商品（``deleted_at`` 非空），按删除时间倒序。"""
    base = select(Product).where(
        Product.workspace_id == workspace_id,
        Product.deleted_at.is_not(None),
    )
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(Product.deleted_at.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)
