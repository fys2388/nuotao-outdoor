#!/usr/bin/env python3
"""
Deploy code fix + cleanup failed suggestions on production server.
"""

import sys
import asyncio

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SERVER_HOST = "95.217.218.178"
SERVER_USER = "root"
SSH_KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"
REMOTE_BACKEND = "/opt/nuotao/backend"
REMOTE_VENV = REMOTE_BACKEND + "/.venv/bin/python"


def ssh_exec(ssh, cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    return out + ("\n[stderr]\n" + err if err else "")


async def main():
    import paramiko

    print("=" * 60)
    print("Nuotao AI OS - Revenue Reconciliation Fix")
    print("=" * 60)

    # 1. SSH
    print("\n[1/4] Connecting to " + SERVER_HOST + " ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=SERVER_HOST, username=SERVER_USER, key_filename=SSH_KEY, timeout=15)
    except Exception as e:
        print("[FAIL] SSH connect failed: " + str(e))
        return
    print("[OK] Connected")

    # 2. Deploy code fix
    print("\n[2/4] Deploying code fix ...")

    # Fix daily_agents.py
    check1 = ssh_exec(ssh, "grep -c 'investigate_revenue_gap' " + REMOTE_BACKEND + "/app/tasks/daily_agents.py")
    if check1.strip().startswith("1"):
        print("[PATCH] Fixing daily_agents.py ...")
        p1 = (
            "cd " + REMOTE_BACKEND +
            " && cp app/tasks/daily_agents.py app/tasks/daily_agents.py.bak"
            " && sed -i 's/execution_action=\"investigate_revenue_gap\"/execution_action=\"manual_review\"/' app/tasks/daily_agents.py"
            " && echo DONE"
            " && grep -n 'manual_review\|investigate_revenue' app/tasks/daily_agents.py | head -5"
        )
        print(ssh_exec(ssh, p1, timeout=30))
    else:
        print("[OK] daily_agents.py already fixed")

    # Fix execution_router.py
    check2 = ssh_exec(ssh, "grep -c 'investigate_revenue_gap' " + REMOTE_BACKEND + "/app/services/execution_router.py")
    if check2.strip().startswith("1"):
        print("[PATCH] Fixing execution_router.py ...")
        p2 = (
            "cd " + REMOTE_BACKEND +
            " && cp app/services/execution_router.py app/services/execution_router.py.bak"
            " && sed -i '/\"investigate_revenue_gap\"/d' app/services/execution_router.py"
            " && echo DONE"
            " && grep -n 'ACTION_ALIASES\|investigate\|manual_review' app/services/execution_router.py | head -10"
        )
        print(ssh_exec(ssh, p2, timeout=30))
    else:
        print("[OK] execution_router.py already fixed")

    # 3. Run data cleanup
    print("\n[3/4] Running data cleanup ...")

    cleanup_script = r'''
import asyncio, os, sys
from datetime import datetime, timezone

sys.path.insert(0, "/opt/nuotao/backend")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nuotao:s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09@localhost:5432/nuotao")

from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.agent_suggestion import AgentSuggestion

TARGET_STATUSES = ("pending_approval", "approved", "executing", "failed")

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        stmt = select(AgentSuggestion).where(
            or_(
                AgentSuggestion.title.contains("收入对账失败"),
                AgentSuggestion.title.contains("执行失败升级"),
            )
        ).order_by(AgentSuggestion.id.asc())

        result = await session.execute(stmt)
        related = list(result.scalars().all())

        print("=== Cleanup Report ===")
        print("Total revenue-gap related suggestions: " + str(len(related)))

        if not related:
            print("No related suggestions found. Done.")
            await engine.dispose()
            return

        by_status = {}
        by_title = {}
        for s in related:
            by_status[s.status] = by_status.get(s.status, 0) + 1
            t = s.title[:60]
            by_title[t] = by_title.get(t, 0) + 1

        print("By status: " + str(by_status))
        print("\nBy title:")
        for t, c in by_title.items():
            print("  [" + str(c) + "] " + t)

        updateable = [s for s in related if s.status in TARGET_STATUSES]
        terminal = [s for s in related if s.status not in TARGET_STATUSES]
        print("\nUpdatable: " + str(len(updateable)) + ", Terminal: " + str(len(terminal)))

        if updateable:
            ids = [s.id for s in updateable]
            now = datetime.now(timezone.utc)
            await session.execute(
                update(AgentSuggestion)
                .where(AgentSuggestion.id.in_(ids))
                .values(
                    status="skipped",
                    approval_comment="Revenue gap: execution action fixed to manual_review, old failed suggestions archived",
                    approved_at=now,
                )
            )
            await session.commit()

            verify = await session.execute(
                select(AgentSuggestion).where(
                    AgentSuggestion.id.in_(ids),
                    AgentSuggestion.status == "skipped"
                )
            )
            verified = len(list(verify.scalars().all()))
            print("\n=== DONE ===")
            print("Updated " + str(len(ids)) + " suggestions to skipped")
            print("Verified: " + str(verified) + "/" + str(len(ids)))
            print("IDs: " + ", ".join(str(i) for i in sorted(ids)))
        else:
            print("\nNo updates needed - all related suggestions are in terminal state.")

    await engine.dispose()

asyncio.run(main())
'''

    script_path = "/tmp/nuotao_cleanup.py"
    ssh_exec(ssh, "cat > " + script_path + " << 'ENDOFSCRIPT'\n" + cleanup_script + "\nENDOFSCRIPT", timeout=15)
    output = ssh_exec(ssh, "cd " + REMOTE_BACKEND + " && " + REMOTE_VENV + " " + script_path + " 2>&1", timeout=120)
    print(output)
    ssh_exec(ssh, "rm -f " + script_path, timeout=10)

    # 4. Restart backend
    print("\n[4/4] Restarting backend service ...")
    restart_out = ssh_exec(ssh, "systemctl restart nuotao-backend 2>&1 && sleep 2 && systemctl is-active nuotao-backend", timeout=30)
    print(restart_out)

    ssh.close()
    print("\n" + "=" * 60)
    print("All done!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
