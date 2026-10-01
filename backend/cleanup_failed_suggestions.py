#!/usr/bin/env python3
"""
一次性清理脚本：批量处理"收入对账失败"及"执行失败升级"建议。

用法（在生产服务器上执行）：
    cd /opt/nuotao/backend
    python cleanup_failed_suggestions.py

或者从本地通过 SSH 执行：
    python cleanup_failed_suggestions.py  # 自动 SSH 到生产服务器执行

已完成的代码修复：
    1. daily_agents.py: execution_action 从 "investigate_revenue_gap" 改为 "manual_review"
    2. execution_router.py: 移除 "investigate_revenue_gap" -> "generate_marketing_content" 别名映射
"""

import asyncio
import os
import sys
import textwrap

# 生产服务器配置
SERVER_HOST = "95.217.218.178"
SERVER_USER = "root"
SSH_KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"
REMOTE_BACKEND = "/opt/nuotao/backend"
REMOTE_VENV = f"{REMOTE_BACKEND}/.venv/bin/python"


# =============================================================================
# 远程执行模式（默认）
# =============================================================================
REMOTE_SCRIPT = r"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, '/opt/nuotao/backend')
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://nuotao:s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09@localhost:5432/nuotao')

from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.agent_suggestion import AgentSuggestion

TARGET_STATUSES = ("pending_approval", "approved", "executing", "failed")

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. 查询所有收入对账/升级相关建议
        stmt = select(AgentSuggestion).where(
            or_(
                AgentSuggestion.title.contains("收入对账失败"),
                AgentSuggestion.title.contains("执行失败升级"),
            )
        ).order_by(AgentSuggestion.id.asc())

        result = await session.execute(stmt)
        related = list(result.scalars().all())

        print(f"=== 清理报告 ===")
        print(f"收入对账/升级相关建议总数: {len(related)}")

        if not related:
            print("未找到相关建议，退出。")
            await engine.dispose()
            return

        # 2. 按状态分布
        by_status = {}
        by_title = {}
        for s in related:
            by_status[s.status] = by_status.get(s.status, 0) + 1
            by_title[s.title[:50]] = by_title.get(s.title[:50], 0) + 1

        print(f"按状态分布: {by_status}")
        print(f"按标题分布:")
        for title, count in by_title.items():
            print(f"  [{count}条] {title}")

        # 3. 筛选可更新状态的
        updateable = [s for s in related if s.status in TARGET_STATUSES]
        already_terminal = [s for s in related if s.status not in TARGET_STATUSES]
        print(f"\n可更新: {len(updateable)} 条, 已是终态: {len(already_terminal)} 条")

        if not updateable:
            print("无需更新，所有相关建议已是终态。")
            await engine.dispose()
            return

        # 4. 批量更新为 skipped
        ids = [s.id for s in updateable]
        now = datetime.now(timezone.utc)

        await session.execute(
            update(AgentSuggestion)
            .where(AgentSuggestion.id.in_(ids))
            .values(
                status="skipped",
                approval_comment="收入对账缺口：执行动作已修复(改用manual_review)，旧的失败升级建议已归档",
                approved_at=now,
            )
        )
        await session.commit()

        # 5. 验证
        verify = await session.execute(
            select(AgentSuggestion).where(
                AgentSuggestion.id.in_(ids),
                AgentSuggestion.status == "skipped"
            )
        )
        verified_count = len(list(verify.scalars().all()))

        print(f"\n=== 完成 ===")
        print(f"已更新 {len(ids)} 条建议为 skipped")
        print(f"验证: {verified_count}/{len(ids)} 条状态已确认")
        print(f"\n建议ID列表: {', '.join(str(i) for i in ids[:20])}{'...' if len(ids) > 20 else ''}")

    await engine.dispose()

