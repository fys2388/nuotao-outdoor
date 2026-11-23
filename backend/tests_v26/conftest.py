"""M4 V2.6 独立测试配置(避开共享 conftest 的依赖版本冲突).

共享 ``tests/conftest.py`` 顶层导入 ``app.api.v1.endpoints.auth``,在
starlette 1.6 + slowapi 0.1.10 环境触发 ``Config._read_file`` 签名不兼容而崩溃
(与本次改动无关,预存环境问题)。本 conftest 只提供 V2.6 测试所需的
db_engine / db_session(内存 SQLite),不导入 app.api,因此可在当前环境运行。

**不影响正式交付**:``backend/tests/test_identity_model_v26.py`` 仍是交付文件
(供 CI 在正确依赖版本下运行);``tests_v26`` 仅用于本机隔离验证。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base


@pytest.fixture()
async def db_engine():
    """In-memory SQLite engine with all V2.6 models created (no external deps)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def db_session(db_engine):
    """Async session bound to the in-memory SQLite database."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
