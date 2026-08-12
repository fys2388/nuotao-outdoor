"""M5.7 Product Analyst Real Business Validation tests.

Focuses on the NEW M5.7 guarantees on top of the M5.6 loop:

- dry-run validates ``context -> LLM -> schema -> gates`` with zero writes
- provider pinning (openai / deepseek) and fallback responses reach the run
- ``actual_result`` requires an explicit provenance (manual/external/
  connector; ``ai``/``predicted`` are rejected) and stays append-only
- insufficient calibration samples are explicitly flagged, never auto-applied
- rejected calibration can never sync knowledge
- validation cases distinguish real vs synthetic data
- scorecard exposes M5.7 runtime metrics; ROI stays null without attribution
- readiness gate reports BLOCKED items instead of fabricating success
- workspace isolation + PII guards hold on the new paths
"""

import json
from decimal import Decimal
from uuid import UUID

import pytest
from app.agents import product_analyst
from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_operations import AgentApproval
from app.models.event import EventLog
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductDecision,
    ProductExperiment,
    ProductKnowledgeEntry,
    ProductScoreCalibrationRun,
)
from app.services import (
    calibration,
    evaluation_bridge,
    pilot_product_analyst,
    validation_dataset,
)
from app.services.llm_gateway import LLMResponse
from sqlalchemy import select

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")

INTAKE_URL = "/api/v1/products/intake"
DECISIONS_URL = "/api/v1/products/{product_id}/decisions"
APPROVE_URL = "/api/v1/product-decisions/{decision_id}/approve"
EXPERIMENT_URL = "/api/v1/product-decisions/{decision_id}/experiment"
START_URL = "/api/v1/product-decisions/experiments/{experiment_id}/start"
COMPLETE_URL = "/api/v1/product-decisions/experiments/{experiment_id}/complete"

BLOCKED_PII = (
    "email",
    "phone",
    "address",
    "api_key",
    "password",
    "credential",
    "card_number",
    "cvv",
)


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Camping Headlamp M57",
        "sku": "NTO-HEADLAMP-M57",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/987654321.html",
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


async def _seed(db_session, *, workspace: UUID = WORKSPACE) -> None:
    from app.agents.agent_seed import ensure_product_analyst_agent

    await ensure_product_analyst_agent(db_session, workspace_id=workspace)


async def _intake(api_client, *, workspace: UUID = WORKSPACE, sku: str | None = None) -> UUID:
    payload = _intake_payload()
    if sku:
        payload["sku"] = sku
    response = api_client.post(INTAKE_URL, json=payload, headers=_headers(workspace))
    assert response.status_code == 201, response.text
    return UUID(response.json()["product"]["id"])


