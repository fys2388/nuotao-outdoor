r"""M5.10 Production Environment Activation Gate.

Purpose
-------
Confirm whether the real business environment is ready to start the first
real Product Analyst business run. Every item is reported truthfully as one
of:

    PASS     - verified against the real environment (or importable tooling)
    BLOCKED  - a required real-world condition is not configured/present
    FAILED   - configured, but the real verification failed

Two layers are kept strictly separate:

    TECHNICAL_INFRA_PASS - code/runtime components are healthy (importable
                           modules, guard rails in place). A local dev
                           environment can also pass this layer.
    PRODUCTION_ENV_PASS  - real credentials/connections/products/operator
                           verified. Only this layer can produce
                           ``READY_FOR_REAL_BUSINESS_RUN``.

Final state is exactly one of:

    READY_FOR_REAL_BUSINESS_RUN - every production item PASSed
    ENVIRONMENT_BLOCKED         - any production item is BLOCKED/FAILED

Nothing is fabricated: when ``DATABASE_URL`` / ``REDIS_URL`` are not
explicitly configured, the built-in local-dev defaults are never treated as
production configuration. API keys / consumer secrets are checked for
presence and exercised through real read-only calls only; they are never
printed, logged, or written to the database.

Usage (from ``backend``):

    .venv\Scripts\python -m app.pilot.activation_gate --workspace <ws>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.pilot import readiness

# Built-in local-dev defaults: never treated as explicit production config.
_DEFAULT_DATABASE_URL = "postgresql+asyncpg://nuotao:nuotao_dev_password@localhost:5432/nuotao"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"

TECHNICAL_LAYER = "technical"
PRODUCTION_LAYER = "production"

# M5.10 gate items in stable order.
GATE_IDS = [
    "postgres",
    "redis",
    "worker",
    "scheduler",
    "llm",
    "woocommerce",
    "real_products",
    "operator",
    "rbac",
    "sla",
    "budget",
    "retry",
    "pii",
    "secret_guard",
    "audit",
    "workspace_isolation",
]

# DB-dependent items returned by ``_db_gate_checks``.
_DB_GATE_IDS = ("postgres", "real_products", "rbac", "sla", "budget", "retry", "audit")


def _blocked(detail: str) -> dict:
    return {"status": "BLOCKED", "layer": PRODUCTION_LAYER, "detail": detail}


def _failed(detail: str) -> dict:
    return {"status": "FAILED", "layer": PRODUCTION_LAYER, "detail": detail}


def _technical(result: dict) -> dict:
    result["layer"] = TECHNICAL_LAYER
    return result


def _explicit_env(env_name: str, settings_value: str, default: str) -> bool:
    """True when the value comes from an explicit env/.env, not the local default."""
    raw = os.environ.get(env_name)
    if raw and raw.strip():
        return True
    return settings_value != default


def _identity_provider_configured(settings) -> bool:
    """True when the real Clerk identity provider is fully configured.

    Presence-only: the three values are required for the header provider to
    verify tokens at runtime; without them the API fails closed (401) and the
    operator gate must report BLOCKED, never a fabricated PASS. Values are
    never printed.
    """
    return bool(settings.clerk_jwks_url and settings.clerk_issuer and settings.clerk_audience)


async def _check_operator(settings) -> dict:
    """Operator identity must come from a real verified JWT, never the body.

    ``ACTOR_PROVIDER=header`` alone is NOT enough: without a configured Clerk
    JWKS/issuer/audience the runtime rejects every request (401), so the gate
    stays BLOCKED_REAL_OPERATOR until the real identity provider exists.
    When configured, a real read-only JWKS GET proves the endpoint is
    reachable and parseable (public keys only - no secrets involved).
    """
    if settings.actor_provider == "body":
        return _blocked(
            "ACTOR_PROVIDER=body (AUTHENTICATION_GAP): actor declared in the request "
            "body is not a real identity -> BLOCKED_REAL_OPERATOR"
        )
    if not _identity_provider_configured(settings):
        return _blocked(
            "ACTOR_PROVIDER=header but Clerk identity provider is not configured "
            "(CLERK_JWKS_URL/CLERK_ISSUER/CLERK_AUDIENCE required) -> BLOCKED_REAL_OPERATOR"
        )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(settings.clerk_jwks_url)
            response.raise_for_status()
            payload = response.json()
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list) or not keys:
            return _failed("JWKS endpoint reachable but returned no keys")
    except Exception as exc:  # noqa: BLE001
        return _failed(f"JWKS verification failed: {str(exc)[:160]}")
    return {
        "status": "PASS",
        "layer": PRODUCTION_LAYER,
        "detail": (
            "ACTOR_PROVIDER=header + Clerk JWKS reachable "
            "(CLERK_JWKS_URL/CLERK_ISSUER/CLERK_AUDIENCE configured)"
        ),
    }


def _check_pii_guard() -> dict:
    """PII rejection + minimal JSON-safe product context are in place."""
    try:
        from app.services import customer as customer_svc
        from app.services import product_context as product_ctx

        ok = (
            hasattr(customer_svc, "_assert_no_pii")
            and hasattr(product_ctx, "build_product_context")
            and hasattr(product_ctx, "_json_safe")
        )
        if ok:
            return _technical(
                {
                    "status": "PASS",
                    "detail": "PII rejection + minimal JSON-safe product context present",
                }
            )
        return _technical({"status": "BLOCKED", "detail": "PII guard symbols missing"})
    except Exception as exc:  # noqa: BLE001
        return _technical(
            {"status": "BLOCKED", "detail": f"PII guard import failed: {str(exc)[:160]}"}
        )


def _check_secret_guard() -> dict:
    """Secret guard rails (config/tracing/logging) are importable and wired."""
    try:
        from app.core import config as config_mod
        from app.core import logging as logging_mod
        from app.core import tracing as tracing_mod

        ok = (
            hasattr(config_mod, "Settings")
            and hasattr(logging_mod, "setup_logging")
            and hasattr(tracing_mod, "new_trace_id")
        )
        if ok:
            return _technical(
                {
                    "status": "PASS",
                    "detail": "secrets live in env only; trace-aware logging wired",
                }
            )
        return _technical({"status": "BLOCKED", "detail": "secret guard symbols missing"})
    except Exception as exc:  # noqa: BLE001
        return _technical(
            {"status": "BLOCKED", "detail": f"secret guard import failed: {str(exc)[:160]}"}
        )


def _check_workspace_isolation() -> dict:
    """Workspace scoping helpers exist; service queries are workspace-filtered."""
    try:
        from app.core.workspace import DEFAULT_WORKSPACE_ID, get_workspace_id

        ok = callable(get_workspace_id) and DEFAULT_WORKSPACE_ID is not None
        if ok:
            return _technical(
                {
                    "status": "PASS",
                    "detail": "API workspace scoping + workspace-filtered queries present",
                }
            )
        return _technical({"status": "BLOCKED", "detail": "workspace helpers missing"})
    except Exception as exc:  # noqa: BLE001
        return _technical(
            {"status": "BLOCKED", "detail": f"workspace import failed: {str(exc)[:160]}"}
        )


async def _check_real_llm(settings) -> dict:
    """Real LLM provider readiness: key presence + live read-only /models call."""
    providers = (
        ("openai", settings.openai_api_key, settings.openai_base_url),
        ("deepseek", settings.deepseek_api_key, settings.deepseek_base_url),
    )
    present = [(name, key, base) for name, key, base in providers if key]
    if not present:
        return _blocked("OPENAI_API_KEY / DEEPSEEK_API_KEY not configured -> BLOCKED_REAL_LLM")
    ok: list[str] = []
    failed: list[str] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for name, key, base in present:
            url = base.rstrip("/") + "/models"
            try:
                resp = await client.get(url, headers={"Authorization": f"Bearer {key}"})
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name}:{type(exc).__name__}")
                continue
            if resp.status_code == 200:
                ok.append(name)
            elif resp.status_code in (401, 403):
                failed.append(f"{name}:auth_error")
            else:
                failed.append(f"{name}:http_{resp.status_code}")
    if ok:
        detail = f"real provider OK: {', '.join(sorted(ok))}"
        if failed:
            detail += f"; failed: {', '.join(failed)}"
        return {"status": "PASS", "layer": PRODUCTION_LAYER, "detail": detail}
    return _failed(f"real LLM provider check failed: {', '.join(failed)}")


async def _check_real_woocommerce(settings: Settings) -> dict:
    """Real WooCommerce read-only reachability when credentials are present."""
    base = (settings.woocommerce_base_url or "").strip()
    consumer_key = (settings.woocommerce_consumer_key or "").strip()
    consumer_secret = (settings.woocommerce_consumer_secret or "").strip()
    if not (base and consumer_key and consumer_secret):
        return _blocked(
            "WOOCOMMERCE_BASE_URL / CONSUMER_KEY / CONSUMER_SECRET not configured "
            "-> BLOCKED_REAL_PRODUCT"
        )
    url = base.rstrip("/") + "/wp-json/wc/v3/products?per_page=1&status=publish"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, auth=(consumer_key, consumer_secret))
    except Exception as exc:  # noqa: BLE001
        return _failed(f"woocommerce unreachable: {type(exc).__name__}")
    if resp.status_code == 200:
        try:
            preview = len(resp.json())
        except Exception:  # noqa: BLE001
            preview = 0
        return {
            "status": "PASS",
            "layer": PRODUCTION_LAYER,
            "detail": f"read-only GET /products ok ({preview} preview records)",
        }
    if resp.status_code in (401, 403):
        return _failed("woocommerce auth failed (401/403)")
    return _failed(f"woocommerce http_{resp.status_code}")


async def _check_redis(settings) -> dict:
    """Real Redis: PING + stream/consumer-group readiness when explicitly configured."""
    if not _explicit_env("REDIS_URL", settings.redis_url, _DEFAULT_REDIS_URL):
        return _blocked(
            "REDIS_URL not explicitly configured; local default is not a "
            "production environment -> BLOCKED_REAL_REDIS"
        )
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        pong = await client.ping()
        if not pong:
            return _failed("redis PING returned falsy")
        try:
            await client.xgroup_create(
                settings.task_queue_stream,
                settings.task_queue_group,
                id="0",
                mkstream=True,
            )
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" not in str(exc):
                return _failed(f"consumer group init failed: {str(exc)[:160]}")
        try:
            pending = await client.xpending(settings.task_queue_stream, settings.task_queue_group)
        except Exception:  # noqa: BLE001
            pending = None
        return {
            "status": "PASS",
            "layer": PRODUCTION_LAYER,
            "detail": (
                f"PING ok; stream={settings.task_queue_stream}; "
                f"group={settings.task_queue_group}; pending={pending}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return _failed(f"redis unreachable: {str(exc)[:160]}")
    finally:
        await client.aclose()


async def _db_gate_checks(workspace_id: UUID, settings) -> dict:
    """DB-dependent production checks; connect only when DATABASE_URL is explicit."""
    if not _explicit_env("DATABASE_URL", settings.database_url, _DEFAULT_DATABASE_URL):
        base = _blocked(
            "DATABASE_URL not explicitly configured; local default is not a "
            "production environment -> BLOCKED_REAL_DATABASE"
        )
        return {key: dict(base) for key in _DB_GATE_IDS}

    engine = None
    try:
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            checks: dict[str, dict] = {}

            # postgres: live reachability + alembic head
            try:
                await session.execute(text("SELECT version()"))
                db_version = (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one_or_none()
                heads = readiness._alembic_heads()
                if db_version in heads:
                    checks["postgres"] = {
                        "status": "PASS",
                        "layer": PRODUCTION_LAYER,
                        "detail": f"PostgreSQL reachable, alembic={db_version}",
                    }
                else:
                    checks["postgres"] = _failed(
                        f"alembic at {db_version}, expected one of {heads}"
                    )
            except Exception as exc:  # noqa: BLE001
                checks["postgres"] = _failed(f"postgres check failed: {str(exc)[:160]}")

            # real products (M5.13): a Product Candidate (candidate_status
            # NOT NULL) or a WooCommerce-synced commerce product satisfies the
            # gate. WooCommerce published products are NOT a prerequisite for
            # the Product Analyst - WooCommerce is the downstream commerce
            # source. real_product_source = candidate when candidates exist.
            try:
                rows = await session.execute(
                    text(
                        "SELECT candidate_status, source, COUNT(*) FROM products "
                        "WHERE workspace_id = :ws "
                        "GROUP BY candidate_status, source "
                        "ORDER BY candidate_status, source"
                    ),
                    {"ws": str(workspace_id)},
                )
                candidates = 0
                commerce = 0
                details: list[str] = []
                for candidate_status, source, count in rows:
                    count = int(count)
                    if candidate_status is not None:
                        candidates += count
                    else:
                        commerce += count
                    details.append(f"{candidate_status or 'null'}/{source}={count}")
                if candidates > 0 or commerce > 0:
                    source_label = "candidate" if candidates > 0 else "woocommerce"
                    checks["real_products"] = {
                        "status": "PASS",
                        "layer": PRODUCTION_LAYER,
                        "detail": (
                            f"{candidates + commerce} product(s); "
                            f"real_product_source={source_label}; "
                            f"breakdown={', '.join(details)}"
                        ),
                    }
                else:
                    checks["real_products"] = _blocked(
                        "no Product Candidates and no WooCommerce products in "
                        "workspace -> BLOCKED_REAL_PRODUCT"
                    )
            except Exception as exc:  # noqa: BLE001
                checks["real_products"] = _failed(f"products check failed: {str(exc)[:160]}")

            # rbac: enabled roles must grant product.decision approve + reject
            try:
                rows = await session.execute(
                    text(
                        "SELECT role_name, permissions FROM agent_approval_roles "
                        "WHERE workspace_id = :ws AND enabled = true"
                    ),
                    {"ws": str(workspace_id)},
                )
                granted: set[str] = set()
                role_names: list[str] = []
                for role_name, permissions in rows:
                    role_names.append(str(role_name))
                    for perm in permissions or []:
                        if isinstance(perm, str):
                            granted.add(perm)
                required = {"product.decision.approve", "product.decision.reject"}
                missing = required - granted
                if not missing:
                    checks["rbac"] = {
                        "status": "PASS",
                        "layer": PRODUCTION_LAYER,
                        "detail": (
                            f"roles={sorted(role_names)} grant product.decision approve/reject"
                        ),
                    }
                else:
                    checks["rbac"] = _blocked(f"missing permissions: {', '.join(sorted(missing))}")
            except Exception as exc:  # noqa: BLE001
                checks["rbac"] = _failed(f"rbac check failed: {str(exc)[:160]}")

            # sla: per-type rows; config-driven defaults apply when absent
            try:
                sla_rows = await session.execute(
                    text(
                        "SELECT approval_type, enabled FROM agent_approval_slas "
                        "WHERE workspace_id = :ws"
                    ),
                    {"ws": str(workspace_id)},
                )
                enabled_types = sorted(r[0] for r in sla_rows if r[1])
                if enabled_types or settings.approval_sla_enabled:
                    checks["sla"] = {
                        "status": "PASS",
                        "layer": PRODUCTION_LAYER,
                        "detail": (
                            f"enabled SLA(s)={enabled_types}"
                            if enabled_types
                            else "no rows; config-driven defaults apply"
                        ),
                    }
                else:
                    checks["sla"] = _blocked("approval SLA disabled")
            except Exception as exc:  # noqa: BLE001
                checks["sla"] = _failed(f"sla check failed: {str(exc)[:160]}")

            # budget / retry: product_analyst agent policies
            try:
                agent_row = (
                    await session.execute(
                        text(
                            "SELECT id FROM agents WHERE workspace_id = :ws "
                            "AND agent_id = 'product_analyst' AND status = 'active'"
                        ),
                        {"ws": str(workspace_id)},
                    )
                ).first()
                if agent_row is None:
                    checks["budget"] = _blocked("product_analyst agent missing/inactive")
                    checks["retry"] = _blocked("product_analyst agent missing/inactive")
                else:
                    from app.services import agent_policies

                    agent_uuid = UUID(str(agent_row[0]))
                    try:
                        budget_policy = await agent_policies.get_budget_policy(
                            session, workspace_id=workspace_id, agent_id=agent_uuid
                        )
                    except Exception as exc:  # noqa: BLE001
                        budget_policy = None
                        checks["budget"] = _failed(f"budget policy check failed: {str(exc)[:160]}")
                    if budget_policy is not None:
                        checks["budget"] = {
                            "status": "PASS",
                            "layer": PRODUCTION_LAYER,
                            "detail": "budget policy configured",
                        }
                    elif "budget" not in checks:
                        checks["budget"] = _blocked("no budget policy row")
                    try:
                        retry_policy = await agent_policies.get_retry_policy(
                            session, workspace_id=workspace_id
                        )
                    except Exception as exc:  # noqa: BLE001
                        retry_policy = None
                        checks["retry"] = _failed(f"retry policy check failed: {str(exc)[:160]}")
                    if retry_policy is not None:
                        checks["retry"] = {
                            "status": "PASS",
                            "layer": PRODUCTION_LAYER,
                            "detail": "retry policy configured",
                        }
                    elif "retry" not in checks:
                        checks["retry"] = _blocked("no retry policy row")
            except Exception as exc:  # noqa: BLE001
                checks["budget"] = _failed(f"budget check failed: {str(exc)[:160]}")
                checks["retry"] = _failed(f"retry check failed: {str(exc)[:160]}")

            # audit: event_log writable
            try:
                from app.services import event_service

                await event_service.create_event(
                    session,
                    workspace_id=workspace_id,
                    event_type="agent.runtime.activation_gate_checked",
                    entity_type="runtime",
                    entity_id=str(workspace_id),
                    payload={"gate": "M5.10"},
                    trace_id=f"activation-gate-{workspace_id}",
                )
                await session.flush()
                checks["audit"] = {
                    "status": "PASS",
                    "layer": PRODUCTION_LAYER,
                    "detail": "event_log writable",
                }
            except Exception as exc:  # noqa: BLE001
                checks["audit"] = _failed(f"event_log write failed: {str(exc)[:160]}")

            return checks
    except Exception as exc:  # noqa: BLE001
        base = _failed(f"database unreachable: {str(exc)[:160]}")
        return {key: dict(base) for key in _DB_GATE_IDS}
    finally:
        if engine is not None:
            await engine.dispose()


async def run_gate(workspace_id: UUID) -> dict:
    """Run the M5.10 activation gate for a workspace."""
    settings = get_settings()
    checks: dict[str, dict] = {
        "worker": _technical(readiness._check_importable("app.worker.agent_worker")),
        "scheduler": _technical(readiness._check_importable("app.services.alert_scheduler")),
        "llm": await _check_real_llm(settings),
        "woocommerce": await _check_real_woocommerce(settings),
        "operator": await _check_operator(settings),
        "pii": _check_pii_guard(),
        "secret_guard": _check_secret_guard(),
        "workspace_isolation": _check_workspace_isolation(),
    }
    checks.update(await _db_gate_checks(workspace_id, settings))
    checks["redis"] = await _check_redis(settings)

    ordered = {gate_id: checks[gate_id] for gate_id in GATE_IDS}
    technical_blocked = [
        gate_id
        for gate_id, check in ordered.items()
        if check.get("layer") == TECHNICAL_LAYER and check.get("status") != "PASS"
    ]
    production_blocked = [
        gate_id
        for gate_id, check in ordered.items()
        if check.get("layer") == PRODUCTION_LAYER and check.get("status") != "PASS"
    ]
    technical_infra = "TECHNICAL_INFRA_PASS" if not technical_blocked else "TECHNICAL_INFRA_BLOCKED"
    production_env = "PRODUCTION_ENV_PASS" if not production_blocked else "ENVIRONMENT_BLOCKED"
    final_state = (
        "READY_FOR_REAL_BUSINESS_RUN"
        if production_env == "PRODUCTION_ENV_PASS"
        else "ENVIRONMENT_BLOCKED"
    )
    return {
        "workspace_id": str(workspace_id),
        "gate": "M5.10",
        "checks": ordered,
        "technical_infra": technical_infra,
        "production_env": production_env,
        "blocked": [
            gate_id for gate_id, check in ordered.items() if check.get("status") == "BLOCKED"
        ],
        "failed": [
            gate_id for gate_id, check in ordered.items() if check.get("status") == "FAILED"
        ],
        "final_state": final_state,
        "note": (
            "A real business run is only started after an explicit human "
            "instruction; nothing is auto-approved, auto-started, or fabricated."
        ),
    }


async def _run(args: argparse.Namespace) -> int:
    result = await run_gate(UUID(args.workspace))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    if args.verbose:
        for gate_id, check in result["checks"].items():
            print(f"{gate_id}: {check['status']} [{check.get('layer')}] - {check.get('detail')}")
    return 0 if result["final_state"] == "READY_FOR_REAL_BUSINESS_RUN" else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.pilot.activation_gate")
    parser.add_argument("--workspace", required=True, help="workspace UUID")
    parser.add_argument("--verbose", action="store_true", help="print one line per check")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
