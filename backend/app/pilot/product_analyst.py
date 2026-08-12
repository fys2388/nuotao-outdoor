"""M5.6/M5.7 Product Analyst production pilot CLI.

Runs one real product through the chain:

    product -> context -> Product Analyst -> LLM -> structured output ->
    gates -> product_analysis_runs -> product_decisions (pending)

``--dry-run`` validates ``context -> LLM -> schema -> business gates`` WITHOUT
writing any rows (no decision / experiment / approval). A real run creates a
pending decision and keeps the human gates. ``--provider`` pins the LLM
provider (``auto`` = gateway default with OpenAI -> DeepSeek fallback;
``openai`` / ``deepseek`` = that provider only). ``--trace`` prints the
full audit chain for the run. It NEVER approves, never starts experiments and
never executes a business action.

Usage (from ``backend``):

    set PYTHONPATH=%CD%
    .venv\\Scripts\\python -m app.pilot.product_analyst --workspace <ws> --product <id>
    .venv\\Scripts\\python -m app.pilot.product_analyst --workspace <ws> --product <id> --dry-run
    .venv\\Scripts\\python -m app.pilot.product_analyst --workspace <ws> --product <id> \\
        --provider deepseek
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.models.product_intelligence import ProductAnalysisRun, ProductDecision
from app.services import pilot_product_analyst


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.pilot.product_analyst",
        description="Run one Product Analyst pilot (analysis + proposal only).",
    )
    parser.add_argument("--workspace", required=True, help="workspace UUID")
    parser.add_argument("--product", required=True, help="product UUID")
    parser.add_argument(
        "--provider",
        default="auto",
        choices=("auto", "openai", "deepseek"),
        help="LLM provider: auto (default, OpenAI primary + DeepSeek fallback) or a pinned "
        "provider",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate context -> LLM -> schema -> gates without writing any rows",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="print the full audit chain for the run (events by trace_id)",
    )
    parser.add_argument(
        "--validation-source",
        default=None,
        choices=("staging_real", "staging_synthetic"),
        help="record a validation case with this source after the run",
    )
    parser.add_argument("--timeout", type=int, default=300, help="max wait seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="poll interval seconds")
    return parser.parse_args(argv)


async def _gateway_for_provider(provider: str):
    """Return a gateway wrapper pinned to one provider (None = auto)."""
    if provider in (None, "auto"):
        return None
    from dataclasses import replace

    from app.services import llm_gateway

    async def caller(request, trace_id=None):
        pinned = replace(request, provider=provider)
        # Pinning a provider disables the fallback chain: the operator asked
        # for a specific provider, not for failover.
        return await llm_gateway.complete(pinned, trace_id=trace_id, allow_fallback=False)

    return caller


async def _print_trace(session, trace_id: str) -> None:
    """Print the audit chain for one trace (task -> execution -> events)."""
    from sqlalchemy import select

    from app.models.agent_runtime import AgentExecution, AgentTask
    from app.models.event import EventLog

    task = (
        (await session.execute(select(AgentTask).where(AgentTask.trace_id == trace_id)))
        .scalars()
        .first()
    )
    if task is not None:
        print(f"[trace] task: {task.id} status={task.status} agent={task.agent_id}")
    executions = (
        (await session.execute(select(AgentExecution).where(AgentExecution.trace_id == trace_id)))
        .scalars()
        .all()
    )
    for execution in executions:
        print(
            f"[trace] execution: {execution.id} status={execution.status} "
            f"model={execution.model} tokens={execution.tokens} cost={execution.cost}"
        )
    events = (
        (
            await session.execute(
                select(EventLog).where(EventLog.trace_id == trace_id).order_by(EventLog.created_at)
            )
        )
        .scalars()
        .all()
    )
    for event in events:
        print(
            f"[trace] event: {event.event_type} entity={event.entity_type}/{event.entity_id} "
            f"at={event.created_at}"
        )


async def _dry_run(
    session, *, workspace_id: UUID, product_id: UUID, provider: str, trace_id: str
) -> int:
    """Validate context -> LLM -> schema -> gates; write nothing."""
    from app.agents import product_analyst

    gateway = await _gateway_for_provider(provider)
    result = await product_analyst.analyze_product(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        gateway_complete=gateway,
        trace_id=trace_id,
        prompt_name="AGENT_PRODUCT_ANALYST",
        re_raise_llm_errors=True,
        persist=False,
        dry_run=True,
    )
    assert result.output is not None
    print(f"DRY-RUN OK trace_id={trace_id}")
    print(f"decision={result.output.decision} confidence={result.output.confidence}")
    print(
        "recommended_price="
        f"{result.output.pricing.recommended_price} max_cac={result.output.pricing.max_cac}"
    )
    print("NOTES: dry-run only - no decision / experiment / approval was created.")
    return 0


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    workspace_id = UUID(args.workspace)
    product_id = UUID(args.product)
    trace_id = f"pilot-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"

    try:
        async with factory() as session:
            if args.dry_run:
                return await _dry_run(
                    session,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    provider=args.provider,
                    trace_id=trace_id,
                )

            task_input = {"product_id": str(product_id)}
            if args.provider in ("openai", "deepseek"):
                task_input["provider"] = args.provider
            task = await pilot_product_analyst.create_pilot_task(
                session,
                workspace_id=workspace_id,
                product_id=product_id,
                actor="pilot-cli",
                trace_id=trace_id,
                task_input=task_input,
            )
            await session.commit()
            print(f"pilot task created: task_id={task.id} trace_id={task.trace_id}")
            task = await pilot_product_analyst.wait_for_task(
                session,
                task_id=task.id,
                timeout_seconds=args.timeout,
                interval=args.interval,
            )
            print(f"task status: {task.status}")
            if task.status != "completed":
                print(f"task error: {task.error_message}")
                return 1
            run = (
                await session.execute(
                    select(ProductAnalysisRun)
                    .where(
                        ProductAnalysisRun.workspace_id == workspace_id,
                        ProductAnalysisRun.product_id == product_id,
                        ProductAnalysisRun.provider != "deterministic",
                    )
                    .order_by(ProductAnalysisRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            decision = (
                await session.execute(
                    select(ProductDecision)
                    .where(
                        ProductDecision.workspace_id == workspace_id,
                        ProductDecision.product_id == product_id,
                    )
                    .order_by(ProductDecision.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            print(f"trace_id: {trace_id}")
            if run is not None:
                print(f"analysis_run_id: {run.id}")
                print(f"provider/model: {run.provider}/{run.model}")
                print(f"execution_cost: {run.estimated_cost}")
                print(f"latency_ms: {run.latency_ms}")
                print(f"tokens: {run.token_usage}")
            if decision is not None:
                print(f"decision_id: {decision.id}")
                print(f"decision: {decision.decision} approval_status={decision.approval_status}")
            if args.validation_source:
                from app.services import validation_dataset

                await validation_dataset.register_case(
                    session,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    source=args.validation_source,
                    run_id=run.id if run else None,
                    trace_id=trace_id,
                    notes="registered by pilot CLI",
                )
                await session.commit()
                print(f"validation case recorded: source={args.validation_source}")
            if args.trace:
                await _print_trace(session, trace_id)
            print("NOTE: decision stays pending; approve it through the Approval Center.")
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    logging.getLogger(__name__).setLevel(logging.WARNING)
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
