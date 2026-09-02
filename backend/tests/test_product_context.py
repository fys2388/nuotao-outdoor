"""Tests for the Product Context Builder (M2.2)."""

from decimal import Decimal
from uuid import UUID

import pytest

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.schemas.product_intelligence import SourcingCandidateCreate
from app.services import (
    product_context,
    product_intelligence as pi,
)

WORKSPACE = DEFAULT_WORKSPACE_ID
INTAKE_URL = "/api/v1/products/intake"


def _intake_payload(**overrides) -> dict:
    payload = {
        "title": "Trail Running Backpack",
        "sku": "NTO-PACK-001",
        "source_type": "1688",
        "source_url": "https://detail.1688.com/offer/999.html",
        "purchase_cost": "12.00",
        "domestic_shipping": "1.50",
        "first_leg_shipping": "2.00",
        "last_leg_shipping": "3.00",
        "weight_kg": "0.35",
        "dimensions": {"length": 30, "width": 12, "height": 5},
        "target_market": "US",
        "currency": "USD",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_context_contains_all_analysis_sections(db_session, api_client) -> None:
    """The built context covers product/cost/landed/suppliers/score/rules/experiments."""
    response = api_client.post(INTAKE_URL, json=_intake_payload())
    assert response.status_code == 201
    product_id = UUID(response.json()["product"]["id"])

    # One supplier candidate + one proposed experiment.
    candidate = await pi.create_sourcing_candidate(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product_id,
        data=SourcingCandidateCreate(
            supplier_code=None,
            source_type="1688",
            source_url="https://detail.1688.com/offer/998.html",
            purchase_price=Decimal("11.00"),
            moq=30,
            lead_time_days=7,
            trend_score=Decimal("8.0"),
        ),
        trace_id="ctx-1",
    )
    assert candidate.id is not None
    await pi.propose_experiment(
        db_session, workspace_id=WORKSPACE, product_id=product_id, trace_id="ctx-1"
    )

    context = await product_context.build_product_context(
        db_session, workspace_id=WORKSPACE, product_id=product_id, trace_id="ctx-1"
    )

    assert context["meta"]["product_id"] == str(product_id)
    assert context["product"]["sku"] == "NTO-PACK-001"
    # Landed cost: 12 + 1.5 + (2+3) + 0 + 0 + 0 = 18.50 (international = legs).
    assert context["landed_cost"]["total_landed_cost"] == "18.50"
    assert context["landed_cost"]["cost_status"] == "KNOWN"
    assert context["cost"]["total_cost"] == "18.50"
    assert len(context["supplier_candidates"]) == 1
    assert context["supplier_candidates"][0]["purchase_price"] == "11.00"
    # Score + per-dimension evidence present.
    assert context["score"] is not None
    assert context["score"]["total"] != "0"
    assert len(context["score"]["evidence"]) == 6
    dimensions = {row["dimension"] for row in context["score"]["evidence"]}
    assert dimensions == {
        "profit",
        "logistics",
        "demand",
        "competition",
        "differentiation",
        "compliance",
    }
    # Rules + experiments sections are lists (may be empty without seeding).
    assert isinstance(context["rules"], list)
    assert len(context["experiments"]) == 1
    assert context["experiments"][0]["status"] == "proposed"

    # JSON-safe: no Decimal left anywhere in the tree.
    def _walk(value):
        if isinstance(value, dict):
            return any(_walk(item) for item in value.values())
        if isinstance(value, list):
            return any(_walk(item) for item in value)
        return isinstance(value, Decimal)

    assert not _walk(context)


@pytest.mark.asyncio
async def test_context_unknown_cost(db_session, api_client) -> None:
    """A product without cost data reports cost_status UNKNOWN."""
    response = api_client.post(
        INTAKE_URL,
        json=_intake_payload(
            purchase_cost="0.00",
            domestic_shipping="0.00",
            first_leg_shipping="0.00",
            last_leg_shipping="0.00",
        ),
    )
    assert response.status_code == 201
    product_id = UUID(response.json()["product"]["id"])
    context = await product_context.build_product_context(
        db_session, workspace_id=WORKSPACE, product_id=product_id
    )
    assert context["landed_cost"]["total_landed_cost"] == "0.00"
    assert context["landed_cost"]["cost_status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_context_missing_product(db_session) -> None:
    """A missing product raises ProductContextError."""
    from uuid import uuid4

    with pytest.raises(product_context.ProductContextError):
        await product_context.build_product_context(
            db_session, workspace_id=WORKSPACE, product_id=uuid4()
        )