async def _propose_decision(api_client, product_id: UUID, *, workspace: UUID = WORKSPACE) -> dict:
    response = api_client.post(
        DECISIONS_URL.format(product_id=product_id), headers=_headers(workspace)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _approve_decision(
    api_client, decision_id: UUID, *, actor: str = "cto@nuotao.example"
) -> None:
    response = api_client.post(
        APPROVE_URL.format(decision_id=decision_id),
        json={"actor": actor, "note": "approved in M5.7 test"},
    )
    assert response.status_code == 200, response.text


async def _propose_experiment(api_client, decision_id: UUID) -> dict:
    response = api_client.post(
        EXPERIMENT_URL.format(decision_id=decision_id), json={"note": "market test"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _start_experiment(api_client, experiment_id: UUID) -> None:
    response = api_client.post(
        START_URL.format(experiment_id=experiment_id),
        json={
            "quantity": 30,
            "channels": ["meta"],
            "budget": "300.00",
            "targets": {"roas": 1.0, "margin_rate": 0.30},
            "started_by": "cto@nuotao.example",
        },
    )
    assert response.status_code == 200, response.text


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


async def _complete_experiment_row(
    db_session, *, product_id: UUID, workspace: UUID = WORKSPACE, roas: str = "2.0"
) -> ProductExperiment:
    """Insert a completed experiment row directly (fast calibration seed)."""
    row = ProductExperiment(
        workspace_id=workspace,
        product_id=product_id,
        status="completed",
        experiment_type="market_test",
        prediction={"decision": "test", "confidence": "0.78"},
        experiment={"targets": {"roas": 1.0}},
        actual_result={
            "decision": "test",
            "roas": roas,
            "margin_rate": "0.30",
            "source": "manual",
            "actor": "tester",
        },
        calibration={},
        trace_id=f"trace-exp-{product_id}",
    )
    db_session.add(row)
    await db_session.flush()
    return row


# --------------------------------------------------------------------------- #
# Dry-run vs real run (zero writes vs pending proposal)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dry_run_validates_without_persisting(db_session, api_client, monkeypatch) -> None:
    """Dry-run executes context -> LLM -> schema -> gates with no DB rows."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))

    result = await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-dry-run-1",
        prompt_name="AGENT_PRODUCT_ANALYST",
        persist=False,
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.output is not None
    assert result.output.decision == "test"
    assert result.analysis_run is None
    assert result.decision is None

    # Intake runs a deterministic M2.2 chain; no LLM analysis run may exist.
    llm_runs = (
        (
            await db_session.execute(
                select(ProductAnalysisRun).where(ProductAnalysisRun.provider != "deterministic")
            )
        )
        .scalars()
        .all()
    )
    assert llm_runs == []
    assert (await db_session.execute(select(ProductDecision))).scalars().all() == []
    assert (await db_session.execute(select(AgentApproval))).scalars().all() == []
    # Dry-run writes no events under its own trace.
    dry_events = (
        (await db_session.execute(select(EventLog).where(EventLog.trace_id == "trace-dry-run-1")))
        .scalars()
        .all()
    )
    assert dry_events == []


@pytest.mark.asyncio
async def test_dry_run_invalid_schema_writes_nothing(db_session, api_client, monkeypatch) -> None:
    """A schema failure during dry-run raises without writing audit rows."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    bad = dict(VALID_OUTPUT)
    bad["decision"] = "launch_now"  # not a valid enum member
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(bad))

    with pytest.raises(product_analyst.ProductAnalystError):
        await product_analyst.analyze_product(
            db_session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            trace_id="trace-dry-bad",
            prompt_name="AGENT_PRODUCT_ANALYST",
            persist=False,
            dry_run=True,
        )
    llm_runs = (
        (
            await db_session.execute(
                select(ProductAnalysisRun).where(ProductAnalysisRun.provider != "deterministic")
            )
        )
        .scalars()
        .all()
    )
    assert llm_runs == []
    assert (await db_session.execute(select(ProductDecision))).scalars().all() == []
    bad_events = (
        (await db_session.execute(select(EventLog).where(EventLog.trace_id == "trace-dry-bad")))
        .scalars()
        .all()
    )
    assert bad_events == []


@pytest.mark.asyncio
async def test_real_run_creates_pending_decision_and_run(
    db_session,
    api_client,
    monkeypatch,
) -> None:
    """A real run persists the audit run + a pending decision proposal."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))

    result = await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-real-run-1",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )
    assert result.dry_run is False
    assert result.analysis_run is not None and result.analysis_run.status == "completed"
    assert result.decision is not None and result.decision.approval_status == "pending"
    assert result.output is not None

    run = (
        await db_session.execute(
            select(ProductAnalysisRun).where(ProductAnalysisRun.trace_id == "trace-real-run-1")
        )
    ).scalar_one()
    assert run.provider == "openai"
    assert run.input_snapshot  # JSON-safe context snapshot
    assert run.output.get("enforced_decision") is None

    approval = (
        await db_session.execute(
            select(AgentApproval).where(
                AgentApproval.approval_type == "PRODUCT_DECISION",
                AgentApproval.entity_id == str(result.decision.id),
            )
        )
    ).scalar_one()
    assert approval.status == "pending"
    events = (await db_session.execute(select(EventLog))).scalars().all()
    proposed = [e for e in events if e.event_type == "agent.product_decision.proposed"]
    assert proposed
    assert all(e.trace_id == "trace-real-run-1" for e in proposed)


# --------------------------------------------------------------------------- #
# Provider pinning + fallback response
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_provider_pinned_deepseek_recorded_on_run(
    db_session,
    api_client,
    monkeypatch,
) -> None:
    """A pinned DeepSeek call records provider/model on the analysis run."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    monkeypatch.setattr(
        product_analyst.llm_gateway,
        "complete",
        _fake_complete(VALID_OUTPUT, provider="deepseek"),
    )
    await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-pin-ds",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )
    run = (
        await db_session.execute(
            select(ProductAnalysisRun).where(ProductAnalysisRun.trace_id == "trace-pin-ds")
        )
    ).scalar_one()
    assert run.provider == "deepseek"


@pytest.mark.asyncio
async def test_fallback_response_deepseek_accepted_by_agent(
    db_session,
    api_client,
    monkeypatch,
) -> None:
    """A caller that fell back from OpenAI to DeepSeek persists the provider."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    monkeypatch.setattr(
        product_analyst.llm_gateway,
        "complete",
        _fake_complete(VALID_OUTPUT, provider="deepseek"),
    )
    await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-fallback-1",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )
    run = (
        await db_session.execute(
            select(ProductAnalysisRun).where(ProductAnalysisRun.trace_id == "trace-fallback-1")
        )
    ).scalar_one()
    assert run.provider == "deepseek"


# --------------------------------------------------------------------------- #
# Actual result provenance + append-only history
# --------------------------------------------------------------------------- #


async def _active_experiment(api_client, *, workspace: UUID = WORKSPACE) -> UUID:
    product_id = await _intake(api_client, workspace=workspace)
    decision = await _propose_decision(api_client, product_id, workspace=workspace)
    await _approve_decision(api_client, UUID(decision["id"]))
    experiment = await _propose_experiment(api_client, UUID(decision["id"]))
    experiment_id = UUID(experiment["id"])
    await _start_experiment(api_client, experiment_id)
    return experiment_id


@pytest.mark.asyncio
async def test_complete_requires_actor_and_source(db_session, api_client) -> None:
    """Backfilling an experiment result requires actor + explicit source."""
    await _seed(db_session)
    experiment_id = await _active_experiment(api_client)

    no_source = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json={"units_sold": 10, "revenue": "400.00", "actor": "tester"},
    )
    assert no_source.status_code == 400, no_source.text
    assert "source" in no_source.text

    no_actor = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json={"units_sold": 10, "revenue": "400.00", "source": "manual"},
    )
    assert no_actor.status_code == 400, no_actor.text
    assert "actor" in no_actor.text


@pytest.mark.asyncio
async def test_complete_rejects_predicted_or_ai_source(db_session, api_client) -> None:
    """A model prediction can never be an actual_result source."""
    await _seed(db_session)
    experiment_id = await _active_experiment(api_client)
    response = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json={
            "units_sold": 10,
            "revenue": "400.00",
            "actor": "tester",
            "source": "predicted",
        },
    )
    assert response.status_code in (400, 422), response.text


@pytest.mark.asyncio
async def test_complete_result_history_append_only(db_session, api_client) -> None:
    """The first result is recorded; a later observation appends, never overwrites."""
    await _seed(db_session)
    experiment_id = await _active_experiment(api_client)

    first = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json={
            "units_sold": 10,
            "revenue": "400.00",
            "orders": 8,
            "actor": "tester",
            "source": "manual",
        },
    )
    assert first.status_code == 200, first.text
    experiment = (
        await db_session.execute(
            select(ProductExperiment).where(ProductExperiment.id == experiment_id)
        )
    ).scalar_one()
    assert experiment.status == "completed"
    assert experiment.actual_result["source"] == "manual"
    assert experiment.actual_result["actor"] == "tester"
    assert experiment.actual_result["observed_at"]
    assert len(experiment.result_history) == 1
    first_actual = dict(experiment.actual_result)

    # Force a second observation (operator correction) - history must grow.
    experiment.status = "active"
    await db_session.flush()
    second = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json={
            "units_sold": 12,
            "revenue": "480.00",
            "orders": 10,
            "actor": "cto@nuotao.example",
            "source": "external",
        },
    )
    assert second.status_code == 200, second.text
    await db_session.refresh(experiment)
    assert experiment.actual_result["source"] == "external"
    assert experiment.actual_result["units_sold"] == 12
    assert len(experiment.result_history) == 2
    # The first observation is preserved verbatim in history.
    assert dict(experiment.result_history[0]) == first_actual
    assert experiment.result_history[1]["units_sold"] == 12


@pytest.mark.asyncio
async def test_complete_sources_external_and_connector(db_session, api_client) -> None:
    """external and connector are valid provenance sources."""
    await _seed(db_session)
    for source in ("external", "connector"):
        experiment_id = await _active_experiment(api_client)
        response = api_client.post(
            COMPLETE_URL.format(experiment_id=experiment_id),
            json={
                "units_sold": 10,
                "revenue": "400.00",
                "actor": "tester",
                "source": source,
            },
        )
        assert response.status_code == 200, response.text
        experiment = (
            await db_session.execute(
                select(ProductExperiment).where(ProductExperiment.id == experiment_id)
            )
        ).scalar_one()
        assert experiment.actual_result["source"] == source


@pytest.mark.asyncio
async def test_complete_events_carry_trace_and_no_pii(db_session, api_client) -> None:
    """Completion events keep the trace and never carry PII."""
    await _seed(db_session)
    experiment_id = await _active_experiment(api_client)
    response = api_client.post(
        COMPLETE_URL.format(experiment_id=experiment_id),
        json={
            "units_sold": 10,
            "revenue": "400.00",
            "actor": "tester",
            "source": "manual",
            "trace_id": "trace-complete-pii",
        },
    )
    assert response.status_code == 200, response.text
    events = (await db_session.execute(select(EventLog))).scalars().all()
    completed = [
        e
        for e in events
        if e.event_type in ("product.experiment.completed", "agent.experiment.completed")
    ]
    assert completed, "expected experiment completion events"
    traces = {e.trace_id for e in completed}
    assert "trace-complete-pii" in traces
    for event in completed:
        payload = json.dumps(event.payload or {}).lower()
        for token in BLOCKED_PII:
            assert token not in payload, f"PII token {token!r} in {event.event_type}"


# --------------------------------------------------------------------------- #
# Calibration: insufficient sample + rejected can never sync knowledge
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_calibration_insufficient_sample_flagged(db_session, api_client) -> None:
    """Zero or sub-minimum samples are explicitly flagged as insufficient."""
    await _seed(db_session)
    product_id = await _intake(api_client)

    empty = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-0"
    )
    assert empty["skipped"] is True
    assert empty["insufficient_sample"] is True
    assert empty["minimum_required"] == calibration.MIN_CALIBRATION_SAMPLES

    await _complete_experiment_row(db_session, product_id=product_id)
    one = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-1"
    )
    assert one["skipped"] is False
    assert one["insufficient_sample"] is True
    assert one["sample_size"] == 1


@pytest.mark.asyncio
async def test_calibration_enough_samples_proposes(db_session, api_client) -> None:
    """Three completed experiments produce a proposed calibration run."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    for roas in ("2.0", "1.8", "1.5"):
        await _complete_experiment_row(db_session, product_id=product_id, roas=roas)

    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-3"
    )
    assert result["skipped"] is False
    assert result["insufficient_sample"] is False
    assert result["sample_size"] == 3
    assert result["calibration_run"]["status"] == "proposed"
    # SCORE_WEIGHTS are never modified by the proposal.
    from app.services.product_intelligence import SCORE_WEIGHTS

    run = (
        await db_session.execute(
            select(ProductScoreCalibrationRun).where(
                ProductScoreCalibrationRun.id == UUID(result["calibration_run"]["id"])
            )
        )
    ).scalar_one()
    assert run.suggested_weights is not None
    assert dict(SCORE_WEIGHTS) == {
        "profit": 0.30,
        "logistics": 0.20,
        "demand": 0.15,
        "competition": 0.10,
        "differentiation": 0.15,
        "compliance": 0.10,
    }


