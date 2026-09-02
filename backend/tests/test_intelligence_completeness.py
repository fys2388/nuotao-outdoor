"""Tests for M2.1.5 product intelligence data completeness.

Covers sourcing candidates (one product, many suppliers), the landed cost
model, per-dimension score evidence, and the prediction -> experiment ->
actual_result testing loop.
"""

import json
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductCostSnapshot,
    ProductScoreEvidence,
)
from app.schemas.rule import RuleCreate
from app.services import rule_engine

WORKSPACE = DEFAULT_WORKSPACE_ID
INTAKE_URL = "/api/v1/products/intake"


async def _seed_product_rules(db_session) -> None:
    """Seed deterministic PRODUCT gates (PROD-GATE-001/002)."""
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


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Camping Stove Set",
        "sku": "NTO-STOVE-001",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/987654321.html",
        "purchase_cost": "12.00",
        "domestic_shipping": "1.00",
        "first_leg_shipping": "2.00",
        "last_leg_shipping": "3.00",
        "international_shipping": "4.00",
        "packaging": "0.80",
        "tax_estimate": "1.20",
        "handling": "0.50",
        "weight_kg": "0.60",
        "dimensions": {"length": 20, "width": 15, "height": 10},
        "target_market": "US",
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------- sourcing


@pytest.mark.asyncio
async def test_sourcing_candidates_multiple_per_product(db_session, api_client) -> None:
    """One product can carry many supplier candidates with quote data."""
    await _seed_product_rules(db_session)
    intake = api_client.post(INTAKE_URL, json=_intake_payload()).json()
    product_id = UUID(intake["product"]["id"])

    first = api_client.post(
        f"/api/v1/products/{product_id}/candidates",
        json={
            "supplier_code": None,
            "source_type": "1688",
            "source_url": "https://detail.1688.com/offer/a.html",
            "title": "Stove Set Offer A",
            "purchase_price": "11.00",
            "moq": 50,
            "lead_time_days": 7,
        },
    )
    assert first.status_code == 201
    second = api_client.post(
        f"/api/v1/products/{product_id}/candidates",
        json={
            "source_type": "1688",
            "source_url": "https://detail.1688.com/offer/b.html",
            "title": "Stove Set Offer B",
            "purchase_price": "10.50",
            "moq": 100,
            "lead_time_days": 5,
        },
    )
    assert second.status_code == 201

    rows = api_client.get(f"/api/v1/products/{product_id}/candidates").json()
    assert len(rows) == 2
    assert {r["title"] for r in rows} == {"Stove Set Offer A", "Stove Set Offer B"}
    for row in rows:
        assert row["workspace_id"] == str(WORKSPACE)
        assert row["version"] == "v1"
        assert row["status"] == "active"
        assert row["trace_id"] is not None
    assert {r["purchase_price"] for r in rows} == {"11.00", "10.50"}

    # Missing product -> 404
    from uuid import uuid4

    missing = api_client.post(
        f"/api/v1/products/{uuid4()}/candidates",
        json={"purchase_price": "5.00"},
    )
    assert missing.status_code == 404

    # events recorded
    from app.models.event import EventLog

    events = (
        (
            await db_session.execute(
                select(EventLog.event_type).where(EventLog.event_type == "product.candidate.added")
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 2


# --------------------------------------------------------------- landed cost model


@pytest.mark.asyncio
async def test_landed_cost_model_breakdown(db_session, api_client) -> None:
    """Intake computes the full landed cost and keeps versioned history."""
    await _seed_product_rules(db_session)
    response = api_client.post(INTAKE_URL, json=_intake_payload())
    assert response.status_code == 201
    product_id = UUID(response.json()["product"]["id"])

    # total_landed = 12 + 1 + 4 + 0.8 + 1.2 + 0.5 = 19.50
    current = (
        await db_session.execute(select(ProductCost).where(ProductCost.product_id == product_id))
    ).scalar_one()
    assert current.purchase_cost == Decimal("12.00")
    assert current.international_shipping == Decimal("4.00")
    assert current.packaging == Decimal("0.80")
    assert current.tax_estimate == Decimal("1.20")
    assert current.handling == Decimal("0.50")
    assert current.total_landed_cost == Decimal("19.50")
    assert current.version == "v1"

    snapshot = (
        await db_session.execute(
            select(ProductCostSnapshot).where(ProductCostSnapshot.product_id == product_id)
        )
    ).scalar_one()
    assert snapshot.total_landed_cost == Decimal("19.50")
    assert snapshot.version == "v1"

    # Re-intake with a different purchase cost bumps the version and appends.
    updated = api_client.post(
        INTAKE_URL, json=_intake_payload(purchase_cost="14.00", sku="NTO-STOVE-001")
    )
    assert updated.status_code == 201
    await db_session.refresh(current)
    assert current.total_landed_cost == Decimal("21.50")
    assert current.version == "v2"

    snapshots = (
        (
            await db_session.execute(
                select(ProductCostSnapshot)
                .where(ProductCostSnapshot.product_id == product_id)
                .order_by(ProductCostSnapshot.valid_from)
            )
        )
        .scalars()
        .all()
    )
    assert len(snapshots) == 2
    assert [s.total_landed_cost for s in snapshots] == [Decimal("19.50"), Decimal("21.50")]
    assert [s.version for s in snapshots] == ["v1", "v2"]


@pytest.mark.asyncio
async def test_landed_cost_falls_back_to_legacy_legs(db_session, api_client) -> None:
    """Without explicit international shipping, first+last legs are used."""
    await _seed_product_rules(db_session)
    payload = _intake_payload(sku="NTO-LEGACY", international_shipping=None)
    response = api_client.post(INTAKE_URL, json=payload)
    assert response.status_code == 201
    product_id = UUID(response.json()["product"]["id"])

    current = (
        await db_session.execute(select(ProductCost).where(ProductCost.product_id == product_id))
    ).scalar_one()
    # international = first(2) + last(3) = 5 -> landed = 12+1+5+0.8+1.2+0.5 = 20.50
    assert current.international_shipping == Decimal("5.00")
    assert current.total_landed_cost == Decimal("20.50")


# ----------------------------------------------------------------- score evidence


@pytest.mark.asyncio
async def test_score_evidence_per_dimension(db_session, api_client) -> None:
    """Each score dimension persists score/source/evidence/confidence."""
    await _seed_product_rules(db_session)
    intake = api_client.post(INTAKE_URL, json=_intake_payload()).json()
    product_id = intake["product"]["id"]
    score_id = UUID(intake["score_id"])

    rows = (
        (
            await db_session.execute(
                select(ProductScoreEvidence).where(
                    ProductScoreEvidence.product_score_id == score_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 6
    dims = {row.dimension: row for row in rows}
    assert set(dims) == {
        "profit",
        "logistics",
        "demand",
        "competition",
        "differentiation",
        "compliance",
    }
    profit = dims["profit"]
    assert profit.score > 0
    assert profit.source == "landed-cost-model-v1"
    assert profit.evidence
    assert profit.confidence == Decimal("0.900")  # cost KNOWN
    assert profit.version == "v1"
    assert profit.trace_id is not None

    demand = dims["demand"]
    assert demand.source == "pending-llm"
    assert demand.confidence == Decimal("0.200")

    # Evidence endpoint + analyze response include evidence.
    evidence_api = api_client.get(f"/api/v1/product-decisions/scores/{score_id}/evidence")
    assert evidence_api.status_code == 200
    assert len(evidence_api.json()) == 6

    analyze = api_client.post(f"/api/v1/products/{product_id}/analyze").json()
    assert len(analyze["evidence"]) == 6


# ---------------------------------------------------------------- experiments


@pytest.mark.asyncio
async def test_experiment_prediction_loop(db_session, api_client) -> None:
    """prediction -> experiment -> actual_result -> calibration."""
    await _seed_product_rules(db_session)
    intake = api_client.post(INTAKE_URL, json=_intake_payload()).json()
    product_id = intake["product"]["id"]

    # propose
    proposed = api_client.post(f"/api/v1/products/{product_id}/experiments")
    assert proposed.status_code == 201
    experiment = proposed.json()
    assert experiment["status"] == "proposed"
    assert experiment["prediction"]["score_total"] is not None
    assert experiment["prediction"]["landed_cost"] == "19.50"
    assert experiment["version"] == "v1"
    experiment_id = experiment["id"]

    # start
    started = api_client.post(
        f"/api/v1/product-decisions/experiments/{experiment_id}/start",
        json={
            "quantity": 40,
            "channels": ["meta", "google"],
            "budget": "200.00",
            "targets": {"conversion_rate": "0.02", "roas": "2.00"},
        },
    )
    assert started.status_code == 200
    assert started.json()["status"] == "active"
    assert started.json()["experiment"]["quantity"] == 40

    # cannot start twice
    again = api_client.post(
        f"/api/v1/product-decisions/experiments/{experiment_id}/start",
        json={"quantity": 10},
    )
    assert again.status_code == 400

    # complete
    completed = api_client.post(
        f"/api/v1/product-decisions/experiments/{experiment_id}/complete",
        json={
            "units_sold": 12,
            "revenue": "480.00",
            "orders": 12,
            "conversion_rate": "0.03",
            "roas": "2.50",
            "return_rate": "0.05",
            "actor": "tester",
            "source": "manual",
        },
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert body["actual_result"]["units_sold"] == 12
    calibration = body["calibration"]
    assert Decimal(calibration["conversion_rate"]) == Decimal("0.0100")
    assert Decimal(calibration["roas"]) == Decimal("0.5000")

    # list endpoint
    listed = api_client.get(f"/api/v1/products/{product_id}/experiments").json()
    assert len(listed) == 1

    # cannot complete again
    again_complete = api_client.post(
        f"/api/v1/product-decisions/experiments/{experiment_id}/complete",
        json={"units_sold": 1},
    )
    assert again_complete.status_code == 400

    # events
    from app.models.event import EventLog

    events = (
        (
            await db_session.execute(
                select(EventLog.event_type).where(EventLog.event_type.like("product.experiment.%"))
            )
        )
        .scalars()
        .all()
    )
    assert sorted(events) == [
        "product.experiment.completed",
        "product.experiment.proposed",
        "product.experiment.started",
    ]


# ------------------------------------------------------------- order landed cost


@pytest.mark.asyncio
async def test_order_resolves_landed_cost(db_session, api_client) -> None:
    """Webhook order profit uses the authoritative total_landed_cost."""
    from app.schemas.rule import RuleCreate
    from app.services import rule_engine

    product = Product(workspace_id=WORKSPACE, sku="SKU-LANDED", name="Landed Lamp")
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductCost(
            workspace_id=WORKSPACE,
            product_id=product.id,
            purchase_cost=Decimal("10.00"),
            first_leg_shipping=Decimal("2.00"),
            last_leg_shipping=Decimal("3.00"),
            packaging=Decimal("1.00"),
            international_shipping=Decimal("5.00"),
            total_landed_cost=Decimal("16.00"),
            total_cost=Decimal("15.00"),
            version="v1",
        )
    )
    for data in (
        RuleCreate(
            rule_id="PROFIT-002",
            name="margin >= 20%",
            category="PROFIT",
            rule_type="hard",
            version="v1",
            status="active",
            when_conditions={"field": "profit.contribution_margin_rate", "op": "gte", "value": 0.2},
            then_result={"passed_message": "ok", "failed_message": "low"},
        ),
    ):
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=data)
    await db_session.commit()

    import hashlib
    import hmac

    payload = {
        "id": 5001,
        "status": "processing",
        "currency": "USD",
        "total": "100.00",
        "subtotal": "95.00",
        "shipping_total": "5.00",
        "discount_total": "5.00",
        "tax_total": "0.00",
        "line_items": [
            {"id": 1, "name": "Landed Lamp", "sku": "SKU-LANDED", "quantity": 1, "total": "90.00"}
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    secret = get_settings().woocommerce_webhook_secret
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    response = api_client.post(
        "/api/v1/webhooks/woocommerce",
        content=body,
        headers={"Content-Type": "application/json", "X-Wc-Webhook-Signature": signature},
    )
    assert response.status_code == 201
    profit = response.json()["profit"]
    assert profit["product_cost"] == "16.00"  # total_landed_cost, not 15.00
    assert profit["cost_status"] == "KNOWN"
