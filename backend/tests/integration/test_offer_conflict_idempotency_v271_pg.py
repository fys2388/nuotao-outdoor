"""M4 V2.7.1 Supplier/Offer 映射冲突幂等性测试(真实 PG16,pgserver 隔离实例).

指令 V2.7.1 §六:针对 spec_conflict 的 5 种场景,确保冲突证据不会因重试无限重复创建;
已验证(mapped)映射不得被未经审核的新规格证据覆盖。

幂等键 = workspace + supplier + offer + variation + 冲突规格指纹(canonical spec)。

5 场景:
1. 同一冲突证据重复提交(同 trace_id)      -> 只 1 条 unconfirmed,不重复新建。
2. 相同 trace_id 重试                      -> 幂等,unconfirmed 数不变。
3. 不同 trace_id 但同一冲突事实(同规格)    -> 仍复用同一 unconfirmed(trace_id 更新)。
4. 不同供应商提供冲突规格                   -> 各自独立 unconfirmed(supplier 隔离)。
5. 人工审核后接受/驳回                      -> 接受=unconfirmed→mapped(旧 mapped 归档);
                                              驳回=unconfirmed→archived;均不新建。

隔离与安全:仅 pgserver 内嵌一次性 PG16;绝不连生产库、绝不用生产凭据。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import asyncpg
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.supplier_offer_mapping import (
    MAPPING_STATUS_ARCHIVED,
    MAPPING_STATUS_MAPPED,
    MAPPING_STATUS_UNCONFIRMED,
    SupplierOfferMapping,
)
from app.services import identity_model_v26 as idm
from tests.integration.conftest import run_alembic

WS = UUID("00000000-0000-0000-0000-00000000a271")
SUPPLIER_A = uuid4()
SUPPLIER_B = uuid4()
OFFER = "688123456"
WC_PRODUCT = 1001
WC_VARIATION = 2001

# 0091 时代 product_mappings 基线(身份列前),供 fresh DB 驱动到 0092。
_BOOTSTRAP_PM_SQL = """
CREATE TABLE product_mappings (
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


async def _pg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture()
async def pg_0092(pg_database_url: str) -> str:
    """Fresh DB driven to 0092 (0091 -> bootstrap external PM -> 0092)."""
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0091")
    conn = await asyncpg.connect(await _pg_url(pg_database_url))
    try:
        await conn.execute(_BOOTSTRAP_PM_SQL)
    finally:
        await conn.close()
    await asyncio.to_thread(run_alembic, pg_database_url, "upgrade", "0092")
    seed = await asyncpg.connect(await _pg_url(pg_database_url))
    try:
        await seed.execute(
            "INSERT INTO workspaces (id, name, code) VALUES ($1, 'ws-v271-offer', 'WS271O') "
            "ON CONFLICT (id) DO NOTHING",
            str(WS),
        )
        await seed.execute(
            "INSERT INTO suppliers (id, workspace_id, code, name) VALUES "
            "($1, $2, 'SUP-A', 'Supplier A'), ($3, $2, 'SUP-B', 'Supplier B')",
            SUPPLIER_A,
            str(WS),
            SUPPLIER_B,
        )
    finally:
        await seed.close()
    return pg_database_url


@pytest.fixture()
async def session(pg_0092: str):
    engine = create_async_engine(pg_0092)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as sess:
            yield sess
    finally:
        await engine.dispose()


async def _count_unconfirmed(sess, **kw) -> int:
    stmt = select(SupplierOfferMapping).where(
        SupplierOfferMapping.workspace_id == WS,
        SupplierOfferMapping.supplier_id == kw["supplier_id"],
        SupplierOfferMapping.source_offer_id == OFFER,
        SupplierOfferMapping.wc_variation_id == WC_VARIATION,
        SupplierOfferMapping.mapping_status == MAPPING_STATUS_UNCONFIRMED,
    )
    return len((await sess.execute(stmt)).scalars().all())


async def _setup_mapped(sess, spec: dict, effective_at: datetime) -> SupplierOfferMapping:
    """建立一条已验证(mapped)映射,作为冲突的既有基线."""
    return await idm.upsert_offer_mapping(
        sess,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=spec,
        effective_at=effective_at,
        evidence_source="manual",
        trace_id="setup-mapped",
    )


@pytest.mark.asyncio
async def test_offer_conflict_01_same_evidence_repeat_no_dup(session) -> None:
    """场景 1:同一冲突证据重复提交 -> 只 1 条 unconfirmed."""
    t0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    await _setup_mapped(session, {"color": "红"}, t0)
    conflict_spec = {"color": "蓝色"}  # 与 mapped 规格不同 -> 冲突
    t1 = t0 + timedelta(minutes=1)
    m1 = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t1,
        evidence_source="crawl",
        trace_id="retry-1",
    )
    assert m1.mapping_status == MAPPING_STATUS_UNCONFIRMED
    # 重复提交完全相同的冲突证据
    m2 = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t1 + timedelta(seconds=1),
        evidence_source="crawl",
        trace_id="retry-1",
    )
    assert m2.id == m1.id, "同一冲突证据应复用同一 unconfirmed 行"
    assert await _count_unconfirmed(session, supplier_id=SUPPLIER_A) == 1