@pytest.mark.asyncio
async def test_rejected_calibration_cannot_sync_knowledge(db_session, api_client) -> None:
    """Knowledge distillation is impossible from a rejected calibration run."""
    from app.schemas.calibration import CalibrationApproveRequest

    await _seed(db_session)
    product_id = await _intake(api_client)
    await _complete_experiment_row(db_session, product_id=product_id)
    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-rej"
    )
    run_id = UUID(result["calibration_run"]["id"])

    await calibration.reject_calibration(
        db_session,
        workspace_id=WORKSPACE,
        run_id=run_id,
        data=CalibrationApproveRequest(actor="cto@nuotao.example", note="not now"),
        trace_id="trace-calb-rej",
    )
    with pytest.raises(evaluation_bridge.EvaluationBridgeError):
        await evaluation_bridge.sync_calibration_to_knowledge(
            db_session, workspace_id=WORKSPACE, run_id=run_id, trace_id="trace-calb-rej"
        )
    assert (
        await db_session.execute(
            select(ProductKnowledgeEntry).where(ProductKnowledgeEntry.workspace_id == WORKSPACE)
        )
    ).scalars().all() == []


@pytest.mark.asyncio
async def test_approved_calibration_syncs_knowledge_and_second_context(
    db_session,
    api_client,
) -> None:
    """Approved calibration -> knowledge -> visible in the next product context."""
    from app.schemas.calibration import CalibrationApproveRequest
    from app.services import product_context

    await _seed(db_session)
    product_id = await _intake(api_client)
    for roas in ("2.0", "1.8", "1.5"):
        await _complete_experiment_row(db_session, product_id=product_id, roas=roas)
    result = await pilot_product_analyst.run_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="trace-calb-ok"
    )
    run_id = UUID(result["calibration_run"]["id"])
    await calibration.approve_calibration(
        db_session,
        workspace_id=WORKSPACE,
        run_id=run_id,
        data=CalibrationApproveRequest(actor="cto@nuotao.example", note="approved"),
        trace_id="trace-calb-ok",
    )
    entries = await pilot_product_analyst.feedback_knowledge(
        db_session,
        workspace_id=WORKSPACE,
        calibration_run_id=run_id,
        trace_id="trace-fb-ok",
    )
    assert entries, "expected knowledge entries after approved calibration"
    knowledge_rows = (
        (
            await db_session.execute(
                select(ProductKnowledgeEntry).where(ProductKnowledgeEntry.workspace_id == WORKSPACE)
            )
        )
        .scalars()
        .all()
    )
    assert knowledge_rows
    assert any(k.source == "calibration" for k in knowledge_rows)

    context = await product_context.build_product_context(
        db_session, workspace_id=WORKSPACE, product_id=product_id, trace_id="trace-ctx-2"
    )
    knowledge = context.get("knowledge") or []
    assert knowledge, "second product context must include approved knowledge"
    serialized = json.dumps(knowledge)
    assert "success_pattern" in serialized or "failure_pattern" in serialized


