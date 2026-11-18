"""PII 字段回填脚本（APR-M440-PII-001，仅 Staging 验证；生产不执行）。

Owner 边界：本脚本**禁止**在生产运行（未获批准）。在 Staging 服务器执行：

    cd /opt/nuotao/staging/backend
    PII_HMAC_KEY=<staging-test-hmac> PII_ENCRYPTION_KEY=<base64-32B> \\
        .venv/bin/python scripts/backfill_pii_fields_m440.py [--dry-run]

行为：
- 对 ``b2b_leads`` 中 email/contact_name 非空的记录写
  ``email_hash`` / ``email_encrypted`` / ``contact_name_encrypted`` / ``pii_key_version``；
- 只读对账：解密 ``email_encrypted`` 与原文比对；
- 写 append-only ``b2b_lead.pii_backfill`` 审计事件；
- email_hash 唯一冲突：跳过并记录（不覆盖既有记录）；
- ``--dry-run`` 只打印，不写库。
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.pii_crypto import (
    PiiCryptoError,
    build_email_hash,
    decrypt_field,
    encrypt_field,
)
from app.models.b2b_leads import B2BLead
from app.services import event_service

RUN_ID = "APR-M440-PII-001-staging-backfill"
EVENT_TYPE = "b2b_lead.pii_backfill"


async def _backfill(dry_run: bool) -> int:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(B2BLead).where(
                        (B2BLead.email.isnot(None))
                        | (B2BLead.contact_name.isnot(None))
                    )
                )
            ).scalars()
        ).all()
        print(f"[1] rows_to_backfill={len(rows)}")
        filled = skipped = conflicts = 0
        for lead in rows:
            email = (lead.email or "").strip()
            name = (lead.contact_name or "").strip()
            try:
                if email:
                    h = build_email_hash(email, workspace_id=str(lead.workspace_id))
                    dup = (
                        await session.execute(
                            select(B2BLead.id).where(
                                B2BLead.email_hash == h, B2BLead.id != lead.id
                            )
                        )
                    ).first()
                    if dup is not None:
                        conflicts += 1
                        print(
                            f"  [conflict] {lead.reference_number} email_hash 已存在于 "
                            f"{dup[0]} — 跳过（不覆盖）"
                        )
                        continue
                    lead.email_hash = h
                    lead.email_encrypted = encrypt_field(email)
                if name:
                    lead.contact_name_encrypted = encrypt_field(name)
                lead.pii_key_version = "v1"
                filled += 1
                print(
                    f"  [fill] {lead.reference_number} email={bool(email)} "
                    f"name={bool(name)}"
                )
            except PiiCryptoError as exc:
                skipped += 1
                print(f"  [skip] {lead.reference_number}: {exc}")

        if dry_run:
            print(
                f"[2] DRY-RUN：未写库（filled={filled} skipped={skipped} "
                f"conflicts={conflicts}）"
            )
            return 0

        for lead in rows:
            if lead.pii_key_version:
                await event_service.create_event(
                    session,
                    workspace_id=lead.workspace_id,
                    event_type=EVENT_TYPE,
                    entity_type="b2b_lead",
                    entity_id=str(lead.id),
                    payload={
                        "run_id": RUN_ID,
                        "filled": lead.email_hash is not None,
                        "key_version": lead.pii_key_version,
                    },
                    commit=False,
                )
        await session.commit()
        print(
            f"[2] committed（filled={filled} skipped={skipped} "
            f"conflicts={conflicts}，审计事件 {EVENT_TYPE}）"
        )

    # 对账（独立会话，读已提交结果）
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(B2BLead).where(B2BLead.email_encrypted.isnot(None))
                )
            ).scalars()
        ).all()
        ok = fail = 0
        for lead in rows:
            try:
                if decrypt_field(lead.email_encrypted) != (lead.email or "").strip():
                    fail += 1
                    print(f"  [recon-fail] {lead.reference_number}")
                else:
                    ok += 1
            except PiiCryptoError:
                fail += 1
                print(f"  [recon-error] {lead.reference_number}")
        print(f"[3] 对账：ok={ok} fail={fail}")
        return 0 if fail == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="只打印命中情况，不写库"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_backfill(args.dry_run)))


if __name__ == "__main__":
    main()
