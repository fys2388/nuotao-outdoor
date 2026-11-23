"""M4 V2.6 Product / Variation 身份模型实现测试(17 项,SQLite 兼容)。

覆盖:PRODUCT/VARIATION/UNKNOWN_LEGACY 三态;唯一性;SKU 重复/缺失;workspace 隔离;
多 Offer 映射;Offer 失效;ProductMapping 冲突;OrderItem 变体关联;Inventory 变体级更新;
Inventory 防父商品误更新;CostSnapshot 历史一致性;回填幂等;Migration 语法/元数据;
event_log+trace_id;历史兼容;71 行 CSV 分类校验。

**不执行生产迁移/回填**(M4 V2.6 指令 §8)。PostgreSQL 集成测试见
``test_identity_model_v26_pg.py``(Testcontainers,需 PG/Docker 可用)。
"""

from __future__ import annotations

import ast
import csv
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.product_intelligence import ProductCostSnapshot
from app.models.product_mapping import (
    IDENTITY_STATE_PRODUCT,
    IDENTITY_STATE_UNKNOWN_LEGACY,
    IDENTITY_STATE_VARIATION,
    ProductMapping,
)
from app.models.supplier_offer_mapping import (
    MAPPING_STATUS_ARCHIVED,
    MAPPING_STATUS_MAPPED,
    SupplierOfferMapping,
)
from app.models.supply_chain import InventorySnapshot
from app.services import identity_model_v26 as idm

WORKSPACE = DEFAULT_WORKSPACE_ID

CSV_PATH = Path(__file__).resolve().parents[2] / "docs" / "_audit" / "PRICING_V2_3_SKU_UNIQUENESS.csv"


# --- helpers ---------------------------------------------------------------


async def _make_product(
    session,
    *,
    sku: str = "SKU-1",
    name: str = "Test Product",
    workspace_id: UUID = WORKSPACE,
) -> Product:
    product = Product(sku=sku, name=name, workspace_id=workspace_id)
    session.add(product)
    await session.flush()
    return product


def _load_71_rows() -> list[dict]:
    """读取 71 行 CSV(隔离测试数据)."""
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# --- 1. identity_state 纯函数边界 -----------------------------------------


@pytest.mark.asyncio
async def test_identity_state_basics() -> None:
    """身份判定核心规则:vid 非空→VARIATION;vid 空+无变体→PRODUCT;否则 UNKNOWN."""
    assert idm.identity_state(2549, 2552, True) == IDENTITY_STATE_VARIATION
    assert idm.identity_state(2687, None, False) == IDENTITY_STATE_PRODUCT
    assert idm.identity_state(2549, None, True) == IDENTITY_STATE_UNKNOWN_LEGACY
    assert idm.identity_state(2549, None, None) == IDENTITY_STATE_UNKNOWN_LEGACY
    # vid 空 + 商品有变体 + 记录有变体上下文 ⇒ 按上下文归类为变体.
    assert idm.identity_state(2549, None, True, True) == IDENTITY_STATE_VARIATION
    # 纯函数严格按 `is not None`:0 非空 ⇒ VARIATION(CSV "0" 由 classify_rows 归一化为 None).
    assert idm.identity_state(2549, 0, True) == IDENTITY_STATE_VARIATION
    # classify_rows 把 "0" 视作空(无变体),商品有变体 ⇒ UNKNOWN_LEGACY.
    batch = idm.classify_rows([{"wc_product_id": 2549, "wc_variation_id": "0", "product_has_variations": True}])
    assert batch.rows[0].identity_state == IDENTITY_STATE_UNKNOWN_LEGACY


# --- 2. 71 行 CSV 分类校验 -------------------------------------------------


