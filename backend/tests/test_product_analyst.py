"""Tests for the Product Analyst Agent v1 (M2.2).

Covers: LLM mock flow, structured output validation (schema + business
gates), agent audit rows, decision proposals, permission boundaries and the
AI evaluation workflow.
"""

import json
from decimal import Decimal
from uuid import UUID

import pytest
from app.agents import product_analyst
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent import AiAgentRun
from app.models.event import EventLog
from app.models.product import Product
from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductDecision,
)
from app.schemas.prompt import PromptCreate
from app.schemas.rule import RuleCreate
from app.services import prompt_registry, rule_engine
from app.services.llm_gateway import LLMResponse
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
INTAKE_URL = "/api/v1/products/intake"
ANALYZE_URL = "/api/v1/agents/product-analyst/analyze"

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


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Camping Headlamp Pro",
        "sku": "NTO-HEADLAMP-002",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/123456789.html",
        "purchase_cost": "10.00",
        "domestic_shipping": "1.00",
        "first_leg_shipping": "2.00",
        "last_leg_shipping": "3.00",
        "weight_kg": "0.30",
        "dimensions": {"length": 8, "width": 5, "height": 4},
        "target_market": "US",
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


async def _seed_product_rules(db_session) -> None:
    """Seed the PRODUCT gates so the agent rule check has real gates."""
    for rule in (
        RuleCreate(
            rule_id="PROD-GATE-001",
            name="Product cost data must be complete",
            category="PRODUCT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "cost.total_cost", "op": "gt", "value": 0},
            then_result={
                "passed_message": "cost ok",
                "failed_message": "cost missing",
            },
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
            then_result={
                "passed_message": "ship ok",
                "failed_message": "ship too high",
            },
        ),
    ):
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=rule)


async def _seed_analyst_prompt(db_session) -> None:
    """Seed the PRODUCT_ANALYST prompt (registry-backed, never hardcoded)."""
    await prompt_registry.create_prompt(
        db_session,
        workspace_id=WORKSPACE,
        data=PromptCreate(
            prompt_id="PRODUCT_ANALYST",
            name="PRODUCT_ANALYST",
            version="v1",
            template=(
                "You are the Product Analyst. Context: {context_json}\n"
                "Output schema: {output_schema}"
            ),
            variables=["context_json", "output_schema"],
            status="active",
            description="test analyst prompt",
        ),
    )


def _fake_complete(content: str | dict, **overrides) -> None:
    """Build a fake gateway callable returning a canned LLMResponse."""
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


async def _intake_product(api_client, **overrides) -> UUID:
    response = api_client.post(INTAKE_URL, json=_intake_payload(**overrides))
    assert response.status_code == 201
    return UUID(response.json()["product"]["id"])


@pytest.mark.asyncio
async def test_agent_full_flow_creates_audit_and_pending_decision(
    db_session, api_client, monkeypatch
) -> None:
    """Happy path: audit run + pending decision proposal; nothing is approved."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(api_client)

    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    response = api_client.post(f"{ANALYZE_URL}/{product_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["provider"] == "openai"
    assert body["model"] == "gpt-4o-mini"
    assert body["prompt_version"] == "v1"
    assert body["decision"] == "test"
    assert body["confidence"] == "0.78"
    assert body["recommended_price"] == "39.99"
    assert body["max_cac"] == "20.00"
    assert body["test_quantity"] == 50
    assert body["test_days"] == 30
    assert body["approval_status"] == "pending"
    assert body["tokens"]["total_tokens"] == 180
    assert body["estimated_cost"] == "0.001500"
    assert body["latency_ms"] == 41

    # product_analysis_runs audit row with full metadata.
    runs = (await db_session.execute(select(ProductAnalysisRun))).scalars().all()
    llm_runs = [run for run in runs if run.provider == "openai"]
    assert len(llm_runs) == 1
    run = llm_runs[0]
    assert run.model == "gpt-4o-mini"
    assert run.prompt_version == "v1"
    assert run.status == "completed"
    assert run.estimated_cost == Decimal("0.001500")
    assert run.latency_ms == 41
    assert run.input_snapshot["meta"]["trace_id"] is not None
    assert run.output["decision"] == "test"

    # Decision proposal exists and is pending (agent cannot approve).
    decisions = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.decision == "test"
    assert decision.approval_status == "pending"
    assert decision.approved_by is None
    assert decision.recommended_price == Decimal("39.99")
    assert decision.max_cac == Decimal("20.00")
    assert decision.test_quantity == 50

    # AiAgentRun audit row.
    agent_runs = (await db_session.execute(select(AiAgentRun))).scalars().all()
    assert len(agent_runs) == 1
    agent_run = agent_runs[0]
    assert agent_run.agent == "product-analyst"
    assert agent_run.status == "completed"
    assert agent_run.cost == Decimal("0.001500")
    assert agent_run.approval == {
        "required": True,
        "status": "pending",
        "target": "product_decisions",
    }

    # Permission: product lifecycle untouched; no approval event emitted.
    product = (
        await db_session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one()
    assert product.status == "candidate"

    events = (await db_session.execute(select(EventLog))).scalars().all()
    event_types = {event.event_type for event in events}
    assert "product.analyst.analyzed" in event_types
    assert "product.decision.proposed" not in event_types
    assert "product.decision.approved" not in event_types


@pytest.mark.asyncio
async def test_agent_schema_validation_rejects_invalid_output(
    db_session, api_client, monkeypatch
) -> None:
    """Invalid structured output (bad decision) is recorded as a failed run."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(api_client)

    bad_output = dict(VALID_OUTPUT)
    bad_output["decision"] = "publish"  # not in test/hold/reject
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(bad_output))
    response = api_client.post(f"{ANALYZE_URL}/{product_id}")
    assert response.status_code == 422

    runs = (await db_session.execute(select(ProductAnalysisRun))).scalars().all()
    failed = [run for run in runs if run.provider == "openai"]
    assert len(failed) == 1
    assert failed[0].status == "failed"
    assert "invalid structured output" in failed[0].output["error"]
    # No decision proposal on failure.
    decisions = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert len(decisions) == 0
    # Failure event recorded.
    events = (await db_session.execute(select(EventLog))).scalars().all()
    assert any(event.event_type == "product.analyst.failed" for event in events)


