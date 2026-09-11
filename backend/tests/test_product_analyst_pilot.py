"""M5.6 Product Analyst Production Pilot tests.

Verifies the real business loop end to end with the in-memory DB:

    product -> decision proposal -> Human Approval (Approval Center + RBAC)
    -> experiment proposal -> human start (second gate) -> actual result
    -> evaluation backfill -> calibration proposal -> human-approved
    -> knowledge feedback -> next product context

plus the pilot API / scorecard / ROI endpoints, PII guards, workspace
isolation and the "no shortcut" guarantees (agents can never approve, an
experiment can never start without a human ``started_by``, calibration can
never auto-modify weights/rules).
"""

import json
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.agents import product_analyst
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentApproval
from app.models.event import EventLog
from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductDecision,
    ProductExperiment,
    ProductScoreCalibrationRun,
)
from app.schemas.rule import RuleCreate
from app.services import (
    approval_rbac,
    evaluation_bridge,
    pilot_product_analyst,
    rule_engine,
)
from app.services.llm_gateway import LLMResponse

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

INTAKE_URL = "/api/v1/products/intake"
DECISIONS_URL = "/api/v1/products/{product_id}/decisions"
APPROVE_URL = "/api/v1/product-decisions/{decision_id}/approve"
REJECT_URL = "/api/v1/product-decisions/{decision_id}/reject"
EXPERIMENT_URL = "/api/v1/product-decisions/{decision_id}/experiment"
START_URL = "/api/v1/product-decisions/experiments/{experiment_id}/start"
COMPLETE_URL = "/api/v1/product-decisions/experiments/{experiment_id}/complete"


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _seed_rules(db_session, *, workspace: UUID = WORKSPACE) -> None:
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
        await rule_engine.create_rule(db_session, workspace_id=workspace, data=rule)


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Camping Headlamp Pro",
        "sku": "NTO-HEADLAMP-PILOT",
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


async def _seed_and_intake(db_session, api_client, *, workspace: UUID = WORKSPACE) -> UUID:
    """Seed PRODUCT gates + register the analyst agent + intake a product."""
    await _seed_rules(db_session, workspace=workspace)
    from app.agents.agent_seed import ensure_product_analyst_agent

    await ensure_product_analyst_agent(db_session, workspace_id=workspace)
    payload = _intake_payload()
    if workspace != WORKSPACE:
        payload["sku"] = "NTO-HEADLAMP-PILOT-ALT"
    response = api_client.post(INTAKE_URL, json=payload, headers=_headers(workspace))
    assert response.status_code == 201, response.text
    return UUID(response.json()["product"]["id"])


async def _propose_decision(api_client, product_id: UUID, *, workspace: UUID = WORKSPACE) -> dict:
    response = api_client.post(
        DECISIONS_URL.format(product_id=product_id), headers=_headers(workspace)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _approve(
    api_client, decision_id: UUID, *, actor: str, workspace: UUID = WORKSPACE
) -> dict:
    response = api_client.post(
        APPROVE_URL.format(decision_id=decision_id),
        json={"actor": actor, "note": "approved in test"},
        headers=_headers(workspace),
    )
    return response


async def _propose_experiment(
    api_client, decision_id: UUID, *, workspace: UUID = WORKSPACE
) -> dict:
    response = api_client.post(
        EXPERIMENT_URL.format(decision_id=decision_id),
        json={"note": "market test proposal"},
        headers=_headers(workspace),
    )
    return response


async def _start(
    api_client, experiment_id: UUID, *, workspace: UUID = WORKSPACE, **overrides
) -> dict:
    body = {
        "quantity": 30,
        "channels": ["meta"],
        "budget": "300.00",
        "targets": {"roas": 1.0, "margin_rate": 0.30},
        "started_by": overrides.pop("started_by", None),
        **overrides,
    }
    response = api_client.post(
        START_URL.format(experiment_id=experiment_id),
        json=body,
        headers=_headers(workspace),
    )
    return response


async def _complete(
    api_client, experiment_id: UUID, *, workspace: UUID = WORKSPACE, **overrides
) -> dict:
    body = {
        "units_sold": 40,
        "revenue": "1600.00",
        "orders": 32,
        "conversion_rate": "0.031",
        "roas": "2.00",
        "margin_rate": "0.35",
        "actor": overrides.pop("actor", "tester"),
        "source": overrides.pop("source", "manual"),
        **overrides,
    }
    response = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json=body,
        headers=_headers(workspace),
    )
    return response