@pytest.mark.asyncio
async def test_classify_71_rows() -> None:
    """71 行 CSV → 70 VARIATION + 1 PRODUCT + 0 UNKNOWN(与 V2.5 审计一致)."""
    rows = _load_71_rows()
    assert len(rows) == 71
    batch = idm.classify_csv_rows(rows)
    summary = batch.summary()
    assert summary["VARIATION"] == 70
    assert summary["PRODUCT"] == 1
    assert summary["UNKNOWN_LEGACY"] == 0
    assert summary["total"] == 71
    # PRODUCT 行正是 2687 净水器.
    product_rows = [r for r in batch.rows if r.identity_state == IDENTITY_STATE_PRODUCT]
    assert len(product_rows) == 1
    assert product_rows[0].wc_product_id == 2687


# --- 3/4. PRODUCT / VARIATION 创建与读取 -----------------------------------


@pytest.mark.asyncio
async def test_product_mapping_create_and_read(db_session) -> None:
    """商品级映射创建/读取,identity_state=PRODUCT,vid 为空."""
    product = await _make_product(db_session, sku="FILTER-2687", name="Portable Water Filter")
    mapping = await idm.upsert_product_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2687,
        variation_sku="NT-972602197791",
        trace_id="t-product-1",
    )
    await db_session.commit()
    assert mapping.identity_state == IDENTITY_STATE_PRODUCT
    assert mapping.woocommerce_variation_id is None
    assert mapping.is_product_level is True

    row = (
        (await db_session.execute(select(ProductMapping).where(ProductMapping.woocommerce_id == 2687)))
        .scalars()
        .first()
    )
    assert row is not None
    assert row.identity_state == IDENTITY_STATE_PRODUCT


@pytest.mark.asyncio
async def test_variation_mapping_create_and_read(db_session) -> None:
    """变体级映射创建/读取,identity_state=VARIATION,variation_sku 保留."""
    product = await _make_product(db_session, sku="CRAMPON-2763", name="Ice Crampons")
    mapping = await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2763,
        woocommerce_variation_id=2772,
        variation_sku="NT-746435358585-10-B-M",
        trace_id="t-variation-1",
    )
    await db_session.commit()
    assert mapping.identity_state == IDENTITY_STATE_VARIATION
    assert mapping.woocommerce_variation_id == 2772
    assert mapping.variation_sku == "NT-746435358585-10-B-M"
    assert mapping.is_variation_level is True

    row = (
        (await db_session.execute(select(ProductMapping).where(ProductMapping.woocommerce_variation_id == 2772)))
        .scalars()
        .first()
    )
    assert row is not None
    assert row.identity_state == IDENTITY_STATE_VARIATION


# --- 5. UNKNOWN_LEGACY -----------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_legacy_not_auto_product(db_session) -> None:
    """vid 空 + 商品有变体 ⇒ UNKNOWN_LEGACY,不被自动归为 PRODUCT 或具体变体."""
    product = await _make_product(db_session, sku="BAG-2549", name="Waterproof Bag")
    # 直接构造:无 vid 且商品有变体(无记录上下文).
    mapping = ProductMapping(
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2549,
        woocommerce_variation_id=None,
        identity_state=IDENTITY_STATE_UNKNOWN_LEGACY,
        trace_id="t-unknown-1",
    )
    db_session.add(mapping)
    await db_session.commit()

    row = (
        (await db_session.execute(select(ProductMapping).where(ProductMapping.woocommerce_id == 2549)))
        .scalars()
        .first()
    )
    assert row.identity_state == IDENTITY_STATE_UNKNOWN_LEGACY
    # 不自动变 PRODUCT,不自动绑定具体变体.
    assert row.identity_state != IDENTITY_STATE_PRODUCT
    assert row.woocommerce_variation_id is None

    # 服务层 record_order_item 对历史(无 vid + 商品有变体)也判定 UNKNOWN.
    order = Order(workspace_id=WORKSPACE, external_order_id="ord-u1", status="received")
    db_session.add(order)
    await db_session.flush()
    item = await idm.record_order_item(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        product_id=product.id,
        name="Bag",
        quantity=1,
        unit_price=0,
        line_total=0,
        wc_product_id=2549,
        wc_variation_id=None,
        variation_sku=None,
        product_has_variations=True,
        trace_id="t-unknown-2",
    )
    await db_session.commit()
    assert item.identity_state == IDENTITY_STATE_UNKNOWN_LEGACY


