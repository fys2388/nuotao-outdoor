"""M5.7-REAL: Product Analyst first real business loop on REAL PG + REAL Redis.

These integration tests run the M5.7 closed loop against a real PostgreSQL
(pgserver embedded PG16, migrated to head 0022) and a real Redis server
(auto-resolved binary, fresh instance per test):

1. readiness gate against real infra (LLM keys stay BLOCKED when absent)
2. real-PG Product Analyst dry-run (zero business writes)
3. real-PG Product Analyst run (audit run + pending decision + approval row)
4. real-PG closed loop: run -> human approve -> experiment proposal ->
   human start -> complete(source guard) -> evaluation -> calibration
   sample gate -> human approve -> knowledge -> second context reads the
   approved knowledge

The LLM gateway is mocked (no API keys required); real-LLM tests live in
``test_llm_gateway_integration.py`` and skip without OPENAI/DEEPSEEK keys.
Nothing here auto-approves, auto-starts experiments or fabricates results.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

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
    ProductKnowledgeEntry,
    ProductScoreCalibrationRun,
)
from app.schemas.product_intelligence import (
    ExperimentCompleteRequest,
    ExperimentStartRequest,
)
from app.services import (
    pilot_product_analyst,
    product_intelligence as pi,
)
from tests.integration.runtime_helpers import (
    VALID_OUTPUT,
    factory,
    fake_complete,
    seed_and_intake,
    set_execution_policy,
    set_fast_retry,
)

WORKSPACE = DEFAULT_WORKSPACE_ID


@pytest.fixture()
async def pg_engine(pg_migrated: str):
    """Async engine + migrated real PostgreSQL database for one test."""
    engine = create_async_engine(pg_migrated)
    yield engine
    await engine.dispose()


async def _llm_runs(session) -> list[ProductAnalysisRun]:
    rows = (
        (
            await session.execute(
                select(ProductAnalysisRun).where(ProductAnalysisRun.provider != "deterministic")
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


# --------------------------------------------------------------------------- #
# 1. Readiness gate against real PostgreSQL + real Redis
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_readiness_gate_real_pg_redis(pg_engine, redis_url: str, monkeypatch) -> None:
    """Real PG + Redis make the infrastructure checks PASS; no-key LLM stays BLOCKED."""
    from app.pilot import readiness

    session_factory = factory(pg_engine)
    async with session_factory() as session:
        agent, _ = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", str(pg_engine.url))
    monkeypatch.setattr(settings, "redis_url", redis_url)
    # This integration test pins the no-key scenario: readiness must report
    # BLOCKED and never fabricate a PASS, regardless of a local .env.
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    result = await readiness.run_checks(WORKSPACE)
    checks = result["checks"]
    for key in (
        "alembic_head",
        "toolchain",
        "postgres_migration",
        "redis",
        "worker",
        "scheduler",
        "agent_active",
        "prompt_active",
        "execution_policy",
        "retry_policy",
        "audit",
    ):
        assert checks[key]["status"] == "PASS", f"{key}: {checks[key]}"
    # No API keys in CI -> the LLM gate must be BLOCKED, never fabricated.
    assert checks["llm_keys"]["status"] == "BLOCKED", checks["llm_keys"]
    # The overall gate reflects the missing keys.
    assert result["overall"] == "NOT_READY"


# --------------------------------------------------------------------------- #
# 2. Dry-run on real PG: zero business writes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_product_analyst_dry_run_zero_write_real_pg(pg_engine, monkeypatch) -> None:
    """Dry-run on real PG validates the chain with no DB rows (no decision)."""
    session_factory = factory(pg_engine)
    trace_id = "trace-real-dry-1"
    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)

        result = await product_analyst.analyze_product(
            session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            gateway_complete=fake_complete(VALID_OUTPUT),
            trace_id=trace_id,
            prompt_name="AGENT_PRODUCT_ANALYST",
            persist=False,
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.output is not None and result.output.decision == "test"
        assert result.analysis_run is None
        assert result.decision is None

        assert await _llm_runs(session) == []
        assert (await session.execute(select(ProductDecision))).scalars().all() == []
        assert (await session.execute(select(AgentApproval))).scalars().all() == []
        dry_events = (
            (await session.execute(select(EventLog).where(EventLog.trace_id == trace_id)))
            .scalars()
            .all()
        )
        assert dry_events == []


# --------------------------------------------------------------------------- #
# 3. Real run on real PG: pending decision + approval row + trace
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_product_analyst_run_pending_decision_real_pg(pg_engine, monkeypatch) -> None:
    """A real run on real PG persists audit run + pending decision + approval."""
    session_factory = factory(pg_engine)
    trace_id = "trace-real-run-1"
    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)

        result = await product_analyst.analyze_product(
            session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            gateway_complete=fake_complete(VALID_OUTPUT),
            trace_id=trace_id,
            prompt_name="AGENT_PRODUCT_ANALYST",
        )
        assert result.dry_run is False
        assert result.analysis_run is not None and result.analysis_run.status == "completed"
        assert result.decision is not None and result.decision.approval_status == "pending"

        run = result.analysis_run
        assert run.provider == "openai"
        assert run.input_snapshot  # JSON-safe context snapshot
        assert run.output.get("enforced_decision") is None

        approval = (
            await session.execute(
                select(AgentApproval).where(
                    AgentApproval.approval_type == "PRODUCT_DECISION",
                    AgentApproval.entity_id == str(result.decision.id),
                )
            )
        ).scalar_one()
        assert approval.status == "pending"

        proposed_events = (
            (
                await session.execute(
                    select(EventLog).where(
                        EventLog.event_type == "agent.product_decision.proposed",
                        EventLog.trace_id == trace_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert proposed_events


# --------------------------------------------------------------------------- #
# 4. Closed loop on real PG: run -> approve -> experiment -> start -> complete
#    -> evaluation -> calibration gate -> approve -> knowledge -> second context
# --------------------------------------------------------------------------- #


async def _complete_experiment_row(session, *, product_id) -> ProductExperiment:
    """Insert one completed experiment row (historical sample for calibration)."""
    row = ProductExperiment(
        workspace_id=WORKSPACE,
        product_id=product_id,
        status="completed",
        experiment_type="market_test",
        prediction={"decision": "test", "confidence": "0.78"},
        experiment={"targets": {"roas": 1.0}},
        actual_result={
            "decision": "test",
            "roas": "1.8",
            "margin_rate": "0.30",
            "source": "manual",
            "actor": "tester",
        },
        calibration={},
        trace_id=f"trace-hist-{product_id}",
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_closed_loop_second_context_knowledge_real_pg(pg_engine, monkeypatch) -> None:
    """Full M5.7 loop on real PG; second context reads the approved knowledge."""
    session_factory = factory(pg_engine)
    trace_id = "trace-real-loop-1"
    async with session_factory() as session:
        agent, product_id = await seed_and_intake(session)
        await set_fast_retry(session)
        await set_execution_policy(session, agent_id=agent.id)

        # 1. analysis -> pending decision
        result = await product_analyst.analyze_product(
            session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            gateway_complete=fake_complete(VALID_OUTPUT),
            trace_id=trace_id,
            prompt_name="AGENT_PRODUCT_ANALYST",
        )
        decision = result.decision
        assert decision is not None and decision.approval_status == "pending"

        # 2. human approval (agent can never do this)
        await pi.approve_decision(
            session,
            workspace_id=WORKSPACE,
            decision_id=decision.id,
            actor="cto@nuotao.example",
            trace_id=trace_id,
        )

        # 3. experiment proposal (first gate passed)
        experiment = await pi.propose_experiment_for_decision(
            session,
            workspace_id=WORKSPACE,
            decision_id=decision.id,
            trace_id=trace_id,
        )
        assert experiment.status == "proposed"
        assert experiment.decision_id == decision.id
        assert experiment.source_trace_id == trace_id

        # 4. human start (second gate)
        await pi.start_experiment(
            session,
            workspace_id=WORKSPACE,
            experiment_id=experiment.id,
            data=ExperimentStartRequest(
                quantity=30,
                channels=["meta"],
                budget=Decimal("300.00"),
                targets={"roas": 1.0},
                started_by="cto@nuotao.example",
            ),
            trace_id=trace_id,
        )
        assert experiment.status == "active"

        # 5. complete with explicit source (never ai/predicted)
        completed = await pilot_product_analyst.complete_experiment_with_evaluation(
            session,
            workspace_id=WORKSPACE,
            experiment_id=experiment.id,
            data=ExperimentCompleteRequest(
                units_sold=40,
                revenue=Decimal("1600.00"),
                orders=32,
                roas=Decimal("2.00"),
                margin_rate=Decimal("0.35"),
                actor="cto@nuotao.example",
                source="manual",
            ),
            trace_id=trace_id,
        )
        assert completed.status == "completed"
        assert completed.actual_result["source"] == "manual"
        assert len(completed.result_history) >= 1

        evaluations = (
            (
                await session.execute(
                    select(ProductAiEvaluation).where(
                        ProductAiEvaluation.workspace_id == WORKSPACE,
                        ProductAiEvaluation.product_id == product_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert evaluations, "expected an evaluation row after completion"

        # 6. calibration sample gate: 1 real sample -> insufficient
        calibration = await pilot_product_analyst.run_calibration(
            session, workspace_id=WORKSPACE, trace_id=trace_id
        )
        assert calibration["insufficient_sample"] is True

        # top up to 3 historical samples -> proposed run (never auto-approved)
        for _ in range(2):
            await _complete_experiment_row(session, product_id=product_id)
        calibration = await pilot_product_analyst.run_calibration(
            session, workspace_id=WORKSPACE, trace_id=trace_id
        )
        assert calibration["insufficient_sample"] is False
        run_id = UUID(calibration["calibration_run"]["id"])
        run_row = (
            await session.execute(
                select(ProductScoreCalibrationRun).where(ProductScoreCalibrationRun.id == run_id)
            )
        ).scalar_one()
        assert run_row.status == "proposed"

        # 7. human approve calibration -> knowledge (source=calibration)
        from app.schemas.calibration import CalibrationApproveRequest
        from app.services import calibration as calibration_service

        await calibration_service.approve_calibration(
            session,
            workspace_id=WORKSPACE,
            run_id=run_id,
            data=CalibrationApproveRequest(actor="cto@nuotao.example", note="approved"),
            trace_id=trace_id,
        )
        entries = await pilot_product_analyst.feedback_knowledge(
            session,
            workspace_id=WORKSPACE,
            calibration_run_id=run_id,
            trace_id=trace_id,
        )
        assert entries
        knowledge_rows = (
            (
                await session.execute(
                    select(ProductKnowledgeEntry).where(
                        ProductKnowledgeEntry.workspace_id == WORKSPACE
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(k.source == "calibration" for k in knowledge_rows)

        # 8. second context must contain the approved knowledge
        from app.services import product_context

        context = await product_context.build_product_context(
            session,
            workspace_id=WORKSPACE,
            product_id=product_id,
            trace_id="trace-real-ctx-2",
        )
        knowledge = context.get("knowledge") or []
        assert knowledge, "second context must include approved knowledge"
        assert any(
            "success_pattern" in json.dumps(k) or "failure_pattern" in json.dumps(k)
            for k in knowledge
        )