async def _event_types(db_session) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


def _fake_complete(content: str | dict, **overrides):
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


VALID_OUTPUT = {
    "decision": "test",
    "confidence": "0.78",
    "market_reasoning": "Strong margin at light weight; demand signals positive.",
    "risks": ["Supplier lead time variability"],
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

# --------------------------------------------------------------------------- #
# Human Approval Bridge (product decision -> Approval Center + RBAC)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_agent_actor_cannot_approve_decision_403(db_session, api_client) -> None:
    """An agent (reserved or registered) can never approve its own proposal."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)

    response = await _approve(api_client, UUID(decision["id"]), actor="product_analyst")
    assert response.status_code == 403, response.text

    rows = (await db_session.execute(select(ProductDecision))).scalars().all()
    assert rows[0].approval_status == "pending"


@pytest.mark.asyncio
async def test_decision_rbac_403_without_product_decision_permission(
    db_session, api_client, monkeypatch
) -> None:
    """Server-side RBAC: a role without product.decision.approve gets 403."""
    settings = get_settings()
    monkeypatch.setattr(settings, "approval_rbac_enabled", True)
    await approval_rbac.create_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="reviewer",
        permissions=["tool.approve"],  # NOT product.decision.approve
        actors=["alice"],
        enabled=True,
        trace_id="test",
    )
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    response = await _approve(api_client, UUID(decision["id"]), actor="alice")
    assert response.status_code == 403, response.text
    assert "product.decision.approve" in response.text


@pytest.mark.asyncio
async def test_decision_approve_with_rbac_permission_succeeds(
    db_session, api_client, monkeypatch
) -> None:
    """A human with product.decision.approve can approve via the center."""
    settings = get_settings()
    monkeypatch.setattr(settings, "approval_rbac_enabled", True)
    await approval_rbac.create_role(
        db_session,
        workspace_id=WORKSPACE,
        role_name="product-ops",
        permissions=["product.decision.approve", "product.decision.reject"],
        actors=["cto@nuotao.example"],
        enabled=True,
        trace_id="test",
    )
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)

    response = await _approve(api_client, UUID(decision["id"]), actor="cto@nuotao.example")
    assert response.status_code == 200, response.text
    assert response.json()["approval_status"] == "approved"
    assert response.json()["approved_by"] == "cto@nuotao.example"

    approval = (
        await db_session.execute(
            select(AgentApproval).where(
                AgentApproval.approval_type == "PRODUCT_DECISION",
                AgentApproval.entity_id == str(decision["id"]),
            )
        )
    ).scalar_one()
    assert approval.status == "approved"
    assert approval.actor == "cto@nuotao.example"
    assert approval.trace_id is not None

    events = await _event_types(db_session)
    assert "agent.product_decision.proposed" in events
    assert "agent.product_decision.approved" in events
    assert "agent.approval.created" in events


@pytest.mark.asyncio
async def test_decision_double_approve_400(db_session, api_client) -> None:
    """A second approve/reject on the same decision is a hard 400."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    decision_id = UUID(decision["id"])

    first = await _approve(api_client, decision_id, actor="cto@nuotao.example")
    assert first.status_code == 200
    second = await _approve(api_client, decision_id, actor="cto@nuotao.example")
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_rejected_decision_cannot_spawn_experiment(db_session, api_client) -> None:
    """A rejected decision is terminal: no experiment proposal is possible."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    decision_id = UUID(decision["id"])

    rejected = api_client.post(
        REJECT_URL.format(decision_id=decision_id),
        json={"actor": "cto@nuotao.example", "note": "not now"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["approval_status"] == "rejected"

    experiment = await _propose_experiment(api_client, decision_id)
    assert experiment.status_code == 400
    assert "approve" in experiment.text


@pytest.mark.asyncio
async def test_decision_approval_workspace_isolation(db_session, api_client) -> None:
    """Workspace B cannot see/decide workspace A's product decision."""
    product_a = await _seed_and_intake(db_session, api_client)
    decision_a = await _propose_decision(api_client, product_a)

    # Workspace B sees no approval row for the same entity id.
    response = await _approve(
        api_client,
        UUID(decision_a["id"]),
        actor="cto@nuotao.example",
        workspace=OTHER_WORKSPACE,
    )
    assert response.status_code == 404, response.text

    # And workspace A still sees its pending decision untouched.
    rows = (
        (
            await db_session.execute(
                select(ProductDecision).where(ProductDecision.workspace_id == WORKSPACE)
            )
        )
        .scalars()
        .all()
    )
    assert rows[0].approval_status == "pending"


# --------------------------------------------------------------------------- #
# Experiment Bridge (second human gate)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_experiment_requires_approved_decision(db_session, api_client) -> None:
    """A pending decision cannot spawn an experiment (first gate)."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    response = await _propose_experiment(api_client, UUID(decision["id"]))
    assert response.status_code == 400
    assert "not approved" in response.text


@pytest.mark.asyncio
async def test_experiment_proposal_from_approved_decision(db_session, api_client) -> None:
    """Approved decision -> experiment proposal (proposed, never auto-started)."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    approved = api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    assert approved.status_code == 200

    response = await _propose_experiment(api_client, UUID(decision["id"]))
    assert response.status_code == 201, response.text
    experiment = response.json()
    assert experiment["status"] == "proposed"
    assert experiment["decision_id"] == decision["id"]
    assert experiment["hypothesis"]
    assert experiment["expected_metrics"]
    assert experiment["baseline"]
    assert experiment["target_metrics"]["roas"] == "1.0"
    assert experiment["source_trace_id"]

    events = await _event_types(db_session)
    assert "agent.experiment.proposed" in events
    assert "product.experiment.proposed" in events


@pytest.mark.asyncio
async def test_experiment_proposal_idempotent_per_decision(db_session, api_client) -> None:
    """Re-proposing for the same decision returns the same experiment row."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    first = await _propose_experiment(api_client, UUID(decision["id"]))
    second = await _propose_experiment(api_client, UUID(decision["id"]))
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    rows = (await db_session.execute(select(ProductExperiment))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_experiment_start_requires_human_started_by(db_session, api_client) -> None:
    """Decision-linked experiments cannot start without a human started_by."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])

    no_actor = await _start(api_client, experiment_id, started_by=None)
    assert no_actor.status_code == 400
    assert "started_by" in no_actor.text

    # An agent identifier is not accepted either (human control point).
    agent_start = await _start(api_client, experiment_id, started_by="product_analyst")
    assert agent_start.status_code == 403


@pytest.mark.asyncio
async def test_experiment_start_second_gate_full(db_session, api_client) -> None:
    """Human start activates the experiment; the decision stays approved."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])

    response = await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "active"
    assert body["started_by"] == "cto@nuotao.example"
    assert body["experiment"]["quantity"] == 30

    events = await _event_types(db_session)
    assert "agent.experiment.started" in events
    assert "product.experiment.started" in events


# --------------------------------------------------------------------------- #
# Evaluation Bridge (actual result -> product_ai_evaluations)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_complete_experiment_backfills_product_ai_evaluation(db_session, api_client) -> None:
    """actual_result flows into product_ai_evaluations (append-only, linked)."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    assert (
        await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    ).status_code == 200

    completed = await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["actual_result"]["roas"] == "2.00"

    evaluations = (await db_session.execute(select(ProductAiEvaluation))).scalars().all()
    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert evaluation.experiment_id == experiment_id
    assert evaluation.product_id == product_id
    assert evaluation.actual_result["roas"] == "2.00"
    assert evaluation.prediction_result == "success"
    assert evaluation.success_flag is True
    assert evaluation.confidence_bucket is not None
    assert evaluation.metric_snapshot["actual_roas"] == "2.00"

    events = await _event_types(db_session)
    assert "agent.product_evaluation.backfilled" in events
    assert "agent.experiment.completed" in events