# --- 6. Product/Variation 唯一性 -------------------------------------------


@pytest.mark.asyncio
async def test_product_variation_uniqueness(db_session) -> None:
    """商品级/变体级部分唯一索引:同键重复被拒,不同变体可共存."""
    product = await _make_product(db_session, sku="PAD-2698", name="Sleeping Pad")
    pid = product.id  # rollback 会过期实例属性,改用保存的 id.
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=pid,
        woocommerce_id=2698,
        woocommerce_variation_id=2700,
        variation_sku="NT-1054599709111-2",
        trace_id="t-u1",
    )
    await db_session.commit()

    # 同键(同 workspace+woo+vid)重复 ⇒ 部分唯一索引拒绝.
    dup = ProductMapping(
        workspace_id=WORKSPACE,
        nuotao_product_id=pid,
        woocommerce_id=2698,
        woocommerce_variation_id=2700,
        identity_state=IDENTITY_STATE_VARIATION,
    )
    db_session.add(dup)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # 不同变体可共存(同一商品多变体).
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=pid,
        woocommerce_id=2698,
        woocommerce_variation_id=2701,
        variation_sku="NT-1054599709111-3",
        trace_id="t-u2",
    )
    await db_session.commit()
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(ProductMapping)
            .where(
                ProductMapping.woocommerce_id == 2698,
                ProductMapping.identity_state == IDENTITY_STATE_VARIATION,
            )
        )
    ).scalar_one()
    assert count == 2

    # 商品级同键重复 ⇒ 商品级部分唯一索引拒绝.
    prod = Product(workspace_id=WORKSPACE, sku="FILTER-2687-B", name="Filter")
    db_session.add(prod)
    await db_session.flush()
    await idm.upsert_product_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=prod.id,
        woocommerce_id=2687,
        trace_id="t-u3",
    )
    await db_session.commit()
    dup_prod = ProductMapping(
        workspace_id=WORKSPACE,
        nuotao_product_id=prod.id,
        woocommerce_id=2687,
        identity_state=IDENTITY_STATE_PRODUCT,
    )
    db_session.add(dup_prod)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --- 7. SKU 重复 / 缺失 ----------------------------------------------------


@pytest.mark.asyncio
async def test_sku_duplicate_and_missing(db_session) -> None:
    """SKU 辅助非主键:重复 SKU 允许;SKU 缺失(NULL)允许."""
    product = await _make_product(db_session, sku="CHAIR-2669", name="Moon Chair")
    # 两个不同变体共用同一 SKU(历史 SKU 重复).
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2669,
        woocommerce_variation_id=2670,
        variation_sku="NT-844058953087-1",
        trace_id="t-sku-1",
    )
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2669,
        woocommerce_variation_id=2671,
        variation_sku="NT-844058953087-1",
        trace_id="t-sku-2",
    )
    await db_session.commit()
    count = (
        await db_session.execute(
            select(func.count()).select_from(ProductMapping).where(ProductMapping.variation_sku == "NT-844058953087-1")
        )
    ).scalar_one()
    assert count == 2  # 重复 SKU 合法

    # SKU 缺失 ⇒ NULL 允许.
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2669,
        woocommerce_variation_id=2672,
        variation_sku=None,
        trace_id="t-sku-3",
    )
    await db_session.commit()
    row = (
        (await db_session.execute(select(ProductMapping).where(ProductMapping.woocommerce_variation_id == 2672)))
        .scalars()
        .first()
    )
    assert row.variation_sku is None