# --------------------------------------------------------------------------- #
# Validation dataset (synthetic vs real, workspace isolation)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_validation_case_real_vs_synthetic_distinct(db_session, api_client) -> None:
    """staging_real and staging_synthetic are explicit, filterable sources."""
    product_id = await _intake(api_client)
    real = await validation_dataset.register_case(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        source="staging_real",
        run_id=None,
        trace_id="trace-vc-real",
    )
    synth = await validation_dataset.register_case(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        source="staging_synthetic",
        run_id=None,
        trace_id="trace-vc-synth",
    )
    assert real.source == "staging_real"
    assert synth.source == "staging_synthetic"

    real_cases = await validation_dataset.list_cases(
        db_session, workspace_id=WORKSPACE, source="staging_real"
    )
    assert [c.id for c in real_cases] == [real.id]
    synth_cases = await validation_dataset.list_cases(
        db_session, workspace_id=WORKSPACE, source="staging_synthetic"
    )
    assert [c.id for c in synth_cases] == [synth.id]


@pytest.mark.asyncio
async def test_validation_case_rejects_unknown_source(db_session) -> None:
    with pytest.raises(validation_dataset.ValidationDatasetError):
        await validation_dataset.register_case(
            db_session,
            workspace_id=WORKSPACE,
            product_id=None,
            source="fixture",  # not staging_real / staging_synthetic
            trace_id="trace-vc-bad",
        )