@pytest.mark.asyncio
async def test_agent_unknown_cost_gate_blocks_test_decision(
    db_session, api_client, monkeypatch
) -> None:
    """PROFIT-003 gate: UNKNOWN cost + test/high confidence is rejected."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(
        api_client,
        purchase_cost="0.00",
        domestic_shipping="0.00",
        first_leg_shipping="0.00",
        last_leg_shipping="0.00",
    )

    risky = dict(VALID_OUTPUT)
    risky["confidence"] = "0.90"  # > 0.5 with UNKNOWN cost
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(risky))
    response = api_client.post(f"{ANALYZE_URL}/{product_id}")
    assert response.status_code == 422

    runs = (await db_session.execute(select(ProductAnalysisRun))).scalars().all()
    failed = [run for run in runs if run.provider == "openai"]
    assert len(failed) == 1
    assert failed[0].status == "failed"
    assert "PROFIT-003" in failed[0].output["error"]
    decisions = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert len(decisions) == 0


@pytest.mark.asyncio
async def test_agent_rule_veto_forces_reject(db_session, api_client, monkeypatch) -> None:
    """A hard gate failure deterministically overrides the LLM to 'reject'."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    # International shipping (2+3=5) vs LLM price 8.00 -> ratio 0.625 > 0.4.
    product_id = await _intake_product(api_client)

    veto_output = dict(VALID_OUTPUT)
    veto_output["decision"] = "hold"
    veto_output["pricing"] = dict(VALID_OUTPUT["pricing"], recommended_price="8.00")
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(veto_output))
    response = api_client.post(f"{ANALYZE_URL}/{product_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "reject"
    assert body["approval_status"] == "pending"

    decision = (await db_session.execute(select(ProductDecision))).scalars().first()
    assert decision.decision == "reject"
    assert any("hard product gate failed" in reason for reason in decision.reasons)


@pytest.mark.asyncio
async def test_agent_llm_failure_recorded(db_session, api_client, monkeypatch) -> None:
    """Gateway failure surfaces as an agent error and a failed audit row."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(api_client)

    from app.services.llm_gateway import LLMError

    async def failing(request, trace_id=None):
        raise LLMError("network down", kind="network")

    monkeypatch.setattr(product_analyst.llm_gateway, "complete", failing)
    response = api_client.post(f"{ANALYZE_URL}/{product_id}")
    assert response.status_code == 422
    assert "LLM call failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_agent_permission_never_mutates_product(db_session, api_client, monkeypatch) -> None:
    """The agent may read product data but never change lifecycle/supplier rows."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(api_client)

    before = (
        await db_session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one()
    assert before.status == "candidate"

    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    api_client.post(f"{ANALYZE_URL}/{product_id}")
    await db_session.flush()

    after = (await db_session.execute(select(Product).where(Product.id == product_id))).scalar_one()
    assert after.status == "candidate"
    assert after.sku == before.sku
    # No purchase orders / suppliers / order rows are created by the agent.
    from app.models.order import Order

    orders = (await db_session.execute(select(Order))).scalars().all()
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_ai_evaluation_records_prediction_accuracy(
    db_session, api_client, monkeypatch
) -> None:
    """Evaluation stores prediction, actuals, deterministic deltas, human rating."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(api_client)

    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    run_response = api_client.post(f"{ANALYZE_URL}/{product_id}")
    run_id = run_response.json()["analysis_run_id"]

    eval_response = api_client.post(
        "/api/v1/ai-evaluations",
        json={
            "product_id": str(product_id),
            "analysis_run_id": run_id,
            "actual_result": {
                "decision": "test",
                "confidence": "0.70",
                "test_plan.kpis.roas": 2.5,
            },
            "human_rating": 4,
            "notes": "prediction direction was right",
        },
    )
    assert eval_response.status_code == 201
    body = eval_response.json()
    assert body["human_rating"] == 4
    assert body["prediction"]["decision"] == "test"
    assert body["accuracy"]["decision_match"] is True
    assert body["accuracy"]["keys"] == ["confidence", "test_plan.kpis.roas"]
    assert body["accuracy"]["deltas"]["test_plan.kpis.roas"] == "0.5000"

    rows = (await db_session.execute(select(ProductAiEvaluation))).scalars().all()
    assert len(rows) == 1
    evaluation = rows[0]
    assert evaluation.analysis_run_id is not None
    assert evaluation.accuracy["deltas"]["test_plan.kpis.roas"] == "0.5000"
    assert evaluation.accuracy["deltas"]["confidence"] == "-0.0800"


@pytest.mark.asyncio
async def test_analysis_runs_listing(db_session, api_client, monkeypatch) -> None:
    """AI runs are listed separately from deterministic runs."""
    await _seed_product_rules(db_session)
    await _seed_analyst_prompt(db_session)
    product_id = await _intake_product(api_client)

    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    api_client.post(f"{ANALYZE_URL}/{product_id}")
    response = api_client.get(f"/api/v1/agents/product-analyst/runs/{product_id}")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["provider"] == "openai"
