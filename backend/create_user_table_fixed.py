"""创建用户表脚本（修复版）"""
import asyncio
import sys

sys.path.insert(0, '.')

from sqlalchemy import text
from app.core.database import Base, _engine
from app.models.user import User  # 显式导入 User 模型

async def create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print('✅ 表创建完成')

    async with _engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name = 'users'"))
        row = result.fetchone()
        if row:
            print(f'✅ 验证: users 表存在 - {row[0]}')
        else:
            print('❌ 验证: users 表不存在')

asyncio.run(create_tables())