asyncio.run(main())
"""


async def run_remote_cleanup():
    """通过 SSH 在生产服务器上执行清理脚本。"""
    try:
        import paramiko
    except ImportError:
        print("paramiko 未安装，请先运行: pip install paramiko")
        return

    print(f"正在通过 SSH 连接到 {SERVER_HOST} ...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=SERVER_HOST,
            username=SERVER_USER,
            key_filename=SSH_KEY,
            timeout=15,
        )
        print(f"✅ 已连接到 {SERVER_HOST}")
    except Exception as e:
        print(f"❌ SSH 连接失败: {e}")
        return

    # 先验证服务器上的代码是否已更新
    print("\n=== 检查服务器代码状态 ===")
    check_cmd = (
        f"grep -n 'investigate_revenue_gap' {REMOTE_BACKEND}/app/tasks/daily_agents.py "
        f"{REMOTE_BACKEND}/app/services/execution_router.py 2>/dev/null || echo 'NOT_FOUND'"
    )
    stdin, stdout, stderr = ssh.exec_command(check_cmd, timeout=15)
    check_output = stdout.read().decode()
    if "investigate_revenue_gap" in check_output:
        print(f"⚠️  服务器代码尚未更新! 请先部署新代码：\n{check_output}")
        print("\n=== 但先执行数据清理 ===")
    else:
        print("✅ 服务器代码已是最新版本")

    # 检查是否已有清理脚本
    deploy_cmd = f"cat > /tmp/cleanup_suggestions.py << 'ENDOFSCRIPT'\n{REMOTE_SCRIPT}\nENDOFSCRIPT"
    ssh.exec_command(deploy_cmd, timeout=15)
    stdout.read().decode()

    # 执行清理脚本
    print("\n=== 执行清理 ===")
    run_cmd = f"cd {REMOTE_BACKEND} && {REMOTE_VENV} /tmp/cleanup_suggestions.py 2>&1"
    stdin, stdout, stderr = ssh.exec_command(run_cmd, timeout=60)
    output = stdout.read().decode()
    err = stderr.read().decode()

    print(output)
    if err:
        print(f"[stderr] {err}")

    # 清理临时文件
    ssh.exec_command("rm -f /tmp/cleanup_suggestions.py", timeout=10)

    ssh.close()
    print("\n=== 远程清理完成 ===")


async def run_local_cleanup():
    """在本地直接连接数据库执行清理。"""
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://nuotao:s2o7bdFwAXB2DoaqIhpdakiSJTAj3U09@localhost:5432/nuotao",
    )

    from sqlalchemy import select, update, or_
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    sys.path.insert(0, r"E:\AI\nuotao-ai-os\backend")
    from app.models.agent_suggestion import AgentSuggestion

    TARGET_STATUSES = ("pending_approval", "approved", "executing", "failed")
    now = datetime.now(timezone.utc)

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

        print(f"=== 清理报告 ===")
        print(f"收入对账/升级相关建议总数: {len(related)}")

        if not related:
            print("未找到相关建议，退出。")
            await engine.dispose()
            return

        updateable = [s for s in related if s.status in TARGET_STATUSES]
        print(f"可更新: {len(updateable)} 条")

        if updateable:
            ids = [s.id for s in updateable]
            await session.execute(
                update(AgentSuggestion)
                .where(AgentSuggestion.id.in_(ids))
                .values(
                    status="skipped",
                    approval_comment="收入对账缺口：执行动作已修复，旧的失败升级建议已归档",
                    approved_at=now,
                )
            )
            await session.commit()
            print(f"✅ 已更新 {len(ids)} 条建议为 skipped")

    await engine.dispose()
    print("\n=== 完成 ===")


if __name__ == "__main__":
    print("请选择清理方式：")
    print("  1) SSH 到生产服务器执行（推荐）")
    print("  2) 直接连接本地数据库")
    print()

    try:
        choice = input("请输入 1 或 2（默认 1）: ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        choice = "1"

    if choice == "2":
        asyncio.run(run_local_cleanup())
    else:
        asyncio.run(run_remote_cleanup())