@pytest.mark.asyncio
async def test_complete_experiment_requires_active(db_session, api_client) -> None:
    """Completing a non-active experiment is rejected."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    response = await _complete(api_client, experiment_id)
    assert response.status_code == 400
    assert "not active" in response.text


@pytest.mark.asyncio
async def test_llm_path_decision_and_agent_evaluation_mirror(
    db_session, api_client, monkeypatch
) -> None:
    """LLM path: agent evaluation mirror gets the experiment actuals."""
    product_id = await _seed_and_intake(db_session, api_client)
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    analysis = await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-pilot-llm",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )
    assert analysis.decision is not None
    decision_id = analysis.decision.id

    # Approve -> experiment -> start -> complete (actuals flow back).
    approved = api_client.post(
        APPROVE_URL.format(decision_id=decision_id),
        json={"actor": "cto@nuotao.example"},
    )
    assert approved.status_code == 200
    experiment = await _propose_experiment(api_client, decision_id)
    assert experiment.status_code == 201
    experiment_id = UUID(experiment.json()["id"])
    assert (
        await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    ).status_code == 200
    completed = await _complete(api_client, experiment_id, roas="0.50", margin_rate="-0.10")
    assert completed.status_code == 200

    evaluations = (await db_session.execute(select(ProductAiEvaluation))).scalars().all()
    assert len(evaluations) == 1
    mirrored = [row for row in evaluations if row.experiment_id == experiment_id]
    assert len(mirrored) == 1
    assert mirrored[0].prediction_result == "failure"
    assert mirrored[0].error_type in ("metric_miss", "margin_miss", "other")
    # The prediction snapshot carries the agent's decision (audit of the chain).
    assert mirrored[0].prediction["decision"] == "test"


# --------------------------------------------------------------------------- #
# Calibration + Knowledge feedback
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_calibration_skipped_without_completed_experiments(db_session, api_client) -> None:
    """No completed experiments -> calibration run returns skipped=True."""
    await _seed_and_intake(db_session, api_client)
    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-skip"
    )
    assert result["skipped"] is True
    assert result["calibration_run"] is None
    assert result["confidence"] == []


@pytest.mark.asyncio
async def test_calibration_proposed_after_real_results(db_session, api_client) -> None:
    """Completed experiments -> confidence report + proposed score run."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")

    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-1"
    )
    assert result["skipped"] is False
    assert result["confidence"]
    assert result["calibration_run"]["status"] == "proposed"
    run_id = UUID(result["calibration_run"]["id"])

    # SCORE_WEIGHTS are never modified automatically.
    from app.services.product_intelligence import SCORE_WEIGHTS

    before = dict(SCORE_WEIGHTS)
    run = (
        await db_session.execute(
            select(ProductScoreCalibrationRun).where(ProductScoreCalibrationRun.id == run_id)
        )
    ).scalar_one()
    assert run.suggested_weights is not None
    assert dict(SCORE_WEIGHTS) == before
    assert "agent.product_calibration.proposed" in await _event_types(db_session)

    # The calibration proposal is surfaced in the Approval Center.
    approval = (
        await db_session.execute(
            select(AgentApproval).where(
                AgentApproval.approval_type == "CALIBRATION",
                AgentApproval.entity_id == str(run_id),
            )
        )
    ).scalar_one()
    assert approval.status == "pending"


