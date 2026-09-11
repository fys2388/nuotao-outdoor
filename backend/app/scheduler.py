"""调度器兼容入口：`python -m app.scheduler`。

等价于 `python -m app.services.agent_scheduler`。
历史文档（docs/M5.11_BUSINESS_ENVIRONMENT_SETUP.md、docs/development.md）
使用 `python -m app.scheduler`，本入口消除命令不一致。
"""

from __future__ import annotations

import asyncio

from app.services.agent_scheduler import main

if __name__ == "__main__":
    asyncio.run(main())
