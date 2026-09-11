r"""M5.7 Phase 0 Production Readiness Gate.

Checks the runtime prerequisites before any real Product Analyst pilot:

    1.  Alembic head (code-side)
    2.  pytest / ruff toolchain presence
    3.  PostgreSQL reachable + migration at head
    4.  Redis reachable
    5.  Worker importable
    6.  Scheduler importable
    7.  product_analyst agent active
    8.  AGENT_PRODUCT_ANALYST prompt has an active version
    9.  execution policy configured
    10. budget policy configured
    11. retry policy configured
    12. approval RBAC roles configured
    13. approval SLA configured
    14. console/API audit path (event_log) writable
    15. OpenAI / DeepSeek keys configured (presence only - never printed)

Every BLOCKED item is reported explicitly; nothing is fabricated. API keys
are never written to DB / event_log / trace / prompt / console / logs.

Usage (from ``backend``):

    .venv\Scripts\python -m app.pilot.readiness --workspace <ws>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import setup_logging

# Item ids in stable order (the M5.7 Phase 0 checklist).
CHECK_IDS = [
    "alembic_head",
    "toolchain",
    "postgres_migration",
    "redis",
    "worker",
    "scheduler",
    "agent_active",
    "prompt_active",
    "execution_policy",
    "budget_policy",
    "retry_policy",
    "approval_rbac",
    "approval_sla",
    "audit",
    "llm_keys",
]


def _alembic_heads() -> list[str]:
    """Read migration heads from the local scripts (no DB needed)."""
    import os

    from alembic.script import ScriptDirectory

    location = os.path.join(os.getcwd(), "alembic")
    script = ScriptDirectory(location)
    return sorted(script.get_heads())


def _check_alembic_head() -> dict:
    try:
        heads = _alembic_heads()
        return {"status": "PASS", "detail": ",".join(heads), "heads": heads}
    except Exception as exc:
        return {"status": "BLOCKED", "detail": f"cannot resolve alembic heads: {exc}"}


def _check_toolchain() -> dict:
    """Presence of the quality gate configuration (pytest/ruff run separately)."""
    import os

    missing = [name for name in ("pyproject.toml", "alembic.ini") if not os.path.exists(name)]
    if missing:
        return {"status": "BLOCKED", "detail": f"missing files: {', '.join(missing)}"}
    return {
        "status": "PASS",
        "detail": "pyproject.toml (pytest/ruff) + alembic.ini present; run gates separately",
    }


async def _db_checks(workspace_id: UUID) -> dict:
    """DB-dependent checks (3, 7-14). Requires a reachable PostgreSQL."""
    settings = get_settings()
    engine = None
    try:
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # 3. migration current vs head
            version = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
            heads = _alembic_heads()
            migration = (
                {"status": "PASS", "detail": f"at {version}"}
                if version in heads
                else {
                    "status": "BLOCKED",
                    "detail": f"db at {version}, expected one of {heads}",
                }
            )

            # 7. product_analyst agent active

            agent_row = (
                await session.execute(
                    text(
                        "SELECT id, agent_id, status FROM agents "
                        "WHERE workspace_id = :ws AND agent_id = 'product_analyst'"
                    ),
                    {"ws": str(workspace_id)},
                )
            ).first()
            agent_active = (
                {
                    "status": "PASS",
                    "detail": f"status={agent_row[2]}",
                }
                if agent_row and agent_row[2] == "active"
                else {"status": "BLOCKED", "detail": "product_analyst agent missing/inactive"}
            )

            # 8. AGENT_PRODUCT_ANALYST prompt active version
            from app.services import prompt_registry

            try:
                prompt = await prompt_registry.get_active_prompt(
                    session, workspace_id=workspace_id, name="AGENT_PRODUCT_ANALYST"
                )
                prompt_active = {
                    "status": "PASS",
                    "detail": f"version={prompt.version}",
                }
            except Exception as exc:
                prompt_active = {"status": "BLOCKED", "detail": str(exc)[:200]}

            # 9-11. policies (execution/budget are agent-scoped)
            from app.services import agent_policies

            agent_uuid = str(agent_row[0]) if agent_row else None
            policy_checks = {}
            for label, getter in (
                ("execution_policy", agent_policies.get_execution_policy),
                ("budget_policy", agent_policies.get_budget_policy),
            ):
                if agent_uuid is None:
                    policy_checks[label] = {
                        "status": "BLOCKED",
                        "detail": "product_analyst agent missing",
                    }
                    continue
                try:
                    policy = await getter(
                        session, workspace_id=workspace_id, agent_id=UUID(agent_uuid)
                    )
                    policy_checks[label] = (
                        {"status": "PASS", "detail": "configured"}
                        if policy is not None
                        else {"status": "BLOCKED", "detail": "no policy row"}
                    )
                except Exception as exc:
                    policy_checks[label] = {"status": "BLOCKED", "detail": str(exc)[:200]}
            try:
                policy = await agent_policies.get_retry_policy(session, workspace_id=workspace_id)
                policy_checks["retry_policy"] = (
                    {"status": "PASS", "detail": "configured"}
                    if policy is not None
                    else {"status": "BLOCKED", "detail": "no policy row"}
                )
            except Exception as exc:
                policy_checks["retry_policy"] = {"status": "BLOCKED", "detail": str(exc)[:200]}

            # 12. approval RBAC roles
            from app.services import approval_rbac

            try:
                roles = await approval_rbac.list_roles(session, workspace_id=workspace_id)
                rbac = (
                    {"status": "PASS", "detail": f"{len(roles)} role(s)"}
                    if roles
                    else {"status": "BLOCKED", "detail": "no approval roles configured"}
                )
            except Exception as exc:
                rbac = {"status": "BLOCKED", "detail": str(exc)[:200]}

            # 13. approval SLA

            sla_rows = (
                await session.execute(
                    text(
                        "SELECT approval_type, enabled FROM agent_approval_slas "
                        "WHERE workspace_id = :ws"
                    ),
                    {"ws": str(workspace_id)},
                )
            ).all()
            enabled = [r[0] for r in sla_rows if r[1]]
            sla = (
                {
                    "status": "PASS",
                    "detail": f"{len(enabled)} enabled SLA(s): {','.join(sorted(enabled))}",
                }
                if enabled
                else {
                    "status": "PASS",
                    "detail": "no rows; config-driven defaults apply",
                }
            )

            # 14. audit path: event_log writable
            from app.services import event_service

            try:
                await event_service.create_event(
                    session,
                    workspace_id=workspace_id,
                    event_type="agent.runtime.readiness_checked",
                    entity_type="runtime",
                    entity_id=str(workspace_id),
                    payload={"gate": "M5.7-phase0"},
                    trace_id=f"readiness-{workspace_id}",
                )
                await session.flush()
                audit = {"status": "PASS", "detail": "event_log writable"}
            except Exception as exc:
                audit = {"status": "BLOCKED", "detail": f"event_log write failed: {exc}"[:200]}

            return {
                "postgres_migration": migration,
                "agent_active": agent_active,
                "prompt_active": prompt_active,
                **policy_checks,
                "approval_rbac": rbac,
                "approval_sla": sla,
                "audit": audit,
            }
    except Exception as exc:
        base = {"status": "BLOCKED", "detail": f"database unreachable: {str(exc)[:200]}"}
        return {
            "postgres_migration": base,
            "agent_active": base,
            "prompt_active": base,
            "execution_policy": base,
            "budget_policy": base,
            "retry_policy": base,
            "approval_rbac": base,
            "approval_sla": base,
            "audit": base,
        }
    finally:
        if engine is not None:
            await engine.dispose()


async def _check_redis() -> dict:
    import redis.asyncio as aioredis

    settings = get_settings()
    client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        pong = await client.ping()
        return {"status": "PASS" if pong else "BLOCKED", "detail": "pong"}
    except Exception as exc:
        return {"status": "BLOCKED", "detail": f"redis unreachable: {str(exc)[:200]}"}
    finally:
        await client.aclose()


def _check_importable(module: str) -> dict:
    import importlib

    try:
        importlib.import_module(module)
        return {"status": "PASS", "detail": f"{module} importable"}
    except Exception as exc:
        return {"status": "BLOCKED", "detail": f"{module} import failed: {str(exc)[:200]}"}


def _check_llm_keys() -> dict:
    settings = get_settings()
    providers = (
        ("openai", settings.openai_api_key),
        ("deepseek", settings.deepseek_api_key),
    )
    present = [name for name, value in providers if value]
    missing = [name for name, value in providers if not value]
    if present and not missing:
        return {"status": "PASS", "detail": "both providers configured (presence only)"}
    return {
        "status": "BLOCKED",
        "detail": f"configured: {', '.join(present) or 'none'}; missing: {', '.join(missing)}",
    }


async def run_checks(workspace_id: UUID) -> dict:
    checks = {
        "alembic_head": _check_alembic_head(),
        "toolchain": _check_toolchain(),
        "redis": await _check_redis(),
        "worker": _check_importable("app.worker.agent_worker"),
        "scheduler": _check_importable("app.services.alert_scheduler"),
        "llm_keys": _check_llm_keys(),
    }
    db_checks = await _db_checks(workspace_id)
    checks.update(db_checks)
    # stable ordering
    ordered = {check_id: checks[check_id] for check_id in CHECK_IDS}
    blocked = [cid for cid, c in ordered.items() if c.get("status") == "BLOCKED"]
    return {
        "workspace_id": str(workspace_id),
        "checks": ordered,
        "blocked": blocked,
        "overall": "READY" if not blocked else "NOT_READY",
    }


async def _run(args: argparse.Namespace) -> int:
    result = await run_checks(UUID(args.workspace))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if args.verbose:
        for check_id, check in result["checks"].items():
            print(f"{check_id}: {check['status']} - {check.get('detail')}")
    return 0 if result["overall"] == "READY" else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.pilot.readiness")
    parser.add_argument("--workspace", required=True, help="workspace UUID")
    parser.add_argument("--verbose", action="store_true", help="print one line per check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
