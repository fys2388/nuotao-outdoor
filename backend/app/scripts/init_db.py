"""初始化数据库：执行迁移 + 创建默认管理员用户。

用法：
    python -m app.scripts.init_db
"""

from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import text

from app.core.database import async_session_factory
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.services.user_db_service import ensure_default_admin_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    print("=" * 60)
    print("Nuotao AI OS 数据库初始化")
    print("=" * 60)

    # Step 1: 检查数据库连接
    print("\n🔍 检查数据库连接...")
    try:
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            print("✅ 数据库连接成功")
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        print("\n请检查：")
        print("  1. PostgreSQL 服务是否运行")
        print("  2. .env 中的 DATABASE_URL 是否正确")
        print("  3. 用户名和密码是否正确")
        sys.exit(1)

    # Step 2: 创建默认管理员用户
    print("\n👤 检查默认管理员用户...")
    try:
        async with async_session_factory() as session:
            admin = await ensure_default_admin_db(session)
            await session.commit()
            print(f"✅ 管理员用户: {admin.username} ({admin.email})")
            print(f"   角色: {admin.role}")
            print(f"   ID: {admin.id}")
    except Exception as e:
        print(f"❌ 创建管理员失败: {e}")
        sys.exit(1)

    # Step 3: 检查 workspace
    print("\n🏢 检查工作空间...")
    try:
        async with async_session_factory() as session:
            # 确保 workspace 存在
            result = await session.execute(
                text("SELECT id FROM workspaces WHERE id = :id"),
                {"id": DEFAULT_WORKSPACE_ID},
            )
            if result.scalar_one_or_none():
                print(f"✅ 默认工作空间已存在: {DEFAULT_WORKSPACE_ID}")
            else:
                print(f"⚠️  默认工作空间不存在: {DEFAULT_WORKSPACE_ID}")
                print("   请运行: alembic upgrade head")
    except Exception as e:
        print(f"⚠️  检查工作空间失败: {e}")

    # Step 4: 显示摘要
    print("\n" + "=" * 60)
    print("✅ 初始化完成！")
    print("=" * 60)
    print(f"\n管理员账号: admin / Admin@2026")
    print(f"API 地址: http://localhost:8012/api/v1")
    print(f"\n下一步：")
    print("  1. 启动后端服务: uvicorn app.main:app --reload --port 8012")
    print("  2. 登录测试: curl -X POST http://localhost:8012/api/v1/auth/login -d 'username=admin&password=Admin@2026'")
    print("  3. 执行迁移: alembic upgrade head")
    print("  4. 运行选品流程: python -m app.scripts.run_selection_to_listing --dry-run")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n已中断")
        sys.exit(1)
    except Exception as exc:
        logger.exception("初始化失败: %s", exc)
        sys.exit(1)