@pytest.mark.asyncio
async def test_validation_case_workspace_isolated(db_session, api_client) -> None:
    product_id = await _intake(api_client)
    await validation_dataset.register_case(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        source="staging_real",
        trace_id="trace-vc-ws",
    )
    cases_b = await validation_dataset.list_cases(db_session, workspace_id=OTHER_WORKSPACE)
    assert cases_b == []


# --------------------------------------------------------------------------- #
# Scorecard / ROI / readiness
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_scorecard_exposes_m57_metrics(db_session, api_client, monkeypatch) -> None:
    """Scorecard includes blocked/waiting/tokens/p95/fallback/calibration."""
    await _seed(db_session)
    product_id = await _intake(api_client)
    monkeypatch.setattr(product_analyst.llm_gateway, "complete", _fake_complete(VALID_OUTPUT))
    await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-sc-1",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )
    monkeypatch.setattr(
        product_analyst.llm_gateway,
        "complete",
        _fake_complete(VALID_OUTPUT, provider="deepseek"),
    )
    await product_analyst.analyze_product(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        trace_id="trace-sc-2",
        prompt_name="AGENT_PRODUCT_ANALYST",
    )

    card = await pilot_product_analyst.scorecard(db_session, workspace_id=WORKSPACE)
    assert card["blocked_runs"] == 0
    assert card["analysis_success"] == 2
    assert card["total_tokens"] >= 180
    assert card["p95_latency_ms"] is not None
    assert card["provider_fallback_rate"] == 0.5
    assert card["experiment_waiting_for_result"] == 0
    assert "calibration" in card and "knowledge" in card