@pytest.mark.asyncio
async def test_offer_conflict_02_same_trace_retry_idempotent(session) -> None:
    """场景 2:相同 trace_id 重试 -> 幂等,unconfirmed 数不变."""
    t0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    await _setup_mapped(session, {"size": "L"}, t0)
    conflict_spec = {"size": "XL"}
    for _ in range(3):
        await idm.upsert_offer_mapping(
            session,
            workspace_id=WS,
            supplier_id=SUPPLIER_A,
            source_offer_id=OFFER,
            wc_product_id=WC_PRODUCT,
            wc_variation_id=WC_VARIATION,
            specification_mapping=conflict_spec,
            effective_at=t0 + timedelta(minutes=1),
            evidence_source="crawl",
            trace_id="same-trace",
        )
    assert await _count_unconfirmed(session, supplier_id=SUPPLIER_A) == 1


@pytest.mark.asyncio
async def test_offer_conflict_03_diff_trace_same_fact_reuse(session) -> None:
    """场景 3:不同 trace_id 但同一冲突事实(同规格) -> 复用同一 unconfirmed."""
    t0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    await _setup_mapped(session, {"color": "黑"}, t0)
    conflict_spec = {"color": "白"}
    m1 = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t0 + timedelta(minutes=1),
        evidence_source="crawl",
        trace_id="trace-A",
    )
    m2 = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t0 + timedelta(minutes=2),
        evidence_source="crawl",
        trace_id="trace-B",
    )
    assert m2.id == m1.id, "同一冲突事实(同规格指纹)不同 trace_id 应复用同一行"
    assert m2.trace_id == "trace-B", "复用时更新为最新 trace_id"
    assert await _count_unconfirmed(session, supplier_id=SUPPLIER_A) == 1


@pytest.mark.asyncio
async def test_offer_conflict_04_diff_supplier_independent(session) -> None:
    """场景 4:不同供应商各自有基线 mapped,再各提交冲突规格 -> 各自独立 unconfirmed."""
    t0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    # 各供应商各自的基线 mapped(规格相同)
    await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping={"color": "绿"},
        effective_at=t0,
        evidence_source="manual",
        trace_id="base-A",
    )
    await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_B,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping={"color": "绿"},
        effective_at=t0,
        evidence_source="manual",
        trace_id="base-B",
    )
    conflict_spec = {"color": "黄"}
    await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t0 + timedelta(minutes=1),
        evidence_source="crawl",
        trace_id="sup-A",
    )
    await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_B,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t0 + timedelta(minutes=1),
        evidence_source="crawl",
        trace_id="sup-B",
    )
    assert await _count_unconfirmed(session, supplier_id=SUPPLIER_A) == 1
    assert await _count_unconfirmed(session, supplier_id=SUPPLIER_B) == 1


@pytest.mark.asyncio
async def test_offer_conflict_05_manual_review_accept_reject(session) -> None:
    """场景 5:人工审核后接受(->mapped,旧 mapped 归档)/驳回(->archived),均不新建."""
    t0 = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    mapped_old = await _setup_mapped(session, {"color": "红"}, t0)
    assert mapped_old.mapping_status == MAPPING_STATUS_MAPPED
    conflict_spec = {"color": "蓝"}
    unconf = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping=conflict_spec,
        effective_at=t0 + timedelta(minutes=1),
        evidence_source="crawl",
        trace_id="review",
    )
    assert unconf.mapping_status == MAPPING_STATUS_UNCONFIRMED

    # 人工「接受」:直接把 unconfirmed 行置为 mapped,旧 mapped 归档(应用层审核动作).
    unconf.mapping_status = MAPPING_STATUS_MAPPED
    mapped_old.mapping_status = MAPPING_STATUS_ARCHIVED
    await session.flush()
    await session.refresh(unconf)
    await session.refresh(mapped_old)
    assert unconf.mapping_status == MAPPING_STATUS_MAPPED
    assert mapped_old.mapping_status == MAPPING_STATUS_ARCHIVED

    # 人工「驳回」另一条冲突证据:置为 archived,不新建.
    await _setup_mapped(session, {"color": "红"}, t0)  # 恢复一条 mapped 基线
    unconf2 = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping={"color": "黑"},
        effective_at=t0 + timedelta(minutes=3),
        evidence_source="crawl",
        trace_id="review-2",
    )
    unconf2.mapping_status = MAPPING_STATUS_ARCHIVED  # 驳回
    await session.flush()
    # 驳回后该键已无 unconfirmed;再提交同一冲突会新建(旧已 archived 不参与幂等)
    again = await idm.upsert_offer_mapping(
        session,
        workspace_id=WS,
        supplier_id=SUPPLIER_A,
        source_offer_id=OFFER,
        wc_product_id=WC_PRODUCT,
        wc_variation_id=WC_VARIATION,
        specification_mapping={"color": "黑"},
        effective_at=t0 + timedelta(minutes=4),
        evidence_source="crawl",
        trace_id="review-3",
    )
    assert again.mapping_status == MAPPING_STATUS_UNCONFIRMED
    assert again.id != unconf2.id, "被驳回(archived)后的新证据允许新建,历史保留"
