"""Tests for M2.1 product intelligence foundation.

Covers product source capture, append-only cost snapshots, score persistence,
analysis audit rows, decision workflow (state machine), intake validation and
deterministic scoring.
"""

from decimal import Decimal

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import ProductCost
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductCostSnapshot,
    ProductScore,
    ProductSource,
)
from app.schemas.rule import RuleCreate
from app.services import rule_engine
from sqlalchemy import func, select

WORKSPACE = DEFAULT_WORKSPACE_ID
INTAKE_URL = "/api/v1/products/intake"


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Camping Headlamp Pro",
        "sku": "NTO-HEADLAMP-001",
        "description": "USB rechargeable 300lm headlamp",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/123456789.html",
        "supplier_code": None,
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
    """Seed the deterministic PRODUCT gates (same shape as migration 0004)."""
    rules = [
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
    ]
    for data in rules:
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=data)


@pytest.mark.asyncio
async def test_intake_creates_source_cost_score_and_audit(db_session, api_client) -> None:
    """A valid intake creates product + source + snapshot + score + analysis."""
    await _seed_product_rules(db_session)
    response = api_client.post(INTAKE_URL, json=_intake_payload())
    assert response.status_code == 201
    result = response.json()
    assert result["product"]["sku"] == "NTO-HEADLAMP-001"
    assert result["product"]["status"] == "candidate"
    assert result["product"]["weight_kg"] == "0.30"
    assert result["product"]["dimensions"] == {"length": 8, "width": 5, "height": 4}
    assert result["product"]["target_market"] == "US"

    # Product source captured with type/url/raw_data.
    sources = (await db_session.execute(select(ProductSource))).scalars().all()
    assert len(sources) == 1
    source = sources[0]
    assert source.source_type == "1688"
    assert source.source_url == "https://detail.1688.com/offer/123456789.html"
    assert source.raw_data["purchase_cost"] == "10.00"
    assert source.trace_id is not None

    # Append-only cost snapshot with the full landing cost.
    snapshots = (await db_session.execute(select(ProductCostSnapshot))).scalars().all()
    assert len(snapshots) == 1
    assert snapshots[0].total_cost == Decimal("16.00")  # 10 + 1 + 2 + 3

    # Score row persisted with dimensions and version metadata.
    scores = (await db_session.execute(select(ProductScore))).scalars().all()
    assert len(scores) == 1
    score = scores[0]
    assert score.model_version == "score-model-v1"
    assert score.rule_version == "prod-score-v1"
    assert score.scored_at is not None
    assert score.trace_id is not None
    assert set(score.__table__.columns.keys()) >= {
        "profit", "logistics", "demand", "competition",
        "differentiation", "compliance", "total",
    }

    # Analysis audit row (deterministic, no LLM).
    runs = (await db_session.execute(select(ProductAnalysisRun))).scalars().all()
    assert len(runs) == 1
    run = runs[0]
    assert run.provider == "deterministic"
    assert run.model == "heuristic-v1"
    assert run.prompt_version is None
    assert run.input_snapshot["total_cost"] == "16.00"
    assert run.output["vetoed"] is False
    assert run.token_usage == {}
    assert run.estimated_cost == Decimal("0.000000")
    assert run.latency_ms >= 0
    assert run.trace_id is not None


@pytest.mark.asyncio
async def test_cost_snapshot_history_is_never_overwritten(db_session, api_client) -> None:
    """Re-intake appends a new snapshot; historical costs are preserved."""
    await _seed_product_rules(db_session)
    first = api_client.post(INTAKE_URL, json=_intake_payload(purchase_cost="10.00"))
    assert first.status_code == 201
    second = api_client.post(INTAKE_URL, json=_intake_payload(purchase_cost="12.00"))
    assert second.status_code == 201

    snapshots = (
        await db_session.execute(
            select(ProductCostSnapshot).order_by(ProductCostSnapshot.valid_from)
        )
    ).scalars().all()
    assert len(snapshots) == 2
    assert [s.total_cost for s in snapshots] == [Decimal("16.00"), Decimal("18.00")]

    # Current cost row reflects the latest value only.
    current = (
        await db_session.execute(
            select(ProductCost).where(ProductCost.product_id == snapshots[0].product_id)
        )
    ).scalar_one()
    assert current.total_cost == Decimal("18.00")


