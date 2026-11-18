"""受控数据维护脚本：标记两条测试 Lead（APR-M440-DATA-001）。

Owner 批准范围（reports/b2b/M441_INSTRUCTION_FROM_CHATGPT.md）：
- 仅 LD-20261117-6B43B6、LD-20261117-3ECF02 两条记录；
- 只写 ``is_test = true``，不得修改其他字段、不得删除记录；
- 命中数不是 2 立即中止，不写库；
- 审计：写 append-only event_log（actor / reason / approval_id / trace_id）；
- 只读复核：更新后核对两条记录，并验证经营统计已排除它们。

用法::

    cd backend && python scripts/mark_test_leads_m440.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models.b2b_leads import B2BLead
from app.services import event_service

REFERENCE_NUMBERS = ("LD-20261117-6B43B6", "LD-20261117-3ECF02")
ACTOR = "dsh-agent"
REASON = "M4.3 测试数据；排除出经营统计与报表"
APPROVAL_ID = "APR-M440-DATA-001"
EVENT_TYPE = "b2b_lead.test_flagged"
# 一次性、可追溯的执行标识（写入 event_log.payload，便于对账）
RUN_ID = "APR-M440-DATA-001-run-0086"


async def _flag(dry_run: bool) -> int:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(B2BLead).where(
                        B2BLead.reference_number.in_(REFERENCE_NUMBERS)
                    )
                )
            ).scalars()
        ).all()
        leads = sorted(rows, key=lambda r: r.reference_number)
        matched = len(leads)
        print(f"[1] matched_count={matched} expected=2")
        if matched != 2:
            found = [r.reference_number for r in leads]
            print(f"ABORT: 命中数不是 2（实际 {found}），不写库。")
            return 2

        changed = 0
        for lead in leads:
            print(
                f"[2] {lead.reference_number} id={lead.id} "
                f"status={lead.status} is_test={lead.is_test}"
            )
            if not dry_run and lead.is_test is not True:
                lead.is_test = True
                changed += 1

        if dry_run:
            print("[3] DRY-RUN：未写库。")
            return 0

        workspace_id = leads[0].workspace_id
        for lead in leads:
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type=EVENT_TYPE,
                entity_type="b2b_lead",
                entity_id=str(lead.id),
                payload={
                    "reference_number": lead.reference_number,
                    "actor": ACTOR,
                    "reason": REASON,
                    "approval_id": APPROVAL_ID,
                    "run_id": RUN_ID,
                    "is_test": True,
                },
                commit=False,
            )
        await session.commit()
        print(
            f"[3] committed：is_test 更新 {changed} 条；"
            f"event_log 写入 {len(leads)} 条（{EVENT_TYPE}）"
        )

    # 复核（独立会话，读已提交结果）
    async with async_session_factory() as session:
        flagged = (
            await session.execute(
                select(B2BLead.reference_number, B2BLead.is_test).where(
                    B2BLead.reference_number.in_(REFERENCE_NUMBERS)
                )
            )
        ).all()
        for reference_number, is_test in flagged:
            print(f"[4] verify {reference_number} is_test={is_test}")

        total = (
            await session.execute(select(func.count()).select_from(B2BLead))
        ).scalar_one()
        valid = (
            await session.execute(
                select(func.count())
                .select_from(B2BLead)
                .where(
                    (B2BLead.is_test.is_(False)) | (B2BLead.is_test.is_(None)),
                    B2BLead.status != "spam",
                )
            )
        ).scalar_one()
        print(
            f"[5] 统计复核：lead_total={total} valid_leads={valid} "
            f"已排除={total - valid}"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="只打印命中情况，不写库"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_flag(args.dry_run)))


if __name__ == "__main__":
    main()
