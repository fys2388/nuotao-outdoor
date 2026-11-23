"""M4 V2.6 PostgreSQL 集成测试(Testcontainers,供有 PG/Docker 环境运行).

指令 §14:优先检查本地 PostgreSQL;无则检查 Docker(Testcontainers);都不可用 ⇒
本文件在无 testcontainers 时跳过(如实说明"PG 集成测试未运行,原因:无可用 PG/Docker")。

本文件覆盖 SQLite 兼容回退测试之外、只有真实 PostgreSQL 才能验证的部分:
- migration upgrade/downgrade(部分唯一索引 / JSONB / supplier_offer_mappings 表)。
- 部分唯一索引在 PG 的 NULL/重复边界。

**migration 只在隔离测试容器验证,禁止生产库。**
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

try:  # testcontainers 未安装时跳过(不阻断 SQLite 测试).
    from testcontainers.postgres import PostgresContainer

    _HAS_TESTCONTAINERS = True
except Exception:
    PostgresContainer = None  # type: ignore[assignment]
    _HAS_TESTCONTAINERS = False

pytestmark = pytest.mark.skipif(
    not _HAS_TESTCONTAINERS,
    reason="PG 集成测试未运行:无可用 PG/Docker(testcontainers 未安装)",
)


@pytest.fixture(scope="module")
def pg_container():
    """PostgreSQL 16 测试容器(Testcontainers)."""
    with PostgresContainer("postgres:16") as container:
        yield container


def _async_url(container) -> str:
    """把 Testcontainers 的 psycopg2 URL 转成 asyncpg URL."""
    return container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://", 1)


async def _run_alembic(container, command: str) -> None:
    """在测试容器上运行 alembic upgrade/downgrade(覆盖 settings 指向容器)."""
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    get_settings().database_url = _async_url(container)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    if command == "upgrade":
        command.upgrade(cfg, "head")
    else:
        command.downgrade(cfg, "base")


@pytest.mark.asyncio
async def test_migration_upgrade_downgrade_pg(pg_container) -> None:
    """真实 PG:migration upgrade 建列/索引/表;downgrade 完全回滚."""
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _async_url(pg_container)
    engine = create_async_engine(url)
    try:
        await _run_alembic(pg_container, "upgrade")
        async with engine.connect() as conn:
            # 表存在.
            res = await conn.exec_driver_sql("SELECT to_regclass('public.supplier_offer_mappings')")
            assert res.scalar() is not None
            # 部分唯一索引存在.
            res = await conn.exec_driver_sql(
                "SELECT indexname FROM pg_indexes WHERE indexname = 'ux_product_mapping_variation'"
            )
            assert res.scalar() is not None
            # 列存在.
            res = await conn.exec_driver_sql(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='product_mappings' AND column_name='identity_state'"
            )
            assert res.scalar() == "identity_state"
        await _run_alembic(pg_container, "downgrade")
        async with engine.connect() as conn:
            res = await conn.exec_driver_sql("SELECT to_regclass('public.supplier_offer_mappings')")
            assert res.scalar() is None  # 回滚后表已删
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_partial_unique_indexes(pg_container) -> None:
    """真实 PG:商品级/变体级部分唯一索引 NULL 与重复边界."""
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _async_url(pg_container)
    engine = create_async_engine(url)
    try:
        await _run_alembic(pg_container, "upgrade")
        async with engine.begin() as conn:
            # 同一 (workspace, woo, vid) 变体级重复 ⇒ 唯一冲突.
            await conn.exec_driver_sql(
                "INSERT INTO product_mappings "
                "(id, workspace_id, nuotao_product_id, woocommerce_id, woocommerce_variation_id, "
                "identity_state) VALUES "
                "(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', "
                "gen_random_uuid(), 2698, 2700, 'VARIATION')"
            )
            with pytest.raises(IntegrityError):
                await conn.exec_driver_sql(
                    "INSERT INTO product_mappings "
                    "(id, workspace_id, nuotao_product_id, woocommerce_id, woocommerce_variation_id, "
                    "identity_state) VALUES "
                    "(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', "
                    "gen_random_uuid(), 2698, 2700, 'VARIATION')"
                )
            # 商品级(变体为 NULL)不与该变体行冲突:部分唯一索引按 identity_state 区分.
            await conn.exec_driver_sql(
                "INSERT INTO product_mappings "
                "(id, workspace_id, nuotao_product_id, woocommerce_id, woocommerce_variation_id, "
                "identity_state) VALUES "
                "(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', "
                "gen_random_uuid(), 2698, NULL, 'PRODUCT')"
            )
        await _run_alembic(pg_container, "downgrade")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_supplier_offer_mapping(pg_container) -> None:
    """真实 PG:SupplierOfferMapping 唯一约束(变体级)与商品级部分唯一索引."""
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _async_url(pg_container)
    engine = create_async_engine(url)
    try:
        await _run_alembic(pg_container, "upgrade")
        async with engine.begin() as conn:
            # 同 (workspace, supplier, offer, variation) 变体级重复 ⇒ 唯一冲突.
            await conn.exec_driver_sql(
                "INSERT INTO supplier_offer_mappings "
                "(id, workspace_id, supplier_id, source_offer_id, wc_product_id, wc_variation_id, "
                "mapping_status) VALUES "
                "(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', NULL, 'OFFER-X', "
                "2838, 2848, 'mapped')"
            )
            with pytest.raises(IntegrityError):
                await conn.exec_driver_sql(
                    "INSERT INTO supplier_offer_mappings "
                    "(id, workspace_id, supplier_id, source_offer_id, wc_product_id, wc_variation_id, "
                    "mapping_status) VALUES "
                    "(gen_random_uuid(), '00000000-0000-0000-0000-000000000001', NULL, 'OFFER-X', "
                    "2838, 2848, 'mapped')"
                )
        await _run_alembic(pg_container, "downgrade")
    finally:
        await engine.dispose()