@pytest.mark.asyncio
async def test_knowledge_sync_requires_approved_calibration(db_session, api_client) -> None:
    """A proposed/rejected calibration run can never sync to knowledge."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")
    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-2"
    )
    run_id = UUID(result["calibration_run"]["id"])

    with pytest.raises(evaluation_bridge.EvaluationBridgeError) as excinfo:
        await evaluation_bridge.sync_calibration_to_knowledge(
            db_session, workspace_id=WORKSPACE, run_id=run_id, trace_id="trace-kb-1"
        )
    assert "only an approved calibration run" in str(excinfo.value)


@pytest.mark.asyncio
async def test_knowledge_feedback_after_approval(db_session, api_client) -> None:
    """Approved calibration + completed experiments -> knowledge entries."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")

    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-3"
    )
    run_id = UUID(result["calibration_run"]["id"])

    # Human approves the calibration run through the Approval Center.
    from app.services import approval_service, task_queue

    approval = (
        await db_session.execute(
            select(AgentApproval).where(
                AgentApproval.approval_type == "CALIBRATION",
                AgentApproval.entity_id == str(run_id),
            )
        )
    ).scalar_one()
    backend = task_queue.get_queue_backend()
    await approval_service.approve_approval(
        db_session,
        backend,
        workspace_id=WORKSPACE,
        approval_id=approval.id,
        actor="cto@nuotao.example",
        trace_id="trace-calb-3",
    )

    entries = await pilot_product_analyst.feedback_knowledge(
        db_session,
        workspace_id=WORKSPACE,
        calibration_run_id=run_id,
        trace_id="trace-kb-2",
    )
    kinds = {entry.entry_type for entry in entries}
    assert "category_insight" in kinds
    assert "success_pattern" in kinds
    assert "agent.product_knowledge.created" in await _event_types(db_session)

    # Idempotent: re-running the feedback creates no duplicate experiment rows.
    entries_again = await pilot_product_analyst.feedback_knowledge(
        db_session,
        workspace_id=WORKSPACE,
        calibration_run_id=run_id,
        trace_id="trace-kb-3",
    )
    again_success = [e for e in entries_again if e.entry_type == "success_pattern"]
    assert len(again_success) == 0


