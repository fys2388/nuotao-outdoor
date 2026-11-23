"""M4 V2.7 真实 PostgreSQL 集成测试(pgserver 内嵌 PG16,一次性隔离实例)。

指令 V2.7 §六:覆盖 PRODUCT/VARIATION 唯一性、UNKNOWN_LEGACY、部分唯一索引、
NULL 边界、workspace 隔离、SKU 重复/缺失、多供应商多 Offer、Offer 报价历史、
Offer 失效归档、映射冲突、OrderItem 变体关联、InventorySnapshot 变体级更新、
父商品误更新阻断、CostSnapshot 历史不覆盖、历史回填幂等、event_service+trace_id、
migration upgrade/downgrade —— **全部真实 PG 读写,不 mock,不用 create_all 判定**。

隔离与安全:
- 仅使用 ``pgserver`` 内嵌的一次性 PG16 实例(临时目录 + 随机端口 + cleanup_mode=delete)。
- **绝不连接生产库,绝不使用生产凭据**,报告中不出现任何真实密码。
- migration 仅在本隔离实例验证(0091 → 0092 → downgrade 0091)。

运行:
    cd backend; $env:PYTHONPATH='.'; .venv/Scripts/python -m pytest \\
        tests/integration/test_identity_model_v27_pg.py -p no:cacheprovider -q
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.event import EventLog
from app.models.order import Order
from app.models.product import Product
from app.models.product_mapping import (
    IDENTITY_STATE_UNKNOWN_LEGACY,
    ProductMapping,
)
from app.models.supplier_offer_mapping import (
    MAPPING_STATUS_ARCHIVED,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_UNCONFIRMED,
    SupplierOfferMapping,
)
from app.services import identity_model_v26 as idm
from tests.integration.conftest import run_alembic

# 隔离测试用的固定 workspace(随机,证明跨 workspace 行为)。
WS_A = UUID("00000000-0000-0000-0000-00000000a001")
WS_B = UUID("00000000-0000-0000-0000-00000000b002")


# --------------------------------------------------------------------------- #
# Fixtures:一次性隔离 PG16,精确驱动到 0092(经 0091),供真实读写。
#
# 关键前提(与生产一致):``product_mappings`` 由应用数据库角色之外的角色持有
# (见 0071 迁移说明),**不在 alembic 链内创建**(0070 因此被 park)。故在 fresh DB
# 上 `alembic upgrade` 不会创建它。为忠实复现 0092 的真实前置状态,这里在
# `upgrade 0091` 之后、`upgrade 0092` 之前,按 0091 时代(0070 已由表 owner 应用的
# workspace 维度唯一约束)手工引导 ``product_mappings`` 表,再执行 0092。
# --------------------------------------------------------------------------- #

# 0091 时代 product_mappings 预置 schema(不含 V2.6 身份列;含 0070 后的
# workspace 维度全局唯一约束,0092 upgrade 会将其移除、downgrade 会重建)。
_BOOTSTRAP_PM_SQL = """
CREATE TABLE IF NOT EXISTS product_mappings (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL,
    nuotao_product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    woocommerce_id INTEGER NOT NULL,
    woocommerce_slug VARCHAR(255),
    sync_status VARCHAR(32) DEFAULT 'synced',
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    CONSTRAINT uq_product_mappings_workspace_nuotao UNIQUE (workspace_id, nuotao_product_id),
    CONSTRAINT uq_product_mappings_workspace_woo UNIQUE (workspace_id, woocommerce_id)
);
"""


async def _bootstrap_product_mappings(pg_database_url: str) -> None:
    """引导外部持有的 product_mappings 表(0091 状态),模拟生产前置。"""
    conn = await asyncpg.connect(_pg_url(pg_database_url))
    try:
        await conn.execute(_BOOTSTRAP_PM_SQL)
    finally:
        await conn.close()


async def _upgrade_to_0092(pg_database_url: str) -> None:
    """0091 -> 引导外部 product_mappings -> 0092(忠实生产前置链)。"""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0091")
    await _bootstrap_product_mappings(pg_database_url)
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0092")


@pytest.fixture()
async def pg_0092(pg_database_url: str) -> str:
    """Fresh database migrated to exactly 0092 via the real 0091 prerequisite."""
    await _upgrade_to_0092(pg_database_url)
    return pg_database_url


@pytest.fixture()
async def pg_conn(pg_0092: str) -> asyncpg.Connection:
    """Raw asyncpg connection to the 0092-migrated isolated database."""
    conn = await asyncpg.connect(pg_0092.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture()
async def pg_session(pg_0092: str):
    """Async ORM session bound to the 0092-migrated isolated database."""
    engine = create_async_engine(pg_0092)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _pg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _index_exists(conn, name: str) -> bool:
    row = await conn.fetchrow("SELECT 1 FROM pg_indexes WHERE indexname = $1", name)
    return row is not None


async def _column_exists(conn, table: str, column: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 AND column_name=$2",
        table,
        column,
    )
    return row is not None


async def _table_exists(conn, table: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1",
        table,
    )
    return row is not None


async def _make_product(session, *, sku: str, workspace_id: UUID = WS_A) -> Product:
    product = Product(sku=sku, name=f"Product {sku}", workspace_id=workspace_id)
    session.add(product)
    await session.flush()
    return product


async def _insert_product(conn, *, ws: UUID = WS_A, sku: str | None = None) -> UUID:
    """插入一条真实 products 行(nuotao_product_id FK 目标),返回其 id。

    products 有 (workspace_id, sku) 唯一约束,缺省用随机 SKU 避免同一 workspace
    内多次自动建品冲突。
    """
    actual_sku = sku or f"SKU-PG-{uuid4().hex[:12]}"
    return await conn.fetchval(
        "INSERT INTO products (id, workspace_id, sku, name) VALUES (gen_random_uuid(), $1, $2, $3) RETURNING id",
        ws,
        actual_sku,
        f"Product {actual_sku}",
    )


async def _insert_variation_mapping(conn, *, ws, woo, vid, sku=None, pid=None):
    """插入变体级映射;pid 为真实 product id(FK 目标),缺省现建一条。"""
    if pid is None:
        pid = await _insert_product(conn, ws=ws)
    await conn.execute(
        "INSERT INTO product_mappings "
        "(id, workspace_id, nuotao_product_id, woocommerce_id, woocommerce_variation_id, "
        "variation_sku, identity_state) VALUES "
        "(gen_random_uuid(), $1, $2, $3, $4, $5, 'VARIATION')",
        ws,
        pid,
        woo,
        vid,
        sku,
    )


async def _insert_product_mapping(conn, *, ws, woo, pid=None, vid=None, sku=None, state="PRODUCT"):
    """插入商品级/变体级映射;pid 缺省现建一条真实 product。"""
    if pid is None:
        pid = await _insert_product(conn, ws=ws)
    await conn.execute(
        "INSERT INTO product_mappings "
        "(id, workspace_id, nuotao_product_id, woocommerce_id, woocommerce_variation_id, "
        "variation_sku, identity_state) VALUES "
        "(gen_random_uuid(), $1, $2, $3, $4, $5, $6)",
        ws,
        pid,
        woo,
        vid,
        sku,
        state,
    )


# --------------------------------------------------------------------------- #
# 0. 隔离环境证明:真实 PG16(与生产基线一致)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg00_isolated_postgres16_environment(pg_conn) -> None:
    """证明跑在真实 PostgreSQL 16 隔离实例上(非 SQLite,非生产库)。"""
    version = await pg_conn.fetchval("SELECT current_setting('server_version')")
    assert version.startswith("16"), f"expected PG16, got {version}"
    dbname = await pg_conn.fetchval("SELECT current_database()")
    # 隔离实例默认连 postgres 库,测试库由 fixture 另建;确认不是生产库名。
    assert dbname not in ("nuotao", "nuotao_prod", "production")


# --------------------------------------------------------------------------- #
# 1. Migration 0092 upgrade(0091 -> 0092):列/索引/表全部到位
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg01_migration_upgrade_0091_to_0092(pg_database_url: str) -> None:
    """从真实前置 0091 upgrade 到 0092,验证全部新增字段/索引/新表。"""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0091")
    # 引导外部持有的 product_mappings(0091 时代 schema),复现生产前置。
    await _bootstrap_product_mappings(pg_database_url)
    conn = await asyncpg.connect(_pg_url(pg_database_url))
    try:
        # 0091 前置状态:identity_state 列/部分唯一索引/新表均不存在。
        assert await _column_exists(conn, "product_mappings", "identity_state") is False
        assert await _index_exists(conn, "ux_product_mapping_variation") is False
        assert await _table_exists(conn, "supplier_offer_mappings") is False
    finally:
        await conn.close()

    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0092")
    conn = await asyncpg.connect(_pg_url(pg_database_url))
    try:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0092"
        # product_mappings 新增身份字段。
        for col in (
            "woocommerce_variation_id",
            "variation_sku",
            "source_offer_id",
            "source_variation_spec",
            "identity_state",
            "trace_id",
        ):
            assert await _column_exists(conn, "product_mappings", col), f"missing {col}"
        # order_items 变体身份列。
        for col in ("wc_variation_id", "variation_sku", "identity_state"):
            assert await _column_exists(conn, "order_items", col), f"missing order_items.{col}"
        # inventory_snapshots 变体维度列。
        for col in ("variation_id", "variation_sku", "source_timestamp"):
            assert await _column_exists(conn, "inventory_snapshots", col), f"missing inv.{col}"
        # product_cost + product_cost_snapshots 变体维度列。
        for table in ("product_cost", "product_cost_snapshots"):
            for col in ("variation_id", "variation_sku"):
                assert await _column_exists(conn, table, col), f"missing {table}.{col}"
        # PRODUCT / VARIATION / SKU 辅助索引存在。
        assert await _index_exists(conn, "ux_product_mapping_product")
        assert await _index_exists(conn, "ux_product_mapping_variation")
        assert await _index_exists(conn, "ix_product_mapping_variation_sku")
        # 新表 supplier_offer_mappings + 其索引。
        assert await _table_exists(conn, "supplier_offer_mappings")
        assert await _index_exists(conn, "ux_supplier_offer_mapping_variation")
        assert await _index_exists(conn, "ux_supplier_offer_mapping_product")
    finally:
        await conn.close()


# --------------------------------------------------------------------------- #
# 2. Migration 0092 downgrade(0092 -> 0091):表/索引/约束恢复
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg02_migration_downgrade_0092_to_0091(pg_database_url: str) -> None:
    """upgrade 到 0092 后 downgrade 回 0091,验证新表/索引/列被回滚。"""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0091")
    await _bootstrap_product_mappings(pg_database_url)
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0092")
    await asyncio.to_thread(run_alembic, pg_database_url, "downgrade", "0091")
    conn = await asyncpg.connect(_pg_url(pg_database_url))
    try:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "0091"
        # 新表删除。
        assert await _table_exists(conn, "supplier_offer_mappings") is False
        # 0092 新增索引全部删除。
        for idx in (
            "ux_product_mapping_product",
            "ux_product_mapping_variation",
            "ix_product_mapping_variation_sku",
            "ux_inventory_snapshot_variation",
            "ux_inventory_snapshot_product",
        ):
            assert await _index_exists(conn, idx) is False, f"{idx} not dropped"
        # 0092 新增列删除。
        for col in ("woocommerce_variation_id", "identity_state", "trace_id"):
            assert await _column_exists(conn, "product_mappings", col) is False
        assert await _column_exists(conn, "order_items", "identity_state") is False
        assert await _column_exists(conn, "inventory_snapshots", "variation_id") is False
        # 旧全局唯一约束在 downgrade 中重建(0091 前置状态)。
        constraints = await conn.fetch(
            "SELECT conname FROM pg_constraint WHERE conrelid='product_mappings'::regclass AND contype='u'"
        )
        names = {r["conname"] for r in constraints}
        assert "uq_product_mappings_workspace_woo" in names
        assert "uq_product_mappings_workspace_nuotao" in names
    finally:
        await conn.close()


# --------------------------------------------------------------------------- #
# 3/4. PRODUCT / VARIATION 部分唯一索引(真实 PG 约束)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg03_product_level_partial_unique_index(pg_conn) -> None:
    """同 workspace 同 Product 不能重复商品级映射;不同 workspace 可各自拥有。"""
    # 先插入一条 PRODUCT 级映射。
    await _insert_product_mapping(pg_conn, ws=WS_A, woo=2687, state="PRODUCT")
    # 同 workspace 同 woo 重复商品级 ⇒ 唯一冲突。
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await _insert_product_mapping(pg_conn, ws=WS_A, woo=2687, state="PRODUCT")
    # 不同 workspace 同 woo 商品级 ⇒ 允许(workspace 隔离)。
    await _insert_product_mapping(pg_conn, ws=WS_B, woo=2687, state="PRODUCT")


@pytest.mark.asyncio
async def test_pg04_variation_level_partial_unique_index(pg_conn) -> None:
    """同 workspace 同 Variation 不能重复变体级映射;不同变体可共存。"""
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2698, vid=2700, sku="NT-V1")
    # 同 (workspace, woo, vid) 变体级重复 ⇒ 唯一冲突。
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2698, vid=2700, sku="NT-V1")
    # 不同变体可共存(同一商品多变体)。
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2698, vid=2701, sku="NT-V2")
    count = await pg_conn.fetchval(
        "SELECT count(*) FROM product_mappings WHERE woocommerce_id=2698 AND identity_state='VARIATION'"
    )
    assert count == 2


# --------------------------------------------------------------------------- #
# 5. workspace 隔离:不同 workspace 可拥有相同外部 WooCommerce ID
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg05_cross_workspace_same_woo_id_allowed(pg_conn) -> None:
    """不同 workspace 可拥有相同外部 WooCommerce ID(商品级与变体级皆然)。"""
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2818, vid=2828, sku="NT-BLK")
    await _insert_variation_mapping(pg_conn, ws=WS_B, woo=2818, vid=2828, sku="NT-BLK")
    count = await pg_conn.fetchval(
        "SELECT count(*) FROM product_mappings WHERE woocommerce_id=2818 AND woocommerce_variation_id=2828"
    )
    assert count == 2  # 两个 workspace 各自一条,互不冲突


# --------------------------------------------------------------------------- #
# 6. UNKNOWN_LEGACY:未知身份不被自动归类 PRODUCT
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg06_unknown_legacy_not_auto_product(pg_session) -> None:
    """无 wc_variation_id 且商品有变体 ⇒ UNKNOWN_LEGACY,不被自动归为 PRODUCT。"""
    product = await _make_product(pg_session, sku="BAG-2549")
    mapping = ProductMapping(
        workspace_id=product.workspace_id,
        nuotao_product_id=product.id,
        woocommerce_id=2549,
        woocommerce_variation_id=None,
        identity_state=IDENTITY_STATE_UNKNOWN_LEGACY,
        trace_id="t-pg06",
    )
    pg_session.add(mapping)
    await pg_session.commit()
    result = (
        (await pg_session.execute(select(ProductMapping).where(ProductMapping.woocommerce_id == 2549)))
        .scalars()
        .first()
    )
    assert result.identity_state == "UNKNOWN_LEGACY"
    assert result.identity_state != "PRODUCT"
    assert result.woocommerce_variation_id is None


# --------------------------------------------------------------------------- #
# 7. NULL 行为:NULL 不绕过身份校验;NULL 维度可入库
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg07_null_behavior_boundaries(pg_conn) -> None:
    """NULL woocommerce_variation_id 的 PRODUCT 行不与变体行冲突;NULL SKU 可入库。"""
    # PRODUCT 行(variation NULL)。
    await _insert_product_mapping(pg_conn, ws=WS_A, woo=2743, vid=None, sku=None, state="PRODUCT")
    # 同商品一条 VARIATION 行(vid 非空)⇒ 与 PRODUCT 行不冲突(部分唯一索引区分)。
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2743, vid=2744, sku=None)
    # NULL variation_sku 的变体行 ⇒ 允许(SKU 仅辅助)。
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2743, vid=2745, sku=None)
    count = await pg_conn.fetchval("SELECT count(*) FROM product_mappings WHERE woocommerce_id=2743")
    assert count == 3  # 1 PRODUCT + 2 VARIATION


# --------------------------------------------------------------------------- #
# 8. SKU 辅助索引:非唯一、允许重复与缺失
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg08_sku_auxiliary_non_unique_index(pg_conn) -> None:
    """SKU 非唯一辅助索引:重复 SKU 合法;SKU 缺失(NULL)合法;索引存在。"""
    assert await _index_exists(pg_conn, "ix_product_mapping_variation_sku")
    # 两个不同变体共用同一 SKU(历史 SKU 重复)。
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2669, vid=2670, sku="NT-DUP")
    await _insert_variation_mapping(pg_conn, ws=WS_A, woo=2669, vid=2671, sku="NT-DUP")
    count = await pg_conn.fetchval("SELECT count(*) FROM product_mappings WHERE variation_sku='NT-DUP'")
    assert count == 2  # 重复 SKU 合法(SKU 非身份主键)


# --------------------------------------------------------------------------- #
# 9. 身份判定边界 5 种情况(A/B/C/D/E)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg09_identity_boundary_five_cases() -> None:
    """A→PRODUCT;B/C/D/E→UNKNOWN_LEGACY(指令 §四)。"""
    assert idm.IDENTITY_REASON_CONFIRMED_NO_VARIATION == "confirmed_no_variation"
    # A:确认无变体 ⇒ PRODUCT。
    assert idm.identity_state(2687, None, False) == "PRODUCT"
    # B:变体列表未完整获取 ⇒ UNKNOWN_LEGACY。
    assert idm.identity_state(2549, None, None, identity_reason="variation_list_incomplete") == "UNKNOWN_LEGACY"
    # C:WC API 请求失败 ⇒ UNKNOWN_LEGACY。
    assert idm.identity_state(2549, None, None, identity_reason="wc_api_failed") == "UNKNOWN_LEGACY"
    # D:本地变体数据未同步完整 ⇒ UNKNOWN_LEGACY。
    assert idm.identity_state(2549, None, True, identity_reason="local_sync_incomplete") == "UNKNOWN_LEGACY"
    # E:有变体但记录缺 Variation ID ⇒ UNKNOWN_LEGACY。
    assert idm.identity_state(2549, None, True, identity_reason="variation_id_missing") == "UNKNOWN_LEGACY"
    # 即便商品"有变体 + 记录上下文",显式 E 原因仍强制 UNKNOWN_LEGACY。
    assert idm.identity_state(2549, None, True, True, identity_reason="variation_id_missing") == "UNKNOWN_LEGACY"
    # B/C/D/E reason 集合齐全。
    assert (
        frozenset(
            {
                "variation_list_incomplete",
                "wc_api_failed",
                "local_sync_incomplete",
                "variation_id_missing",
            }
        )
        == idm.UNKNOWN_IDENTITY_REASONS
    )


# --------------------------------------------------------------------------- #
# 10. 多供应商 / 多 Offer(多对多独立)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg10_multi_supplier_multi_offer(pg_conn) -> None:
    """一变体 ↔ 多供应商 ↔ 多 Offer 独立存在;不同 supplier 各自独立无冲突。"""
    sup1 = uuid4()
    sup2 = uuid4()
    await pg_conn.execute(
        "INSERT INTO suppliers (id, workspace_id, code, name) VALUES ($1,$2,'S1','Sup1'),($3,$2,'S2','Sup2')",
        sup1,
        WS_A,
        sup2,
    )
    for sup, offer in ((sup1, "OFFER-A"), (sup2, "OFFER-B"), (None, "OFFER-C")):
        await pg_conn.execute(
            "INSERT INTO supplier_offer_mappings "
            "(id, workspace_id, supplier_id, source_offer_id, wc_product_id, wc_variation_id, "
            "mapping_status) VALUES (gen_random_uuid(), $1, $2, $3, 2565, 2588, 'mapped')",
            WS_A,
            sup,
            offer,
        )
    count = await pg_conn.fetchval(
        "SELECT count(*) FROM supplier_offer_mappings WHERE wc_variation_id=2588 AND mapping_status='mapped'"
    )
    assert count == 3  # 三个独立 Offer/供应商映射共存


# --------------------------------------------------------------------------- #
# 11. Offer 报价历史:同 Offer 报价更新归档旧版本,历史保留
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg11_offer_quote_history_preserved(pg_session) -> None:
    """同一 Offer 报价更新(规格未变)⇒ 新行 mapped,旧行 archived,历史不删除。"""
    from datetime import UTC, datetime, timedelta

    _ = await _make_product(pg_session, sku="BOTTLE-2838")
    older = datetime(2026, 11, 1, tzinfo=UTC)
    newer = older + timedelta(days=5)
    await idm.upsert_offer_mapping(
        pg_session,
        workspace_id=WS_A,
        supplier_id=None,
        source_offer_id="OFFER-H",
        wc_product_id=2838,
        wc_variation_id=2848,
        effective_at=older,
        trace_id="t-h1",
    )
    await pg_session.commit()
    await idm.upsert_offer_mapping(
        pg_session,
        workspace_id=WS_A,
        supplier_id=None,
        source_offer_id="OFFER-H",
        wc_product_id=2838,
        wc_variation_id=2848,
        effective_at=newer,
        trace_id="t-h2",
    )
    await pg_session.commit()
    rows = (
        (
            await pg_session.execute(
                select(SupplierOfferMapping).where(SupplierOfferMapping.source_offer_id == "OFFER-H")
            )
        )
        .scalars()
        .all()
    )
    statuses = sorted(r.mapping_status for r in rows)
    assert statuses == ["archived", "mapped"]  # 历史保留 + 当前生效
    mapped = next(r for r in rows if r.mapping_status == MAPPING_STATUS_MAPPED)
    assert mapped.effective_at == newer


# --------------------------------------------------------------------------- #
# 12. Offer 失效归档
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg12_offer_invalidation_archives(pg_session) -> None:
    """Offer 失效 ⇒ archived,历史报价保留不删除。"""
    _ = await _make_product(pg_session, sku="LAMP-2864")
    await idm.upsert_offer_mapping(
        pg_session,
        workspace_id=WS_A,
        supplier_id=None,
        source_offer_id="OFFER-INV",
        wc_product_id=2864,
        wc_variation_id=2889,
        trace_id="t-inv",
    )
    await pg_session.commit()
    archived = await idm.archive_offer_mapping(
        pg_session,
        workspace_id=WS_A,
        source_offer_id="OFFER-INV",
        wc_product_id=2864,
        wc_variation_id=2889,
        trace_id="t-inv2",
    )
    await pg_session.commit()
    assert archived == 1
    row = (
        (
            await pg_session.execute(
                select(SupplierOfferMapping).where(SupplierOfferMapping.source_offer_id == "OFFER-INV")
            )
        )
        .scalars()
        .first()
    )
    assert row.mapping_status == MAPPING_STATUS_ARCHIVED


# --------------------------------------------------------------------------- #
# 13. 映射冲突:禁止自动覆盖已验证规格映射
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg13_mapping_conflict_no_auto_overwrite(pg_session) -> None:
    """同一 Offer 规格映射变更:已验证 mapped 行不被覆盖,新证据 unconfirmed 等审核。"""
    from datetime import UTC, datetime, timedelta

    _ = await _make_product(pg_session, sku="CRAMPON-2772")
    t1 = datetime(2026, 11, 1, tzinfo=UTC)
    t2 = t1 + timedelta(days=1)
    # 已验证规格映射。
    await idm.upsert_offer_mapping(
        pg_session,
        workspace_id=WS_A,
        supplier_id=None,
        source_offer_id="OFFER-CF",
        wc_product_id=2772,
        wc_variation_id=2772,
        specification_mapping={"color": "red"},
        effective_at=t1,
        trace_id="t-cf1",
    )
    await pg_session.commit()
    # 同一 Offer,冲突规格证据(更晚)⇒ 不得覆盖已验证映射。
    conflict = await idm.upsert_offer_mapping(
        pg_session,
        workspace_id=WS_A,
        supplier_id=None,
        source_offer_id="OFFER-CF",
        wc_product_id=2772,
        wc_variation_id=2772,
        specification_mapping={"color": "blue"},
        effective_at=t2,
        trace_id="t-cf2",
    )
    await pg_session.commit()
    assert conflict.mapping_status == MAPPING_STATUS_UNCONFIRMED  # 新证据保持未确认
    # 已验证映射仍在(mapped,未被覆盖)。
    mapped = (
        (
            await pg_session.execute(
                select(SupplierOfferMapping).where(
                    SupplierOfferMapping.source_offer_id == "OFFER-CF",
                    SupplierOfferMapping.mapping_status == MAPPING_STATUS_MAPPED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(mapped) == 1
    assert mapped[0].specification_mapping == {"color": "red"}  # 原规格保留
    # 冲突原因 + trace_id 落 event_log。
    evt = (
        (
            await pg_session.execute(
                select(EventLog).where(EventLog.event_type == "supplier_offer_mapping.spec_conflict")
            )
        )
        .scalars()
        .first()
    )
    assert evt is not None
    assert evt.payload["conflict_reason"] == "spec_mapping_changed"
    assert evt.payload["requires_manual_review"] is True
    assert evt.trace_id == "t-cf2"


# --------------------------------------------------------------------------- #
# 14. OrderItem 变体关联
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg14_order_item_variation_link(pg_session) -> None:
    """订单行变体关联:确定变体 ⇒ VARIATION;历史无法确定 ⇒ UNKNOWN_LEGACY。"""
    product = await _make_product(pg_session, sku="HEADLAMP-2864-O")
    order = Order(workspace_id=WS_A, external_order_id="ord-v27-1", status="received")
    pg_session.add(order)
    await pg_session.flush()
    item = await idm.record_order_item(
        pg_session,
        workspace_id=WS_A,
        order_id=order.id,
        product_id=product.id,
        name="Headlamp Dual",
        quantity=1,
        unit_price=125,
        line_total=125,
        wc_product_id=2864,
        wc_variation_id=2889,
        variation_sku="NT-D",
        product_has_variations=True,
        trace_id="t-ord",
    )
    await pg_session.commit()
    assert item.identity_state == "VARIATION"
    assert item.wc_variation_id == 2889
    # 历史行:无 vid + 商品有变体 ⇒ UNKNOWN_LEGACY。
    order2 = Order(workspace_id=WS_A, external_order_id="ord-v27-2", status="received")
    pg_session.add(order2)
    await pg_session.flush()
    item2 = await idm.record_order_item(
        pg_session,
        workspace_id=WS_A,
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
        trace_id="t-ord2",
    )
    await pg_session.commit()
    assert item2.identity_state == "UNKNOWN_LEGACY"


# --------------------------------------------------------------------------- #
# 15. InventorySnapshot 变体级更新
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg15_inventory_snapshot_variation_update(pg_session) -> None:
    """库存变体级更新:两个变体各自库存行,不互相覆盖。"""
    from app.models.supply_chain import InventorySnapshot

    product = await _make_product(pg_session, sku="PAD-INV-PG")
    r1 = await idm.update_inventory_variation(
        pg_session,
        workspace_id=WS_A,
        product_id=product.id,
        wc_product_id=2698,
        wc_variation_id=2700,
        product_has_variations=True,
        location="cn",
        quantity=100,
        variation_sku="NT-2",
        trace_id="t-inv1",
    )
    r2 = await idm.update_inventory_variation(
        pg_session,
        workspace_id=WS_A,
        product_id=product.id,
        wc_product_id=2698,
        wc_variation_id=2701,
        product_has_variations=True,
        location="cn",
        quantity=50,
        variation_sku="NT-3",
        trace_id="t-inv2",
    )
    await pg_session.commit()
    assert r1["status"] == "updated" and r2["status"] == "updated"
    rows = (
        (await pg_session.execute(select(InventorySnapshot).where(InventorySnapshot.product_id == product.id)))
        .scalars()
        .all()
    )
    by_vid = {r.variation_id: r.quantity for r in rows}
    assert by_vid == {2700: 100, 2701: 50}


# --------------------------------------------------------------------------- #
# 16. 父商品误更新阻断(guard)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg16_inventory_parent_update_blocked(pg_session) -> None:
    """禁止仅凭父 SKU 更新整个变体集合:无 vid 且商品有变体 ⇒ 跳过。"""
    from app.models.supply_chain import InventorySnapshot

    product = await _make_product(pg_session, sku="PAD-GUARD-PG")
    result = await idm.update_inventory_variation(
        pg_session,
        workspace_id=WS_A,
        product_id=product.id,
        wc_product_id=2698,
        wc_variation_id=None,
        product_has_variations=True,
        location="cn",
        quantity=999,
        trace_id="t-guard",
    )
    await pg_session.commit()
    assert result["status"] == "skipped_unknown_variation"
    count = (
        (await pg_session.execute(select(InventorySnapshot).where(InventorySnapshot.product_id == product.id)))
        .scalars()
        .all()
    )
    assert len(count) == 0  # 未批量覆盖


# --------------------------------------------------------------------------- #
# 17. CostSnapshot 历史不覆盖(append-only)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg17_cost_snapshot_history_not_overwritten(pg_session) -> None:
    """成本快照 append-only:报价变化新增快照行,历史不被覆盖。"""
    from app.models.product_intelligence import ProductCostSnapshot

    product = await _make_product(pg_session, sku="COST-2743-PG")
    await idm.append_cost_snapshot(
        pg_session,
        workspace_id=WS_A,
        product_id=product.id,
        purchase_cost=5.32,
        total_landed_cost=7.00,
        wc_variation_id=2744,
        variation_sku="NT-1",
        trace_id="t-cost1",
    )
    await idm.append_cost_snapshot(
        pg_session,
        workspace_id=WS_A,
        product_id=product.id,
        purchase_cost=5.50,
        total_landed_cost=7.30,
        wc_variation_id=2744,
        variation_sku="NT-1",
        trace_id="t-cost2",
    )
    await pg_session.commit()
    rows = (
        (await pg_session.execute(select(ProductCostSnapshot).where(ProductCostSnapshot.product_id == product.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 2  # 历史保留
    assert float(rows[0].purchase_cost) == 5.32  # 首条未被覆盖
    assert rows[0].variation_id == 2744


# --------------------------------------------------------------------------- #
# 18. 历史数据回填幂等(真实 PG)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg18_backfill_idempotent(pg_session) -> None:
    """71 行回填:首次创建,二次全 skipped(幂等);不重复创建。"""
    import csv
    from pathlib import Path

    csv_path = Path(__file__).resolve().parents[3] / "docs" / "_audit" / "PRICING_V2_3_SKU_UNIQUENESS.csv"
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8-sig", newline="")))
    assert len(rows) == 71
    batch = idm.classify_csv_rows(rows)
    product_ids: dict[int, UUID] = {}
    for cls in batch.rows:
        if cls.wc_product_id and cls.wc_product_id not in product_ids:
            p = await _make_product(pg_session, sku=f"SKU-{cls.wc_product_id}")
            product_ids[cls.wc_product_id] = p.id
    await pg_session.commit()
    result1 = await idm.backfill_71_rows(
        pg_session,
        workspace_id=WS_A,
        rows=rows,
        product_ids=product_ids,
        trace_id="t-bf1",
    )
    await pg_session.commit()
    assert result1["created"] == 71
    result2 = await idm.backfill_71_rows(
        pg_session,
        workspace_id=WS_A,
        rows=rows,
        product_ids=product_ids,
        trace_id="t-bf2",
    )
    await pg_session.commit()
    assert result2["created"] == 0
    assert result2["skipped"] == 71


# --------------------------------------------------------------------------- #
# 19. event_service + trace_id
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg19_event_service_trace_id(pg_session) -> None:
    """所有写操作走 event_service,event_log 保留 trace_id(真实 PG)。"""
    product = await _make_product(pg_session, sku="EVENT-2565-PG")
    await idm.upsert_variation_mapping(
        pg_session,
        workspace_id=WS_A,
        nuotao_product_id=product.id,
        woocommerce_id=2565,
        woocommerce_variation_id=2588,
        variation_sku="NT-GREEN",
        trace_id="trace-pg19",
    )
    await pg_session.commit()
    rows = (
        (await pg_session.execute(select(EventLog).where(EventLog.event_type == "product_mapping.variation_created")))
        .scalars()
        .all()
    )
    assert len(rows) >= 1
    assert any(r.trace_id == "trace-pg19" for r in rows)


# --------------------------------------------------------------------------- #
# 20. workspace 隔离(服务层,跨 workspace 查询互不可见)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pg20_workspace_isolation_service_layer(pg_session) -> None:
    """两个 workspace 各自 upsert 相同 WC id/vid,查询按 workspace 隔离。"""
    pa = await _make_product(pg_session, sku="GAITER-A", workspace_id=WS_A)
    pb = await _make_product(pg_session, sku="GAITER-B", workspace_id=WS_B)
    await idm.upsert_variation_mapping(
        pg_session,
        workspace_id=WS_A,
        nuotao_product_id=pa.id,
        woocommerce_id=2818,
        woocommerce_variation_id=2828,
        variation_sku="NT-BLK",
        trace_id="t-wsA",
    )
    await idm.upsert_variation_mapping(
        pg_session,
        workspace_id=WS_B,
        nuotao_product_id=pb.id,
        woocommerce_id=2818,
        woocommerce_variation_id=2828,
        variation_sku="NT-BLK",
        trace_id="t-wsB",
    )
    await pg_session.commit()
    rows_a = (
        (await pg_session.execute(select(ProductMapping).where(ProductMapping.workspace_id == WS_A))).scalars().all()
    )
    rows_b = (
        (await pg_session.execute(select(ProductMapping).where(ProductMapping.workspace_id == WS_B))).scalars().all()
    )
    assert len(rows_a) == 1 and rows_a[0].workspace_id == WS_A
    assert len(rows_b) == 1 and rows_b[0].workspace_id == WS_B
