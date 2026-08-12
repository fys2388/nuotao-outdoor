"""Tests for M2.3 Product Analyst Learning Loop.

Covers: prediction calibration classification, confidence calibration report,
score weight suggestion, approval protection (no auto rule changes) and
knowledge memory retrieval.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product_intelligence import (
    ConfidenceCalibration,
    ProductAnalysisRun,
    ProductKnowledgeEntry,
)
from app.models.rule import Rule
from app.schemas.calibration import CalibrationApproveRequest
from app.schemas.knowledge import KnowledgeEntryCreate
from app.schemas.product_analyst import EvaluationCreate
from app.schemas.product_intelligence import (
    ExperimentCompleteRequest,
    ExperimentStartRequest,
)
from app.schemas.rule import RuleCreate
from app.services import (
    ai_evaluation,
    calibration,
    knowledge,
    rule_engine,
)
from app.services import (
    product_intelligence as pi,
)
from sqlalchemy import func, select

WORKSPACE = DEFAULT_WORKSPACE_ID
INTAKE_URL = "/api/v1/products/intake"

# Reference weights as shipped in score-model-v1 (must never be auto-modified).
REFERENCE_WEIGHTS = {
    "profit": Decimal("0.30"),
    "logistics": Decimal("0.20"),
    "demand": Decimal("0.15"),
    "competition": Decimal("0.10"),
    "differentiation": Decimal("0.15"),
    "compliance": Decimal("0.10"),
}


async def _seed_product_rules(db_session) -> None:
    """Seed the PRODUCT gates used by the deterministic scoring chain."""
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
            when_conditions={"field": "logistics.shipping_ratio", "op": "lte", "value": 0.4},
            then_result={"passed_message": "ship ok", "failed_message": "ship too high"},
        ),
    ):
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=rule)


def _intake_payload(sku: str, **overrides) -> dict:
    payload = {
        "title": f"Product {sku}",
        "sku": sku,
        "source_type": "1688",
        "source_url": f"https://detail.1688.com/offer/{sku}.html",
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


async def _intake(api_client, sku: str, **overrides) -> UUID:
    response = api_client.post(INTAKE_URL, json=_intake_payload(sku, **overrides))
    assert response.status_code == 201
    return UUID(response.json()["product"]["id"])


async def _complete_experiment(
    db_session, product_id: UUID, *, roas: str, revenue: str = "400.00"
) -> None:
    """Run the full experiment loop: proposed -> active -> completed."""
    experiment = await pi.propose_experiment(
        db_session, workspace_id=WORKSPACE, product_id=product_id
    )
    await pi.start_experiment(
        db_session,
        workspace_id=WORKSPACE,
        experiment_id=experiment.id,
        data=ExperimentStartRequest(
            quantity=30,
            channels=["meta"],
            budget=Decimal("300.00"),
            targets={"roas": Decimal("2.0")},
        ),
    )
    await pi.complete_experiment(
        db_session,
        workspace_id=WORKSPACE,
        experiment_id=experiment.id,
        data=ExperimentCompleteRequest(
            units_sold=12,
            revenue=Decimal(revenue),
            orders=11,
            conversion_rate=Decimal("0.03"),
            roas=Decimal(roas),
            return_rate=Decimal("0.05"),
            margin_rate=Decimal("0.30"),
            actor="tester",
            source="manual",
        ),
    )


async def _make_analysis_run(
    db_session, product_id: UUID, *, confidence: str, decision: str = "test"
) -> UUID:
    """Create a minimal analysis-run audit row carrying a prediction."""
    run = ProductAnalysisRun(
        workspace_id=WORKSPACE,
        product_id=product_id,
        provider="openai",
        model="gpt-4o-mini",
        prompt_version="v1",
        input_snapshot={"product_id": str(product_id)},
        output={
            "decision": decision,
            "confidence": confidence,
            "pricing": {"recommended_price": "39.99"},
            "test_plan": {"kpis": {"roas": 2.0}},
        },
        token_usage={"total_tokens": 100},
        estimated_cost=Decimal("0.0005"),
        latency_ms=50,
        status="completed",
        trace_id="learning-loop-test",
    )
    db_session.add(run)
    await db_session.flush()
    return run.id


# --------------------------------------------------------------------------- #
# 1. Prediction calibration
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_prediction_calibration_classification(db_session, api_client) -> None:
    """Evaluations classify success/failure with bucket, error type, metrics."""
    await _seed_product_rules(db_session)
    product_id = await _intake(api_client, "NTO-CAL-001")
    run_id = await _make_analysis_run(db_session, product_id, confidence="0.78", decision="test")

    # Decision matches -> success.
    success = await ai_evaluation.record_evaluation(
        db_session,
        workspace_id=WORKSPACE,
        data=EvaluationCreate(
            product_id=product_id,
            analysis_run_id=run_id,
            actual_result={"decision": "test", "roas": "0.8"},
        ),
        trace_id="t1",
    )
    assert success.prediction_result == "success"
    assert success.success_flag is True
    assert success.error_type is None
    assert success.confidence_bucket == "HIGH"  # 0.78 > 0.7
    assert success.metric_snapshot["decision_match"] is True
    assert success.metric_snapshot["predicted_decision"] == "test"
    assert success.metric_snapshot["actual_decision"] == "test"

    # Decision mismatch -> failure with decision_mismatch error type.
    mismatch = await ai_evaluation.record_evaluation(
        db_session,
        workspace_id=WORKSPACE,
        data=EvaluationCreate(
            product_id=product_id,
            analysis_run_id=run_id,
            actual_result={"decision": "reject"},
        ),
        trace_id="t2",
    )
    assert mismatch.prediction_result == "failure"
    assert mismatch.success_flag is False
    assert mismatch.error_type == "decision_mismatch"

    # No decision signal, roas below 1 -> metric_miss.
    miss = await ai_evaluation.record_evaluation(
        db_session,
        workspace_id=WORKSPACE,
        data=EvaluationCreate(
            product_id=product_id,
            analysis_run_id=run_id,
            actual_result={"roas": "0.5"},
        ),
        trace_id="t3",
    )
    assert miss.prediction_result == "failure"
    assert miss.error_type == "metric_miss"


# --------------------------------------------------------------------------- #
# 2. Confidence calibration report
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_confidence_calibration_report(db_session, api_client) -> None:
    """The report aggregates buckets into success rates + avg confidence."""
    await _seed_product_rules(db_session)
    product_id = await _intake(api_client, "NTO-CAL-002")

    high_success_run = await _make_analysis_run(db_session, product_id, confidence="0.80")
    high_failure_run = await _make_analysis_run(db_session, product_id, confidence="0.85")
    low_success_run = await _make_analysis_run(db_session, product_id, confidence="0.40")
    for run_id, actual in (
        (high_success_run, {"decision": "test"}),
        (high_failure_run, {"decision": "reject"}),
        (low_success_run, {"decision": "test"}),
    ):
        await ai_evaluation.record_evaluation(
            db_session,
            workspace_id=WORKSPACE,
            data=EvaluationCreate(
                product_id=product_id,
                analysis_run_id=run_id,
                actual_result=actual,
            ),
            trace_id="report",
        )

    report = await calibration.generate_confidence_report(
        db_session, workspace_id=WORKSPACE, trace_id="report"
    )
    by_bucket = {row.bucket: row for row in report}
    assert set(by_bucket) == {"LOW", "MEDIUM", "HIGH"}

    high = by_bucket["HIGH"]
    assert high.sample_count == 2
    assert high.success_count == 1
    assert high.success_rate == Decimal("0.5000")
    assert high.avg_confidence == Decimal("0.8250")
    low = by_bucket["LOW"]
    assert low.sample_count == 1
    assert low.success_rate == Decimal("1.0000")
    assert low.avg_confidence == Decimal("0.4000")
    assert by_bucket["MEDIUM"].sample_count == 0

    # Rows are upserted: regenerating keeps one row per bucket.
    await calibration.generate_confidence_report(db_session, workspace_id=WORKSPACE)
    rows = (await db_session.execute(select(ConfidenceCalibration))).scalars().all()
    assert len(rows) == 3


# --------------------------------------------------------------------------- #
# 3. Score model calibration (weight suggestion)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_score_calibration_weight_suggestion(db_session, api_client) -> None:
    """Completed experiments drive a deterministic, normalized weight proposal."""
    await _seed_product_rules(db_session)
    # 3 successes on known-cost products + 1 failure on an unknown-cost product.
    successful = [await _intake(api_client, f"NTO-W-00{i}") for i in range(1, 4)]
    failed = await _intake(
        api_client,
        "NTO-W-004",
        purchase_cost="0.00",
        domestic_shipping="0.00",
        first_leg_shipping="0.00",
        last_leg_shipping="0.00",
    )
    for product_id in successful:
        await _complete_experiment(db_session, product_id, roas="1.8")
    await _complete_experiment(db_session, failed, roas="0.4")

    run = await calibration.run_score_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="cal-run"
    )
    assert run.status == "proposed"
    assert run.model_version == "score-model-v1"
    assert run.sample_size == 4
    assert "insufficient" not in (run.rationale or "")

    suggested = {key: Decimal(value) for key, value in run.suggested_weights.items()}
    assert set(suggested) == set(REFERENCE_WEIGHTS)
    assert sum(suggested.values()) == Decimal("1.00")
    # Profit evidence confidence is higher on successes -> profit weight rises.
    assert suggested["profit"] > REFERENCE_WEIGHTS["profit"]
    # Failure (unknown-cost) product drags demand evidence -> demand drops.
    assert suggested["demand"] < REFERENCE_WEIGHTS["demand"]
    assert "profit" in run.metrics
    assert run.metrics["profit"]["n_success"] == 3
    assert run.metrics["profit"]["n_failure"] == 1


@pytest.mark.asyncio
async def test_score_calibration_insufficient_samples(db_session, api_client) -> None:
    """Fewer than 3 experiments leaves the weights unchanged."""
    await _seed_product_rules(db_session)
    product_id = await _intake(api_client, "NTO-W-010")
    await _complete_experiment(db_session, product_id, roas="1.5")

    run = await calibration.run_score_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="cal-run"
    )
    assert run.sample_size == 1
    assert run.suggested_weights == run.current_weights
    assert "insufficient" in (run.rationale or "")


# --------------------------------------------------------------------------- #
# 4. Approval protection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_approval_protection_never_auto_modifies_rules(db_session, api_client) -> None:
    """Approving a proposal records the decision; rules/code stay untouched."""
    await _seed_product_rules(db_session)
    successful = [await _intake(api_client, f"NTO-AP-00{i}") for i in range(1, 4)]
    for product_id in successful:
        await _complete_experiment(db_session, product_id, roas="1.7")

    rule_count_before = (
        await db_session.execute(select(func.count()).select_from(Rule))
    ).scalar_one()

    run = await calibration.run_score_calibration(db_session, workspace_id=WORKSPACE, trace_id="ap")
    approved = await calibration.approve_calibration(
        db_session,
        workspace_id=WORKSPACE,
        run_id=run.id,
        data=CalibrationApproveRequest(
            actor="owner@nuotao.example", note="approved for v2 rollout"
        ),
        trace_id="ap",
    )
    assert approved.status == "approved"
    assert approved.approved_by == "owner@nuotao.example"
    assert approved.approved_at is not None

    # No rule rows were added/modified.
    rule_count_after = (
        await db_session.execute(select(func.count()).select_from(Rule))
    ).scalar_one()
    assert rule_count_after == rule_count_before

    # The shipped score weights are unchanged (version update is human work).
    from app.services.product_intelligence import SCORE_WEIGHTS

    assert SCORE_WEIGHTS == {key: float(value) for key, value in REFERENCE_WEIGHTS.items()}

    # Re-approval is rejected; a second run can be rejected.
    from app.services.calibration import CalibrationError

    with pytest.raises(CalibrationError):
        await calibration.approve_calibration(
            db_session,
            workspace_id=WORKSPACE,
            run_id=run.id,
            data=CalibrationApproveRequest(actor="other@nuotao.example"),
        )

    second = await calibration.run_score_calibration(
        db_session, workspace_id=WORKSPACE, trace_id="ap-2"
    )
    rejected = await calibration.reject_calibration(
        db_session,
        workspace_id=WORKSPACE,
        run_id=second.id,
        data=CalibrationApproveRequest(actor="owner@nuotao.example", note="not now"),
    )
    assert rejected.status == "rejected"


# --------------------------------------------------------------------------- #
# 5. Knowledge memory
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_knowledge_retrieval(db_session, api_client) -> None:
    """Knowledge entries are queryable by category/product/type."""
    await _seed_product_rules(db_session)
    product_id = await _intake(api_client, "NTO-K-001")

    await knowledge.create_knowledge_entry(
        db_session,
        workspace_id=WORKSPACE,
        data=KnowledgeEntryCreate(
            product_id=product_id,
            category="headlamp",
            entry_type="success_pattern",
            title="Light weight wins",
            content="Sub-300g headlamps convert at 3x the category average.",
            tags=["lightweight", "US"],
            source="evaluation",
        ),
        trace_id="k1",
    )
    await knowledge.create_knowledge_entry(
        db_session,
        workspace_id=WORKSPACE,
        data=KnowledgeEntryCreate(
            category="headlamp",
            entry_type="failure_pattern",
            title="Heavy battery fails",
            content="Rechargeable units over 200g underperform on paid channels.",
            tags=["weight"],
            source="manual",
        ),
        trace_id="k2",
    )
    await knowledge.create_knowledge_entry(
        db_session,
        workspace_id=WORKSPACE,
        data=KnowledgeEntryCreate(
            category="backpack",
            entry_type="category_insight",
            title="Backpack seasonality",
            content="Trail pack demand peaks in spring in DE/EU.",
            tags=["EU", "seasonality"],
            source="manual",
        ),
        trace_id="k3",
    )

    by_category = await knowledge.list_knowledge_entries(
        db_session, workspace_id=WORKSPACE, category="headlamp"
    )
    assert len(by_category) == 2

    by_product = await knowledge.list_knowledge_entries(
        db_session, workspace_id=WORKSPACE, product_id=product_id
    )
    assert len(by_product) == 1
    assert by_product[0].entry_type == "success_pattern"

    by_type = await knowledge.list_knowledge_entries(
        db_session, workspace_id=WORKSPACE, entry_type="category_insight"
    )
    assert len(by_type) == 1
    assert by_type[0].category == "backpack"

    all_rows = (await db_session.execute(select(ProductKnowledgeEntry))).scalars().all()
    assert len(all_rows) == 3