@pytest.mark.asyncio
async def test_intake_validation_errors(db_session, api_client) -> None:
    """Invalid URL/cost/dimensions payloads are rejected before any write."""
    bad_url = api_client.post(INTAKE_URL, json=_intake_payload(source_url="not-a-url"))
    assert bad_url.status_code == 422

    bad_cost = api_client.post(INTAKE_URL, json=_intake_payload(purchase_cost="-1"))
    assert bad_cost.status_code == 422

    bad_dims = api_client.post(
        INTAKE_URL, json=_intake_payload(dimensions={"length": 8, "width": -2})
    )
    assert bad_dims.status_code == 422

    # Missing required title.
    missing_title = _intake_payload()
    missing_title.pop("title")
    assert api_client.post(INTAKE_URL, json=missing_title).status_code == 422

    # No rows were written by failed attempts.
    total = (await db_session.execute(select(func.count()).select_from(ProductSource))).scalar_one()
    assert total == 0


@pytest.mark.asyncio
async def test_decision_workflow_state_machine(db_session, api_client) -> None:
    """Decision: pending -> approved (with actor/timestamp) or rejected."""
    await _seed_product_rules(db_session)
    intake = api_client.post(INTAKE_URL, json=_intake_payload()).json()
    product_id = intake["product"]["id"]

    proposed = api_client.post(f"/api/v1/products/{product_id}/decisions")
    assert proposed.status_code == 201
    decision = proposed.json()
    assert decision["approval_status"] == "pending"
    assert decision["decision"] in {"test", "hold", "reject"}
    assert decision["confidence"] is not None
    assert decision["reasons"]
    assert decision["risks"]
    assert decision["recommended_price"] is not None
    decision_id = decision["id"]

    # Approve with actor; lifecycle advances to "test" only for test decisions.
    approved = api_client.post(
        f"/api/v1/product-decisions/{decision_id}/approve",
        json={"actor": "cto@nuotao.example", "note": "approved for testing"},
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["approval_status"] == "approved"
    assert body["approved_by"] == "cto@nuotao.example"
    assert body["approved_at"] is not None

    # Approving a second time is rejected (state machine guard).
    again = api_client.post(
        f"/api/v1/product-decisions/{decision_id}/approve",
        json={"actor": "cto@nuotao.example"},
    )
    assert again.status_code == 400

    # A fresh decision can be rejected instead.
    second = api_client.post(f"/api/v1/products/{product_id}/decisions").json()
    rejected = api_client.post(
        f"/api/v1/product-decisions/{second['id']}/reject",
        json={"actor": "cto@nuotao.example"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["approval_status"] == "rejected"

    # Events for the full workflow exist.
    from app.models.event import EventLog

    events = (
        await db_session.execute(select(EventLog.event_type).distinct())
    ).scalars().all()
    assert "product.decision.proposed" in events
    assert "product.decision.approved" in events
    assert "product.decision.rejected" in events


@pytest.mark.asyncio
async def test_intelligence_aggregate_and_sources_endpoints(db_session, api_client) -> None:
    """GET intelligence/sources/cost-snapshots return persisted data."""
    await _seed_product_rules(db_session)
    intake = api_client.post(INTAKE_URL, json=_intake_payload()).json()
    product_id = intake["product"]["id"]

    agg = api_client.get(f"/api/v1/products/{product_id}/intelligence")
    assert agg.status_code == 200
    data = agg.json()
    assert data["product"]["id"] == product_id
    assert data["score"]["total"] is not None
    assert data["analysis"]["provider"] == "deterministic"
    assert data["decision"] is None

    sources = api_client.get(f"/api/v1/products/{product_id}/sources").json()
    assert len(sources) == 1
    assert sources[0]["source_type"] == "1688"

    snapshots = api_client.get(f"/api/v1/products/{product_id}/cost-snapshots").json()
    assert len(snapshots) == 1
    assert snapshots[0]["total_cost"] == "16.00"


@pytest.mark.asyncio
async def test_deterministic_score_penalizes_unknown_cost(db_session, api_client) -> None:
    """A product without cost data gets zero profit dimension + veto on PROD-SEL-004."""
    await _seed_product_rules(db_session)
    payload = _intake_payload(
        purchase_cost="0",
        domestic_shipping="0",
        first_leg_shipping="0",
        last_leg_shipping="0",
        sku="NTO-NOCOST",
    )
    response = api_client.post(INTAKE_URL, json=payload)
    assert response.status_code == 201
    product_id = response.json()["product"]["id"]

    agg = api_client.get(f"/api/v1/products/{product_id}/intelligence").json()
    score = agg["score"]
    assert Decimal(score["profit"]) == Decimal("0.00")
    # cost_status UNKNOWN -> analysis vetoed because PROD-SEL-004 fails
    assert agg["analysis"]["output"]["vetoed"] is True
