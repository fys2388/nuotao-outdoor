"""创建系统设置和操作日志数据库表"""
import asyncio
from app.core.database import Base, _engine
from app.models.system_setting import SystemSetting
from app.models.operation_log import OperationLog

async def create_tables():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully")

if __name__ == "__main__":
    asyncio.run(create_tables())
