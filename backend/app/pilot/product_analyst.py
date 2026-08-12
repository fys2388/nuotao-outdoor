"""M5.6 Product Analyst production pilot CLI.

Runs one real product through the whole chain:

    product -> context -> Product Analyst -> LLM -> structured output ->
    gates -> product_analysis_runs -> product_decisions (pending)

and prints the trace_id / decision_id / cost / latency. It NEVER approves,
never starts experiments and never executes a business action - the human
keeps every gate.

Usage (from ``backend``):

    set PYTHONPATH=%CD%
    .venv\\Scripts\\python -m app.pilot.product_analyst --workspace <ws> --product <id>
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
    parser.add_argument("--timeout", type=int, default=300, help="max wait seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="poll interval seconds")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    workspace_id = UUID(args.workspace)
    product_id = UUID(args.product)
    trace_id = f"pilot-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"

    try:
        async with factory() as session:
            task = await pilot_product_analyst.create_pilot_task(
                session,
                workspace_id=workspace_id,
                product_id=product_id,
                actor="pilot-cli",
                trace_id=trace_id,
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
            if decision is not None:
                print(f"decision_id: {decision.id}")
                print(f"decision: {decision.decision} approval_status={decision.approval_status}")
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
