"""Shared helpers for M5.2.1 real-infrastructure runtime tests.

Seeds a registered Product Analyst agent, product intelligence rows, PRODUCT
hard rules and fast retry/execution policies on a real PostgreSQL database,
then drives the M5.1 worker against a real Redis queue.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentRegistry
from app.models.rule import Rule
from app.schemas.product_intelligence import ProductIntakeRequest
from app.schemas.rule import RuleCreate
from app.services import agent_policies, product_intelligence, rule_engine
from app.services.llm_gateway import LLMResponse
from app.worker.agent_worker import run_worker_once

WORKSPACE = DEFAULT_WORKSPACE_ID

VALID_OUTPUT = {
    "decision": "test",
    "confidence": "0.78",
    "market_reasoning": "Strong margin at light weight; demand signals positive.",
    "risks": ["Supplier lead time variability", "Platform competition"],
    "pricing": {
        "recommended_price": "39.99",
        "price_range": ["34.99", "44.99"],
        "max_cac": "20.00",
        "rationale": "Margin supports paid acquisition",
    },
    "test_plan": {
        "quantity": 50,
        "days": 30,
        "channels": ["meta", "google"],
        "budget": "800.00",
        "kpis": {"roas": 2.0},
    },
}


def factory(engine) -> async_sessionmaker:
    """Async session factory bound to a (real) database engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def seed_rules(session, *, workspace: UUID = WORKSPACE) -> None:
    """Seed the PRODUCT hard gates used by the agent rule check.

    Idempotent: migration 0004 already seeds PROD-GATE-001/002 (and PROFIT-003)
    into the default workspace on a real PostgreSQL database, while SQLite
    ``create_all`` does not run migrations. Rows that exist are skipped so the
    helper works on both backends without unique-constraint conflicts.
    """
    for rule in (
        RuleCreate(
            rule_id="PROD-GATE-001",
            name="Product cost data must be complete",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "cost.total_cost", "op": "gt", "value": 0},
            then_result={"passed_message": "cost ok", "failed_message": "cost missing"},
        ),
        RuleCreate(
            rule_id="PROD-GATE-002",
            name="Shipping within 40% of expected price",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={
                "field": "logistics.shipping_ratio",
                "op": "lte",
                "value": 0.4,
            },
            then_result={"passed_message": "ship ok", "failed_message": "ship too high"},
        ),
    ):
        existing = (
            (
                await session.execute(
                    select(Rule).where(
                        Rule.workspace_id == workspace,
                        Rule.rule_id == rule.rule_id,
                        Rule.version == rule.version,
                    )
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            continue
        await rule_engine.create_rule(session, workspace_id=workspace, data=rule)


async def intake_product(session, *, workspace: UUID = WORKSPACE) -> UUID:
    """Intake one product with complete landed-cost data; returns product id."""
    result = await product_intelligence.intake_product(
        session,
        workspace_id=workspace,
        data=ProductIntakeRequest(
            title="Camping Headlamp Pro",
            sku="NTO-HEADLAMP-M521",
            source_type="1688",
            source_url="https://detail.1688.com/offer/987654321.html",
            purchase_cost=Decimal("10.00"),
            domestic_shipping=Decimal("1.00"),
            first_leg_shipping=Decimal("2.00"),
            last_leg_shipping=Decimal("3.00"),
            weight_kg=Decimal("0.30"),
            target_market="US",
            currency="USD",
        ),
    )
    return result.product.id


async def seed_and_intake(session, *, workspace: UUID = WORKSPACE) -> tuple[AgentRegistry, UUID]:
    """Prompt + registered product_analyst agent + intaken product + rules."""
    await seed_rules(session, workspace=workspace)
    from app.agents.agent_seed import ensure_product_analyst_agent

    agent = await ensure_product_analyst_agent(session, workspace_id=workspace)
    product_id = await intake_product(session, workspace=workspace)
    return agent, product_id


async def set_fast_retry(session, *, workspace: UUID = WORKSPACE, max_attempts: int = 3) -> None:
    """Retry policy with no backoff so retries are processed immediately."""
    await agent_policies.set_retry_policy(
        session,
        workspace_id=workspace,
        retry_policy_id="standard",
        name="Instant (M5.2.1 test)",
        max_attempts=max_attempts,
        backoff_base_seconds=0,
        backoff_multiplier=Decimal("2"),
        max_backoff_seconds=5,
        retry_on_error_types=["llm", "network", "timeout", "transient"],
        enabled=True,
    )


async def set_execution_policy(
    session, *, agent_id: UUID, workspace: UUID = WORKSPACE, execution_timeout: int = 60
) -> None:
    await agent_policies.set_execution_policy(
        session,
        workspace_id=workspace,
        agent_id=agent_id,
        max_concurrent=2,
        execution_timeout_seconds=execution_timeout,
        approval_timeout_seconds=3600,
        max_context_size=5000,
        retry_policy_id="standard",
        enabled=True,
    )


def fake_complete(content: str | dict, **overrides):
    """Canned LLM gateway callable returning a structured response."""
    if isinstance(content, dict):
        content = json.dumps(content)

    async def caller(request, trace_id=None):
        return LLMResponse(
            provider=overrides.get("provider", "openai"),
            model=overrides.get("model", "gpt-4o-mini"),
            content=content,
            tokens=overrides.get(
                "tokens",
                {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
            ),
            cost=overrides.get("cost", Decimal("0.001500")),
            latency_ms=overrides.get("latency_ms", 41),
            trace_id=trace_id,
        )

    return caller


async def run_worker(backend, session_factory, executor, *, rounds: int = 4) -> int:
    """Drain the real queue until no messages remain (or rounds exhausted)."""
    total = 0
    for _ in range(rounds):
        processed = await run_worker_once(backend, session_factory, executor=executor)
        total += processed
        if processed == 0:
            break
    return total
