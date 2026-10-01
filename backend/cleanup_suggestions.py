#!/usr/bin/env python
"""一次性清理脚本：批量处理"收入对账失败"及"执行失败升级"建议。"""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, r"E:\AI\nuotao-ai-os\backend")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///E:/AI/nuotao-ai-os/_local_dev.db"

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.agent_suggestion import AgentSuggestion

TARGET_STATUSES = ("pending_approval", "approved", "executing", "failed")


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 查询所有建议
        all_stmt = select(AgentSuggestion).order_by(AgentSuggestion.id.asc())
        result = await session.execute(all_stmt)
        all_suggestions = list(result.scalars().all())
        print(f"DB total suggestions: {len(all_suggestions)}")

        # 找出收入对账/升级相关的
        related = [
            s for s in all_suggestions
            if ("收入对账失败" in (s.title or "")
                or "执行失败升级" in (s.title or "")
                or "investigate_revenue" in (s.execution_action or ""))
        ]
        print(f"Revenue gap related: {len(related)}")

        if related:
            for s in related:
                print(f"  ID={s.id} status={s.status} action={s.execution_action} title={s.title[:80]}")

        # 筛选可更新的
        updateable = [s for s in related if s.status in TARGET_STATUSES]
        print(f"Updatable: {len(updateable)}/{len(related)}")

        if updateable:
            ids = [s.id for s in updateable]
            from datetime import UTC, datetime
            now = datetime.now(UTC)

            await session.execute(
                update(AgentSuggestion)
                .where(AgentSuggestion.id.in_(ids))
                .values(
                    status="skipped",
                    approval_comment="Revenue gap: execution action fixed, old failed suggestions archived",
                    approved_at=now,
                )
            )
            await session.commit()
            print(f"Updated {len(ids)} suggestions to skipped")

            # verify
            verify = await session.execute(
                select(AgentSuggestion).where(
                    AgentSuggestion.id.in_(ids),
                    AgentSuggestion.status == "skipped"
                )
            )
            print(f"Verified: {len(list(verify.scalars().all()))}/{len(ids)}")
        else:
            print("Nothing to update.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