@pytest.mark.asyncio
async def test_knowledge_enters_next_product_context(db_session, api_client) -> None:
    """Knowledge entries are queryable by the Product Context Builder."""
    product_id = await _seed_and_intake(db_session, api_client)
    from app.schemas.product_analyst import KnowledgeEntryCreate
    from app.services import knowledge, product_context

    await knowledge.create_knowledge_entry(
        db_session,
        workspace_id=WORKSPACE,
        data=KnowledgeEntryCreate(
            product_id=product_id,
            category="camping",
            entry_type="success_pattern",
            title="Headlamp sells",
            content="tested pattern",
            tags=["experiment"],
            source="experiment",
        ),
        trace_id="trace-kb-ctx",
    )
    context = await product_context.build_product_context(
        db_session, workspace_id=WORKSPACE, product_id=product_id, trace_id="trace-ctx-1"
    )
    assert "knowledge" in context
    assert any(row["entry_type"] == "success_pattern" for row in context["knowledge"])
    assert any(row["knowledge_id"] for row in context["knowledge"])


# --------------------------------------------------------------------------- #
# Pilot API / Scorecard / ROI
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pilot_api_creates_task_and_audit_event(db_session, api_client) -> None:
    """POST /agents/product-analyst/pilot creates a task + pilot_started event."""
    product_id = await _seed_and_intake(db_session, api_client)
    response = api_client.post(
        "/api/v1/agents/product-analyst/pilot",
        json={"product_id": str(product_id), "actor": "ops@nuotao.example"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["trace_id"] is not None
    assert body["decision_proposal_id"] is None  # nothing decided

    events = await _event_types(db_session)
    assert "agent.product_analyst.pilot_started" in events

    from app.models.agent_runtime import AgentTask

    tasks = (await db_session.execute(select(AgentTask))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].input["product_id"] == str(product_id)


@pytest.mark.asyncio
async def test_pilot_api_unknown_product_400(db_session, api_client) -> None:
    """An unknown product id is rejected before anything is enqueued."""
    response = api_client.post(
        "/api/v1/agents/product-analyst/pilot",
        json={"product_id": "00000000-0000-0000-0000-00000000dead"},
    )
    assert response.status_code == 400
    assert "product not found" in response.text


@pytest.mark.asyncio
async def test_scorecard_aggregates_workspace_scoped(db_session, api_client) -> None:
    """Scorecard aggregates real runs/decisions; other workspaces are invisible."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")

    scorecard = await pilot_product_analyst.scorecard(db_session, workspace_id=WORKSPACE)
    assert scorecard["analyzed_products"] == 0  # deterministic decision, no LLM run
    assert scorecard["decision_proposed"] == 0
    assert scorecard["decision_approved"] == 1
    assert scorecard["experiment_completed"] == 1

    # The other workspace sees an empty scorecard.
    other = await pilot_product_analyst.scorecard(db_session, workspace_id=OTHER_WORKSPACE)
    assert other["decision_approved"] == 0
    assert other["experiment_completed"] == 0


@pytest.mark.asyncio
async def test_roi_never_fabricates_impact(db_session, api_client) -> None:
    """ROI reports real costs; revenue/margin/roas impact stay null."""
    product_id = await _seed_and_intake(db_session, api_client)
    decision = await _propose_decision(api_client, product_id)
    api_client.post(
        APPROVE_URL.format(decision_id=decision["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment.json()["id"])
    await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")

    result = await pilot_product_analyst.roi(db_session, workspace_id=WORKSPACE)
    assert result["revenue_impact"] is None
    assert result["margin_impact"] is None
    assert result["roas_impact"] is None
    assert result["total_experiments"] == 1
    assert result["note"]  # explicit note that impacts are not simulated
    assert result["total_llm_cost"] == "0"  # deterministic path: no LLM cost


# --------------------------------------------------------------------------- #
# Security / PII + workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pilot_context_and_events_never_leak_pii(db_session, api_client, monkeypatch) -> None:
    """Context snapshot, prompt and events carry no PII fields."""
    product_id = await _seed_and_intake(db_session, api_client)
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-pii-1",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )

    runs = (
        (
            await db_session.execute(
                select(ProductAnalysisRun).where(ProductAnalysisRun.provider != "deterministic")
            )
        )
        .scalars()
        .all()
    )
    assert len(runs) == 1
    snapshot = json.dumps(runs[0].input_snapshot)
    blocked = (
        "email",
        "phone",
        "address",
        "api_key",
        "password",
        "credential",
        "card_number",
        "cvv",
    )
    lowered = snapshot.lower()
    for token in blocked:
        assert token not in lowered, f"PII token {token!r} leaked into input_snapshot"

    events = (await db_session.execute(select(EventLog))).scalars().all()
    for event in events:
        payload = json.dumps(event.payload or {}).lower()
        for token in blocked:
            assert token not in payload, f"PII token {token!r} leaked into {event.event_type}"


@pytest.mark.asyncio
async def test_pilot_workspace_isolation_end_to_end(db_session, api_client) -> None:
    """A pilot in workspace A never influences workspace B statistics."""
    product_a = await _seed_and_intake(db_session, api_client)
    decision_a = await _propose_decision(api_client, product_a)
    api_client.post(
        APPROVE_URL.format(decision_id=decision_a["id"]),
        json={"actor": "cto@nuotao.example"},
    )
    experiment_a = await _propose_experiment(api_client, UUID(decision_a["id"]))
    experiment_id = UUID(experiment_a.json()["id"])
    await _start(api_client, experiment_id, started_by="cto@nuotao.example")
    await _complete(api_client, experiment_id, roas="2.00", margin_rate="0.35")
    await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-ws-a"
    )

    # Workspace B: no experiments, no evaluations, no calibration runs.
    assert (
        await db_session.execute(
            select(ProductExperiment).where(ProductExperiment.workspace_id == OTHER_WORKSPACE)
        )
    ).scalars().all() == []
    assert (
        await db_session.execute(
            select(ProductAiEvaluation).where(ProductAiEvaluation.workspace_id == OTHER_WORKSPACE)
        )
    ).scalars().all() == []
    assert (
        await db_session.execute(
            select(ProductScoreCalibrationRun).where(
                ProductScoreCalibrationRun.workspace_id == OTHER_WORKSPACE
            )
        )
    ).scalars().all() == []
