"""Tests for M3.4 Customer Intelligence Learning Loop.

Covers: behavior prediction evaluation + error classification, deterministic
pattern mining, extended knowledge entry types, cross-domain customer context,
calibration approval protection and workspace isolation.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.order import Order
from app.schemas.rule import RuleCreate
from app.services import rule_engine

WORKSPACE = DEFAULT_WORKSPACE_ID
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000099")
INTAKE_URL = "/api/v1/products/intake"


def _headers(workspace: UUID | None = None) -> dict:
    return {"X-Workspace-Id": str(workspace)} if workspace else {}


async def _event_types(db_session, workspace: UUID) -> set[str]:
    rows = (await db_session.execute(select(EventLog.event_type))).scalars().all()
    return set(rows)


async def _seed_product_rules(db_session) -> None:
    """Seed the PRODUCT gates used by the intake scoring chain."""
    for data in (
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
        await rule_engine.create_rule(db_session, workspace_id=WORKSPACE, data=data)


def _profile(ref: str, **overrides) -> dict:
    payload = {
        "customer_reference_id": ref,
        "country": "US",
        "segment": "new",
        "total_orders": 1,
        "total_revenue": "49.99",
    }
    payload.update(overrides)
    return payload


async def _make_profile(api_client, ref: str, **overrides) -> UUID:
    response = api_client.post("/api/v1/customer-profiles", json=_profile(ref, **overrides))
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


# --------------------------------------------------------------------------- #
# 1. Prediction evaluation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_customer_evaluation_success(db_session, api_client) -> None:
    """A matched behavior prediction/decision is classified as success."""
    customer_id = await _make_profile(api_client, "wc-eval-ok")
    response = api_client.post(
        "/api/v1/customer-evaluations",
        json={
            "customer_id": str(customer_id),
            "prediction": {"decision": "reorder", "confidence": 0.75},
            "actual_behavior": {"decision": "reorder"},
            "human_rating": 5,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction_result"] == "success"
    assert body["success_flag"] is True
    assert body["error_type"] is None
    assert body["confidence_bucket"] == "HIGH"
    assert "customer.evaluation_recorded" in await _event_types(db_session, WORKSPACE)


@pytest.mark.asyncio
async def test_customer_evaluation_failure_classification(db_session, api_client) -> None:
    """Failure modes are classified: decision_mismatch / other."""
    customer_id = await _make_profile(api_client, "wc-eval-fail")

    mismatch = api_client.post(
        "/api/v1/customer-evaluations",
        json={
            "customer_id": str(customer_id),
            "prediction": {"decision": "reorder"},
            "actual_behavior": {"decision": "churn"},
        },
    )
    assert mismatch.status_code == 201
    assert mismatch.json()["prediction_result"] == "failure"
    assert mismatch.json()["error_type"] == "decision_mismatch"

    other = api_client.post(
        "/api/v1/customer-evaluations",
        json={
            "customer_id": str(customer_id),
            "prediction": {},
            "actual_behavior": {"success": False},
        },
    )
    assert other.status_code == 201
    assert other.json()["error_type"] == "other"


@pytest.mark.asyncio
async def test_customer_evaluation_missing_profile_404(db_session, api_client) -> None:
    """Evaluating an unknown customer profile returns 404."""
    missing = UUID("00000000-0000-0000-0000-00000000dead")
    response = api_client.post(
        "/api/v1/customer-evaluations",
        json={"customer_id": str(missing), "prediction": {}, "actual_behavior": {}},
    )
    assert response.status_code == 404
    assert "customer profile not found" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 2. Pattern mining
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pattern_mining_purchase_and_pain(db_session, api_client) -> None:
    """Purchase/pain patterns aggregate deterministically from data."""
    await _make_profile(api_client, "wc-pat-1", total_orders=2, total_revenue="49.99")
    await _make_profile(api_client, "wc-pat-2", total_orders=3, total_revenue="99.99")
    for category, amount in (("quality", "19.99"), ("quality", "29.99")):
        assert (
            api_client.post(
                "/api/v1/refund-cases",
                json={"reason": "damaged", "category": category, "amount": amount},
            ).status_code
            == 201
        )

    purchase = api_client.post(
        "/api/v1/customer-pattern-runs",
        json={"pattern_type": "purchase_pattern"},
    )
    assert purchase.status_code == 201, purchase.text
    body = purchase.json()
    assert body["sample_size"] == 2
    assert body["output_pattern"]["profile_count"] == 2
    assert body["output_pattern"]["avg_total_orders"] == "2.5"
    assert body["output_pattern"]["avg_total_revenue"] == "74.99"
    assert body["confidence"] == "0.2000"
    assert "customer.pattern_run_completed" in await _event_types(db_session, WORKSPACE)

    pain = api_client.post("/api/v1/customer-pattern-runs", json={"pattern_type": "pain_pattern"})
    assert pain.status_code == 201
    output = pain.json()["output_pattern"]
    assert output["refund_categories"] == {"quality": 2}
    assert output["top_category"] == "quality"
    assert output["total_refund_amount"] == "49.98"


@pytest.mark.asyncio
async def test_pattern_mining_churn_from_evaluations(db_session, api_client) -> None:
    """Churn pattern uses failed evaluations (top error type + confidence)."""
    customer_id = await _make_profile(api_client, "wc-churn")
    assert (
        api_client.post(
            "/api/v1/customer-evaluations",
            json={
                "customer_id": str(customer_id),
                "prediction": {"decision": "reorder", "confidence": 0.9},
                "actual_behavior": {"decision": "churn"},
            },
        ).status_code
        == 201
    )

    run = api_client.post("/api/v1/customer-pattern-runs", json={"pattern_type": "churn_pattern"})
    assert run.status_code == 201, run.text
    output = run.json()["output_pattern"]
    assert output["failure_evaluation_count"] == 1
    assert output["top_error_type"] == "decision_mismatch"
    assert output["avg_confidence"] == "0.9000"


# --------------------------------------------------------------------------- #
# 3. Knowledge extended types
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_customer_knowledge_extended_types(db_session, api_client) -> None:
    """M3.4 entry types (churn/bundle/pain_pattern) are supported and queryable."""
    for entry_type in ("churn_pattern", "bundle_pattern", "pain_pattern"):
        response = api_client.post(
            "/api/v1/customer-knowledge-entries",
            json={
                "entry_type": entry_type,
                "category": "trekking-chair",
                "title": f"{entry_type} insight",
                "content": "Insight content.",
                "confidence": "0.8",
            },
        )
        assert response.status_code == 201, response.text
    rows = api_client.get("/api/v1/customer-knowledge-entries?category=trekking-chair").json()
    assert len(rows) == 3
    assert "customer.knowledge_created" in await _event_types(db_session, WORKSPACE)


# --------------------------------------------------------------------------- #
# 4. Cross-domain customer context
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cross_domain_customer_context(db_session, api_client) -> None:
    """Context combines customer + orders/reviews/refunds/marketing/product/knowledge."""
    await _seed_product_rules(db_session)
    intake = api_client.post(
        INTAKE_URL,
        json={
            "title": "Trekking chair",
            "sku": "NTO-CTX-001",
            "source_type": "1688",
            "source_url": "https://detail.1688.com/offer/ctx001.html",
            "purchase_cost": "10.00",
            "weight_kg": "0.30",
            "target_market": "US",
        },
    )
    assert intake.status_code == 201, intake.text
    product_id = UUID(intake.json()["product"]["id"])

    customer_id = await _make_profile(api_client, "wc-ctx")
    db_session.add(
        Order(
            workspace_id=WORKSPACE,
            external_order_id="ord-ctx-001",
            customer_reference_id="wc-ctx",
            country="US",
            total=Decimal("49.99"),
        )
    )
    await db_session.flush()

    assert (
        api_client.post(
            "/api/v1/customer-interactions",
            json={
                "customer_id": str(customer_id),
                "product_id": str(product_id),
                "channel": "review",
                "content": "Love it.",
                "sentiment": "positive",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/api/v1/product-reviews",
            json={
                "product_id": str(product_id),
                "platform": "amazon",
                "rating": 5,
                "content": "Great chair.",
                "sentiment": "positive",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/api/v1/refund-cases",
            json={
                "customer_id": str(customer_id),
                "reason": "damaged",
                "category": "quality",
                "amount": "10.00",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/api/v1/customer-knowledge-entries",
            json={
                "customer_id": str(customer_id),
                "entry_type": "pain_pattern",
                "title": "Straps",
                "content": "Straps slip.",
                "confidence": "0.8",
            },
        ).status_code
        == 201
    )
    assert (
        api_client.post(
            "/api/v1/customer-evaluations",
            json={
                "customer_id": str(customer_id),
                "prediction": {"decision": "reorder"},
                "actual_behavior": {"decision": "reorder"},
            },
        ).status_code
        == 201
    )

    context = api_client.get(f"/api/v1/customer-context/{customer_id}")
    assert context.status_code == 200, context.text
    body = context.json()
    assert body["customer"]["customer_reference_id"] == "wc-ctx"
    assert len(body["orders"]) == 1
    assert body["orders"][0]["external_order_id"] == "ord-ctx-001"
    assert len(body["interactions"]) == 1
    assert len(body["reviews"]) == 1
    assert len(body["refunds"]) == 1
    assert body["refunds"][0]["category"] == "quality"
    assert len(body["product_data"]["products"]) == 1
    assert body["product_data"]["products"][0]["sku"] == "NTO-CTX-001"
    assert body["marketing_data"]["campaigns"] == []
    assert len(body["knowledge"]) == 1
    assert len(body["evaluations"]) == 1

    missing = UUID("00000000-0000-0000-0000-00000000dead")
    assert api_client.get(f"/api/v1/customer-context/{missing}").status_code == 404


# --------------------------------------------------------------------------- #
# 5. Calibration + approval protection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_customer_calibration_approval_protection(db_session, api_client) -> None:
    """Calibration proposes patterns; approve is human-only and recorded."""
    customer_id = await _make_profile(api_client, "wc-cal")
    for prediction, actual in (
        ({"decision": "reorder"}, {"decision": "reorder"}),
        ({"decision": "reorder"}, {"decision": "churn"}),
        ({"decision": "reorder"}, {"decision": "reorder"}),
    ):
        assert (
            api_client.post(
                "/api/v1/customer-evaluations",
                json={
                    "customer_id": str(customer_id),
                    "prediction": prediction,
                    "actual_behavior": actual,
                },
            ).status_code
            == 201
        )

    created = api_client.post("/api/v1/customer-calibration/runs")
    assert created.status_code == 201, created.text
    body = created.json()
    run_id = UUID(body["id"])
    assert body["status"] == "proposed"
    assert body["sample_size"] == 3
    assert body["successful_patterns"]["evaluation_success_count"] == 2
    assert body["failure_patterns"]["error_type_distribution"] == {"decision_mismatch": 1}
    assert "customer.calibration_run_proposed" in await _event_types(db_session, WORKSPACE)

    approved = api_client.post(
        f"/api/v1/customer-calibration/runs/{run_id}/approve",
        json={"actor": "owner@nuotao.example", "note": "ok"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by"] == "owner@nuotao.example"
    assert "customer.calibration_run_approved" in await _event_types(db_session, WORKSPACE)

    again = api_client.post(
        f"/api/v1/customer-calibration/runs/{run_id}/approve",
        json={"actor": "owner@nuotao.example"},
    )
    assert again.status_code == 400
    assert "not proposed" in again.json()["detail"]


@pytest.mark.asyncio
async def test_customer_calibration_requires_samples(db_session, api_client) -> None:
    """Calibration without enough evaluations returns 400."""
    response = api_client.post("/api/v1/customer-calibration/runs")
    assert response.status_code == 400
    assert "not enough evaluations" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 6. Workspace isolation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_customer_learning_workspace_isolation(db_session, api_client) -> None:
    """Evaluations and contexts stay invisible across workspaces."""
    customer_id = await _make_profile(api_client, "wc-iso")
    assert (
        api_client.post(
            "/api/v1/customer-evaluations",
            json={
                "customer_id": str(customer_id),
                "prediction": {"decision": "reorder"},
                "actual_behavior": {"decision": "reorder"},
            },
        ).status_code
        == 201
    )

    mine = api_client.get("/api/v1/customer-evaluations").json()
    theirs = api_client.get(
        "/api/v1/customer-evaluations", headers=_headers(OTHER_WORKSPACE)
    ).json()
    assert len(mine) == 1
    assert len(theirs) == 0

    assert (
        api_client.get(
            f"/api/v1/customer-context/{customer_id}", headers=_headers(OTHER_WORKSPACE)
        ).status_code
        == 404
    )