@pytest.mark.asyncio
async def test_scorecard_waiting_for_result_counts_active_experiments(
    db_session,
    api_client,
) -> None:
    """An active (started, not completed) experiment is waiting for a result."""
    await _seed(db_session)
    await _active_experiment(api_client)
    card = await pilot_product_analyst.scorecard(db_session, workspace_id=WORKSPACE)
    assert card["experiment_waiting_for_result"] == 1
    assert card["experiment_completed"] == 0


@pytest.mark.asyncio
async def test_roi_impact_null_without_attribution(db_session, api_client) -> None:
    """ROI stays null and explicitly says attribution is unavailable."""
    await _seed(db_session)
    await _intake(api_client)
    result = await pilot_product_analyst.roi(db_session, workspace_id=WORKSPACE)
    assert result["revenue_impact"] is None
    assert result["margin_impact"] is None
    assert result["roas_impact"] is None
    assert "ROI attribution unavailable" in result["note"]


@pytest.mark.asyncio
async def test_readiness_reports_blocked_llm_keys(monkeypatch) -> None:
    """Missing LLM keys are a BLOCKED readiness item - never fabricated."""
    from app.pilot import readiness

    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    check = readiness._check_llm_keys()
    assert check["status"] == "BLOCKED"
    assert "missing" in check["detail"]


@pytest.mark.asyncio
async def test_readiness_overall_not_ready_when_infra_missing(monkeypatch) -> None:
    """Unreachable DB/Redis + missing keys -> NOT_READY with BLOCKED list."""
    from app.pilot import readiness

    async def blocked_db(workspace_id):
        base = {"status": "BLOCKED", "detail": "database unreachable"}
        return {key: dict(base) for key in readiness.CHECK_IDS if key != "alembic_head"}

    async def blocked_redis():
        return {"status": "BLOCKED", "detail": "redis unreachable"}

    monkeypatch.setattr(readiness, "_db_checks", blocked_db)
    monkeypatch.setattr(readiness, "_check_redis", blocked_redis)
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    result = await readiness.run_checks(WORKSPACE)
    assert result["overall"] == "NOT_READY"
    assert "postgres_migration" in result["blocked"]
    assert "redis" in result["blocked"]
    assert "llm_keys" in result["blocked"]


# --------------------------------------------------------------------------- #
# Workspace isolation on the M5.7 paths
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_validation_and_scorecard_workspace_isolated(db_session, api_client) -> None:
    """Workspace B never sees workspace A validation cases or decisions."""
    product_a = await _intake(api_client, workspace=WORKSPACE)
    await validation_dataset.register_case(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_a,
        source="staging_real",
        trace_id="trace-ws-a",
    )
    assert await validation_dataset.list_cases(db_session, workspace_id=OTHER_WORKSPACE) == []
    card_b = await pilot_product_analyst.scorecard(db_session, workspace_id=OTHER_WORKSPACE)
    assert card_b["analyzed_products"] == 0
    assert card_b["decision_proposed"] == 0
