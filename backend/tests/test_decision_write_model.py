"""Tests for Phase 3C-3 Decision Write Model (POST /products/{id}/decision).

Covers:
- CONTINUE: candidate -> approved, approved -> testing, testing -> winner
- REJECT: any non-terminal -> rejected
- SUPPLEMENT_DATA: no state change, records event
- APPROVE: same as CONTINUE but with approval semantics
- Idempotency: same key returns stable result
- Terminal states: winner/rejected reject most decisions
- Pricing check: candidate -> approved requires pricing
- Hard rules: RULE_FAIL blocks APPROVE
- Error handling: invalid transitions, missing product

Verifies: No new state machine, reuses existing services.
"""

from decimal import Decimal
from datetime import datetime, UTC
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductNuotaoScore,
    SourcingCandidate,
)
from app.models.rule import RuleExecutionLog
from app.models.supplier import Supplier
from app.models.agent_operations import AgentApproval
from app.models.event import EventLog
from app.schemas.product_intelligence import ProductDecisionRequest


WORKSPACE = DEFAULT_WORKSPACE_ID
DECISION_URL = "/api/v1/products/{product_id}/decision"


@pytest.mark.asyncio
async def test_decision_not_found(api_client) -> None:
    """POST /products/{id}/decision returns 404 for non-existent product."""
    fake_id = str(uuid4())
    response = api_client.post(
        DECISION_URL.format(product_id=fake_id),
        json={"decision": "CONTINUE"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_continue_candidate_to_approved(db_session, api_client) -> None:
    """CONTINUE advances candidate to approved (requires pricing)."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CONT-001",
        name="Continue Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        attributes={"retail_price": "100.00"},
        meta={"regular_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data (required for candidate -> approved)
    from app.services import product_cost_service as pcost_service
    from app.schemas.product_cost import ProductCostUpsertRequest

    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
        currency="USD",
    )
    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Ready to approve"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["decision"] == "CONTINUE"
    assert data["previous_status"] == "candidate"
    assert data["current_status"] == "approved"
    assert data["idempotency_key"] is not None

    # Verify product status changed
    product = (
        await db_session.execute(
            select(Product).where(Product.id == product.id)
        )
    ).scalar_one()
    assert product.candidate_status == "approved"
    assert product.mastered_at is not None  # Product Master created


@pytest.mark.asyncio
async def test_continue_approved_to_testing(db_session, api_client) -> None:
    """CONTINUE advances approved to testing."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CONT-002",
        name="Continue Testing Product",
        status="active",
        candidate_status="approved",
        source="1688",
        mastered_at=datetime.now(UTC),
        mastered_by="admin",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Ready for testing"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["previous_status"] == "approved"
    assert data["current_status"] == "testing"


@pytest.mark.asyncio
async def test_continue_testing_to_winner(db_session, api_client) -> None:
    """CONTINUE advances testing to winner."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CONT-003",
        name="Continue Winner Product",
        status="active",
        candidate_status="testing",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Testing successful"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["previous_status"] == "testing"
    assert data["current_status"] == "winner"


@pytest.mark.asyncio
async def test_continue_from_terminal_rejected(db_session, api_client) -> None:
    """CONTINUE from rejected (terminal) returns error."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CONT-004",
        name="Rejected Product",
        status="active",
        candidate_status="rejected",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Trying to continue"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is False
    assert "terminal state" in data["error"]
    assert data["previous_status"] == "rejected"
    assert data["current_status"] == "rejected"


@pytest.mark.asyncio
async def test_continue_from_terminal_winner(db_session, api_client) -> None:
    """CONTINUE from winner (terminal) returns error."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CONT-005",
        name="Winner Product",
        status="active",
        candidate_status="winner",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Trying to continue"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is False
    assert "terminal state" in data["error"]


@pytest.mark.asyncio
async def test_continue_candidate_without_pricing(db_session, api_client) -> None:
    """CONTINUE from candidate without pricing returns SUPPLEMENT_DATA."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CONT-006",
        name="No Pricing Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Trying to continue"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is False
    assert "pricing" in data["error"].lower()
    assert data["next_action"] == "SUPPLEMENT_DATA"


@pytest.mark.asyncio
async def test_reject_candidate(db_session, api_client) -> None:
    """REJECT moves candidate to rejected state."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-REJ-001",
        name="Reject Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "REJECT", "reason": "Not viable"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["decision"] == "REJECT"
    assert data["previous_status"] == "candidate"
    assert data["current_status"] == "rejected"
    assert data["next_action"] == "NONE"

    # Verify product status changed
    product = (
        await db_session.execute(
            select(Product).where(Product.id == product.id)
        )
    ).scalar_one()
    assert product.candidate_status == "rejected"


@pytest.mark.asyncio
async def test_reject_from_terminal(db_session, api_client) -> None:
    """REJECT from terminal state returns error."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-REJ-002",
        name="Already Rejected",
        status="active",
        candidate_status="rejected",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "REJECT", "reason": "Trying to reject again"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is False
    assert "terminal state" in data["error"]


@pytest.mark.asyncio
async def test_supplement_data_no_fields(db_session, api_client) -> None:
    """SUPPLEMENT_DATA without fields returns error."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-SUP-001",
        name="Supplement Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "SUPPLEMENT_DATA", "reason": "Need data"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is False
    assert "supplement_fields" in data["error"]


@pytest.mark.asyncio
async def test_supplement_data_with_fields(db_session, api_client) -> None:
    """SUPPLEMENT_DATA with fields records event, no state change."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-SUP-002",
        name="Supplement Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={
            "decision": "SUPPLEMENT_DATA",
            "reason": "Need cost and supplier data",
            "supplement_fields": ["cost", "supplier"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["decision"] == "SUPPLEMENT_DATA"
    assert data["previous_status"] == "candidate"
    assert data["current_status"] == "candidate"  # No state change
    assert data["next_action"] == "SUPPLEMENT_DATA"

    # Verify product status unchanged
    product = (
        await db_session.execute(
            select(Product).where(Product.id == product.id)
        )
    ).scalar_one()
    assert product.candidate_status == "candidate"


@pytest.mark.asyncio
async def test_approve_candidate_to_approved(db_session, api_client) -> None:
    """APPROVE advances candidate to approved (same as CONTINUE)."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-APP-001",
        name="Approve Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        meta={"regular_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data
    from app.services import product_cost_service as pcost_service
    from app.schemas.product_cost import ProductCostUpsertRequest

    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
        currency="USD",
    )
    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "APPROVE", "reason": "Human approved"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["decision"] == "APPROVE"
    assert data["previous_status"] == "candidate"
    assert data["current_status"] == "approved"


@pytest.mark.asyncio
async def test_approve_with_rule_fail(db_session, api_client) -> None:
    """APPROVE with RULE_FAIL returns error."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-APP-002",
        name="Rule Fail Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        meta={"regular_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data
    from app.services import product_cost_service as pcost_service
    from app.schemas.product_cost import ProductCostUpsertRequest

    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
        currency="USD",
    )
    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    # Create a failed rule log
    from app.models.rule import RuleExecutionLog

    rule_log = RuleExecutionLog(
        workspace_id=WORKSPACE,
        rule_id="PROD-GATE-001",
        rule_version="v1",
        context={"product_id": str(product.id), "test": True},
        result={
            "name": "Product Gate 001",
            "passed": False,
            "reason": "Cost threshold not met",
        },
        trace_id="test-trace-rule",
    )
    db_session.add(rule_log)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "APPROVE", "reason": "Trying to approve with rule fail"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is False
    assert "RULE_FAIL" in data["error"] or "hard rule" in data["error"].lower()
    assert data["next_action"] == "SUPPLEMENT_DATA"


@pytest.mark.asyncio
async def test_idempotency_same_key(db_session, api_client) -> None:
    """Same idempotency_key returns stable result (no duplicate mutation)."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-IDEM-001",
        name="Idempotency Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        meta={"regular_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data
    from app.services import product_cost_service as pcost_service
    from app.schemas.product_cost import ProductCostUpsertRequest

    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
        currency="USD",
    )
    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    idempotency_key = "test-idempotency-key-001"

    # First request
    response1 = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={
            "decision": "CONTINUE",
            "reason": "First request",
            "idempotency_key": idempotency_key,
        },
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["success"] is True
    assert data1["idempotency_key"] == idempotency_key

    # Second request with same key (product is now approved, not candidate)
    response2 = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={
            "decision": "CONTINUE",
            "reason": "Second request",
            "idempotency_key": idempotency_key,
        },
    )
    assert response2.status_code == 200
    data2 = response2.json()

    # Should return same result (idempotent)
    assert data2["success"] is True
    assert data2["idempotency_key"] == idempotency_key
    assert data2["previous_status"] == data1["previous_status"]
    assert data2["current_status"] == data1["current_status"]

    # Verify product was only advanced once
    product = (
        await db_session.execute(
            select(Product).where(Product.id == product.id)
        )
    ).scalar_one()
    assert product.candidate_status == "approved"  # Not testing


@pytest.mark.asyncio
async def test_event_logged_for_continue(db_session, api_client) -> None:
    """CONTINUE creates an event in EventLog."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-EVT-001",
        name="Event Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        meta={"regular_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data
    from app.services import product_cost_service as pcost_service
    from app.schemas.product_cost import ProductCostUpsertRequest

    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
        currency="USD",
    )
    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Event test"},
    )
    assert response.status_code == 200

    # Verify event was created
    events = (
        await db_session.execute(
            select(EventLog)
            .where(
                EventLog.workspace_id == WORKSPACE,
                EventLog.entity_type == "product",
                EventLog.entity_id == str(product.id),
                EventLog.event_type == "product.decision.continue",
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].payload.get("decision") == "CONTINUE"
    assert events[0].payload.get("success") is True
    assert events[0].payload.get("from_status") == "candidate"
    assert events[0].payload.get("to_status") == "approved"


@pytest.mark.asyncio
async def test_decision_full_flow(db_session, api_client) -> None:
    """Integration test: full decision flow from candidate to winner."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-FLOW-001",
        name="Full Flow Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        meta={"regular_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data
    from app.services import product_cost_service as pcost_service
    from app.schemas.product_cost import ProductCostUpsertRequest

    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("20.00"),
        domestic_shipping=Decimal("2.00"),
        first_leg_shipping=Decimal("3.00"),
        last_leg_shipping=Decimal("4.00"),
        international_shipping=Decimal("25.00"),
        packaging=Decimal("1.00"),
        tax_estimate=Decimal("2.00"),
        handling=Decimal("1.00"),
        payment_fee=Decimal("3.00"),
        marketing_amortization=Decimal("2.00"),
        after_sales_loss=Decimal("2.00"),
        currency="USD",
    )
    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    # Step 1: CONTINUE candidate -> approved
    response1 = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Step 1: Approve"},
    )
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["success"] is True
    assert data1["current_status"] == "approved"

    # Step 2: CONTINUE approved -> testing
    response2 = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Step 2: Test"},
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["success"] is True
    assert data2["current_status"] == "testing"

    # Step 3: CONTINUE testing -> winner
    response3 = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Step 3: Winner"},
    )
    assert response3.status_code == 200
    data3 = response3.json()
    assert data3["success"] is True
    assert data3["current_status"] == "winner"

    # Step 4: CONTINUE from winner (terminal) - should fail
    response4 = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={"decision": "CONTINUE", "reason": "Step 4: Continue from winner"},
    )
    assert response4.status_code == 200
    data4 = response4.json()
    assert data4["success"] is False
    assert "terminal state" in data4["error"]


@pytest.mark.asyncio
async def test_supplement_data_from_terminal(db_session, api_client) -> None:
    """SUPPLEMENT_DATA is allowed from terminal states."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-TERM-SUP-001",
        name="Terminal Supplement Product",
        status="active",
        candidate_status="rejected",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.post(
        DECISION_URL.format(product_id=str(product.id)),
        json={
            "decision": "SUPPLEMENT_DATA",
            "reason": "Need more data even after rejection",
            "supplement_fields": ["supplier_contact"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["decision"] == "SUPPLEMENT_DATA"
    assert data["current_status"] == "rejected"