# --- 8. workspace 隔离 ------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_isolation(db_session) -> None:
    """不同 workspace 相同 WC id/vid 各自映射,不冲突."""
    ws_a = WORKSPACE
    ws_b = uuid4()
    pa = await _make_product(db_session, sku="GAITER-A", name="Gaiters A", workspace_id=ws_a)
    pb = await _make_product(db_session, sku="GAITER-B", name="Gaiters B", workspace_id=ws_b)
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=ws_a,
        nuotao_product_id=pa.id,
        woocommerce_id=2818,
        woocommerce_variation_id=2828,
        variation_sku="NT-799401169116-BLK",
        trace_id="t-ws-1",
    )
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=ws_b,
        nuotao_product_id=pb.id,
        woocommerce_id=2818,
        woocommerce_variation_id=2828,
        variation_sku="NT-799401169116-BLK",
        trace_id="t-ws-2",
    )
    await db_session.commit()
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(ProductMapping)
            .where(
                ProductMapping.woocommerce_id == 2818,
                ProductMapping.woocommerce_variation_id == 2828,
            )
        )
    ).scalar_one()
    assert count == 2  # 两个 workspace 各自一条


# --- 9. 多 Offer 映射 -------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_offer_mapping(db_session) -> None:
    """一变体 ↔ 多供应商 ↔ 多 Offer 独立存在(多对多)."""
    _ = await _make_product(db_session, sku="LIGHT-2565", name="Work Light")
    await idm.upsert_offer_mapping(
        db_session,
        workspace_id=WORKSPACE,
        supplier_id=None,
        source_offer_id="OFFER-A",
        wc_product_id=2565,
        wc_variation_id=2588,
        effective_at=None,
        trace_id="t-offer-1",
    )
    await idm.upsert_offer_mapping(
        db_session,
        workspace_id=WORKSPACE,
        supplier_id=None,
        source_offer_id="OFFER-B",
        wc_product_id=2565,
        wc_variation_id=2588,
        effective_at=None,
        trace_id="t-offer-2",
    )
    await db_session.commit()
    rows = (
        (
            await db_session.execute(
                select(SupplierOfferMapping).where(
                    SupplierOfferMapping.wc_variation_id == 2588,
                    SupplierOfferMapping.mapping_status == MAPPING_STATUS_MAPPED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2  # 两个 Offer 独立存在
    assert {r.source_offer_id for r in rows} == {"OFFER-A", "OFFER-B"}


# --- 10. Offer 失效 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_offer_invalidation(db_session) -> None:
    """Offer 失效 ⇒ archived,历史报价保留不删除."""
    _ = await _make_product(db_session, sku="BOTTLE-2838", name="Titanium Bottle")
    await idm.upsert_offer_mapping(
        db_session,
        workspace_id=WORKSPACE,
        supplier_id=None,
        source_offer_id="OFFER-B1",
        wc_product_id=2838,
        wc_variation_id=2848,
        trace_id="t-inv-1",
    )
    await db_session.commit()
    archived = await idm.archive_offer_mapping(
        db_session,
        workspace_id=WORKSPACE,
        source_offer_id="OFFER-B1",
        wc_product_id=2838,
        wc_variation_id=2848,
        trace_id="t-inv-2",
    )
    await db_session.commit()
    assert archived == 1
    row = (
        (
            await db_session.execute(
                select(SupplierOfferMapping).where(SupplierOfferMapping.source_offer_id == "OFFER-B1")
            )
        )
        .scalars()
        .first()
    )
    assert row.mapping_status == MAPPING_STATUS_ARCHIVED  # 保留,不删除


# --- 11. ProductMapping 冲突 ------------------------------------------------


@pytest.mark.asyncio
async def test_product_mapping_conflict(db_session) -> None:
    """错误(过期)映射不覆盖正确映射:同键(同 offer)保留最新 effective_at,旧版 archived."""
    from datetime import UTC, datetime, timedelta

    _ = await _make_product(db_session, sku="CRAMPON-2772", name="Crampons")
    older = datetime(2026, 11, 1, tzinfo=UTC)
    newer = older + timedelta(days=5)
    # 正确映射(同一 Offer,更晚 effective_at)。
    await idm.upsert_offer_mapping(
        db_session,
        workspace_id=WORKSPACE,
        supplier_id=None,
        source_offer_id="OFFER-X",
        wc_product_id=2772,
        wc_variation_id=2772,
        effective_at=newer,
        trace_id="t-conf-new",
    )
    await db_session.commit()
    # 过期/错误报价(同一 Offer,更早 effective_at)⇒ 应被归档,不覆盖正确映射.
    await idm.upsert_offer_mapping(
        db_session,
        workspace_id=WORKSPACE,
        supplier_id=None,
        source_offer_id="OFFER-X",
        wc_product_id=2772,
        wc_variation_id=2772,
        effective_at=older,
        trace_id="t-conf-old",
    )
    await db_session.commit()

    def _as_utc(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    active = (
        (
            await db_session.execute(
                select(SupplierOfferMapping).where(
                    SupplierOfferMapping.wc_variation_id == 2772,
                    SupplierOfferMapping.mapping_status == MAPPING_STATUS_MAPPED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(active) == 1
    assert _as_utc(active[0].effective_at) == newer  # 正确(最新)映射保留
    # 历史归档行保留(不删除)。
    archived = (
        (
            await db_session.execute(
                select(SupplierOfferMapping).where(
                    SupplierOfferMapping.wc_variation_id == 2772,
                    SupplierOfferMapping.mapping_status == MAPPING_STATUS_ARCHIVED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(archived) == 1
    assert _as_utc(archived[0].effective_at) == older


# --- 12. OrderItem 变体关联 -------------------------------------------------


@pytest.mark.asyncio
async def test_order_item_variation_link(db_session) -> None:
    """订单行变体关联:新订单优先记录确定身份;历史无法确定 ⇒ UNKNOWN."""
    product = await _make_product(db_session, sku="HEADLAMP-2864", name="MH1 Headlamp")
    order = Order(workspace_id=WORKSPACE, external_order_id="ord-v1", status="received")
    db_session.add(order)
    await db_session.flush()
    # 新订单:变体确定.
    item = await idm.record_order_item(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        product_id=product.id,
        name="Headlamp Dual",
        quantity=1,
        unit_price=125,
        line_total=125,
        wc_product_id=2864,
        wc_variation_id=2889,
        variation_sku="NT-964465929482-D",
        product_has_variations=True,
        trace_id="t-ord-1",
    )
    await db_session.commit()
    assert item.identity_state == IDENTITY_STATE_VARIATION
    assert item.wc_variation_id == 2889
    assert item.variation_sku == "NT-964465929482-D"
    # 历史:无 vid + 商品有变体 ⇒ UNKNOWN_LEGACY.
    order2 = Order(workspace_id=WORKSPACE, external_order_id="ord-v2", status="received")
    db_session.add(order2)
    await db_session.flush()
    item2 = await idm.record_order_item(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order2.id,
        product_id=product.id,
        name="Headlamp legacy",
        quantity=1,
        unit_price=69,
        line_total=69,
        wc_product_id=2864,
        wc_variation_id=None,
        variation_sku=None,
        product_has_variations=True,
        trace_id="t-ord-2",
    )
    await db_session.commit()
    assert item2.identity_state == IDENTITY_STATE_UNKNOWN_LEGACY


# --- 13. Inventory 变体级更新 ----------------------------------------------


@pytest.mark.asyncio
async def test_inventory_variation_update(db_session) -> None:
    """库存变体级更新:两个变体各自库存,不互相覆盖."""
    product = await _make_product(db_session, sku="PAD-INV", name="Pad Inventory")
    r1 = await idm.update_inventory_variation(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        wc_product_id=2698,
        wc_variation_id=2700,
        product_has_variations=True,
        location="cn",
        quantity=100,
        variation_sku="NT-1054599709111-2",
        trace_id="t-inv-1",
    )
    r2 = await idm.update_inventory_variation(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        wc_product_id=2698,
        wc_variation_id=2701,
        product_has_variations=True,
        location="cn",
        quantity=50,
        variation_sku="NT-1054599709111-3",
        trace_id="t-inv-2",
    )
    await db_session.commit()
    assert r1["status"] == "updated"
    assert r2["status"] == "updated"
    rows = (
        (await db_session.execute(select(InventorySnapshot).where(InventorySnapshot.product_id == product.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 2
    by_vid = {r.variation_id: r.quantity for r in rows}
    assert by_vid == {2700: 100, 2701: 50}


# --- 14. Inventory 防父商品误更新 ------------------------------------------


@pytest.mark.asyncio
async def test_inventory_guard_no_parent_bulk(db_session) -> None:
    """禁止仅凭父 SKU 更新整个变体集合:无 vid 且商品有变体 ⇒ 跳过/UNKNOWN."""
    product = await _make_product(db_session, sku="PAD-GUARD", name="Pad Guard")
    result = await idm.update_inventory_variation(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        wc_product_id=2698,
        wc_variation_id=None,
        product_has_variations=True,
        location="cn",
        quantity=999,
        trace_id="t-guard-1",
    )
    await db_session.commit()
    assert result["status"] == "skipped_unknown_variation"
    # 未批量覆盖:无任何库存行被创建.
    count = (await db_session.execute(select(func.count()).select_from(InventorySnapshot))).scalar_one()
    assert count == 0


# --- 15. CostSnapshot 历史一致性 -------------------------------------------


@pytest.mark.asyncio
async def test_cost_snapshot_history_consistency(db_session) -> None:
    """成本快照 append-only:供应商报价变化不覆盖历史,变体维度明确对应."""
    product = await _make_product(db_session, sku="COST-2743", name="Heated Liner")
    await idm.append_cost_snapshot(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        purchase_cost=5.32,
        total_landed_cost=7.00,
        wc_variation_id=2744,
        variation_sku="NT-986492089515-1",
        source="supplier_offer",
        trace_id="t-cost-1",
    )
    await idm.append_cost_snapshot(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        purchase_cost=5.50,
        total_landed_cost=7.30,
        wc_variation_id=2744,
        variation_sku="NT-986492089515-1",
        source="supplier_offer",
        trace_id="t-cost-2",
    )
    await db_session.commit()
    rows = (
        (await db_session.execute(select(ProductCostSnapshot).where(ProductCostSnapshot.product_id == product.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 2  # 历史保留,不覆盖
    # 按时间序,第一条未被覆盖.
    first = rows[0]
    assert float(first.purchase_cost) == 5.32
    assert first.variation_id == 2744
    assert first.variation_sku == "NT-986492089515-1"


# --- 16. 回填幂等 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_idempotent(db_session) -> None:
    """71 行回填:第一次创建 70 VARIATION + 1 PRODUCT;第二次全 skipped(幂等)."""
    rows = _load_71_rows()
    batch = idm.classify_csv_rows(rows)
    product_ids: dict[int, UUID] = {}
    for cls in batch.rows:
        if cls.wc_product_id not in product_ids:
            p = await _make_product(db_session, sku=f"SKU-{cls.wc_product_id}", name=str(cls.wc_product_id))
            product_ids[cls.wc_product_id] = p.id
    await db_session.commit()

    result1 = await idm.backfill_71_rows(
        db_session,
        workspace_id=WORKSPACE,
        rows=rows,
        product_ids=product_ids,
        trace_id="t-backfill-1",
    )
    await db_session.commit()
    assert result1["classified"] == {"VARIATION": 70, "PRODUCT": 1, "UNKNOWN_LEGACY": 0, "total": 71}
    assert result1["created"] == 71
    assert result1["skipped"] == 0

    # 重复回填 ⇒ 不重复创建(幂等).
    result2 = await idm.backfill_71_rows(
        db_session,
        workspace_id=WORKSPACE,
        rows=rows,
        product_ids=product_ids,
        trace_id="t-backfill-2",
    )
    await db_session.commit()
    assert result2["created"] == 0
    assert result2["skipped"] == 71

    total = (await db_session.execute(select(func.count()).select_from(ProductMapping))).scalar_one()
    assert total == 71  # 只有 71 条,无重复


# --- 17. Migration 语法/元数据 ---------------------------------------------


@pytest.mark.asyncio
async def test_migration_syntax_and_schema(db_session) -> None:
    """Migration 模块语法有效 + 模型 create_all 生成部分唯一索引(SQLite 兼容)."""
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0092_identity_model.py"
    source = migration_path.read_text(encoding="utf-8")
    tree = ast.parse(source)  # 语法有效
    assert tree is not None
    assert "def upgrade()" in source and "def downgrade()" in source

    # create_all 已由 conftest 触发(SQLite),验证 supplier_offer_mappings 表与部分唯一索引存在.
    from app.models.base import Base

    tables = Base.metadata.tables
    assert "supplier_offer_mappings" in tables
    assert "product_mappings" in tables
    pm = tables["product_mappings"]
    assert any(i.name == "ux_product_mapping_product" for i in pm.indexes)
    assert any(i.name == "ux_product_mapping_variation" for i in pm.indexes)
    assert any(i.name == "ix_product_mapping_variation_sku" for i in pm.indexes)


# --- 18. event_log + trace_id -----------------------------------------------


@pytest.mark.asyncio
async def test_event_log_trace_id(db_session) -> None:
    """所有写操作走 event_service,event_log 保留 trace_id."""
    product = await _make_product(db_session, sku="EVENT-2565", name="Event Light")
    await idm.upsert_variation_mapping(
        db_session,
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2565,
        woocommerce_variation_id=2588,
        variation_sku="NT-1011441593585-GREEN",
        trace_id="trace-evt-1",
    )
    await db_session.commit()
    rows, total = await event_service_query(db_session, "product_mapping.variation_created")
    assert total >= 1
    assert any(r.trace_id == "trace-evt-1" for r in rows)


async def event_service_query(session, event_type: str):
    from app.services import event_service

    return await event_service.query_events(session, workspace_id=WORKSPACE, event_type=event_type)


# --- 19. 历史兼容 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_historical_compatibility(db_session) -> None:
    """历史记录兼容:无身份列 ⇒ 默认 UNKNOWN_LEGACY;不自动 PRODUCT;存量数据保留."""
    product = await _make_product(db_session, sku="HIST-2593", name="Hiking Backpack")
    # 模拟历史行:未显式设置身份(默认 UNKNOWN_LEGACY).
    legacy = ProductMapping(
        workspace_id=WORKSPACE,
        nuotao_product_id=product.id,
        woocommerce_id=2593,
        woocommerce_variation_id=None,
    )
    db_session.add(legacy)
    await db_session.commit()
    assert legacy.identity_state == IDENTITY_STATE_UNKNOWN_LEGACY
    # 兼容:旧 Product 无变体维度字段也能读取(变体维度可空).
    row = (
        (await db_session.execute(select(ProductMapping).where(ProductMapping.woocommerce_id == 2593)))
        .scalars()
        .first()
    )
    assert row.identity_state == IDENTITY_STATE_UNKNOWN_LEGACY
    assert row.woocommerce_variation_id is None

    # 历史订单/库存/成本快照字段默认 NULL 且不报错.
    order = Order(workspace_id=WORKSPACE, external_order_id="ord-hist", status="received")
    db_session.add(order)
    await db_session.flush()
    item = OrderItem(
        workspace_id=WORKSPACE,
        order_id=order.id,
        name="legacy",
        quantity=1,
        unit_price=0,
        line_total=0,
    )
    db_session.add(item)
    inv = InventorySnapshot(workspace_id=WORKSPACE, product_id=product.id, location="cn", quantity=5)
    db_session.add(inv)
    cost = ProductCost(workspace_id=WORKSPACE, product_id=product.id)
    db_session.add(cost)
    await db_session.commit()
    assert item.identity_state == IDENTITY_STATE_UNKNOWN_LEGACY
    assert inv.variation_id is None
    assert cost.variation_id is None
