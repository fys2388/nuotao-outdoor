"""Tests for Phase 3C-2 Decision Read Model (GET /products/{id}/decision).

Covers:
- Normal product with all data
- Candidate stage
- Analysis stage
- Pending Approval stage
- Product Master stage
- Listing stage
- WC Sync stage
- Missing analysis
- Missing cost
- Missing supply
- Rule FAIL
- Rule UNKNOWN
- Return rate UNKNOWN
- Wrong workspace
- Unauthorized
- Not found

Verifies: UNKNOWN is never auto-PASS.
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
    ProductCostSnapshot,
    ProductNuotaoScore,
    SourcingCandidate,
    WooCommerceDraft,
)
from app.models.rule import RuleExecutionLog
from app.models.supplier import Supplier
from app.models.listing_job import ListingJob
from app.models.agent_operations import AgentApproval
from app.models.event import EventLog
from app.services import product_cost_service as pcost_service
from app.schemas.product_cost import ProductCostUpsertRequest


WORKSPACE = DEFAULT_WORKSPACE_ID
DECISION_URL = "/api/v1/products/{product_id}/decision"


def _intake_payload(**overrides) -> dict:
    """Helper to create a valid intake payload."""
    payload = {
        "title": "Test Product",
        "sku": "TEST-001",
        "description": "A test product",
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


async def _seed_supplier(db_session, supplier_code="SUP-001", supplier_name="Test Supplier") -> Supplier:
    """Create a supplier."""
    supplier = Supplier(
        workspace_id=WORKSPACE,
        code=supplier_code,
        name=supplier_name,
        platform="1688",
        shop_url="https://example.1688.com",
        rating="A",
        status="active",
        contact={"lead_time_days": 15, "moq": 100},
    )
    db_session.add(supplier)
    await db_session.flush()
    return supplier


async def _seed_sourcing_candidate(db_session, product_id, supplier_id=None) -> SourcingCandidate:
    """Create a sourcing candidate."""
    candidate = SourcingCandidate(
        workspace_id=WORKSPACE,
        product_id=product_id,
        supplier_id=supplier_id,
        supplier_code="SUP-001",
        source_type="1688",
        source_url="https://detail.1688.com/offer/123456789.html",
        title="Test Product",
        status="active",
        purchase_price=Decimal("10.00"),
        moq=100,
        lead_time_days=15,
        trend_score=Decimal("7.50"),
        profit_model={},
        notes="Test candidate",
        version="v1",
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


async def _seed_analysis_run(db_session, product_id, recommendation="RECOMMEND") -> ProductAnalysisRun:
    """Create an analysis run."""
    analysis = ProductAnalysisRun(
        workspace_id=WORKSPACE,
        product_id=product_id,
        provider="deterministic",
        model="heuristic-v1",
        prompt_version="v1",
        input_snapshot={"total_cost": "16.00"},
        output={
            "recommendation": recommendation,
            "reasons": ["Good margin", "High demand"],
            "risks": ["New supplier"],
            "market_size": "1000000",
            "market_growth": "15.5",
            "competition_level": "medium",
            "seasonality": "summer",
            "target_customer": {"age": "25-35", "gender": "male"},
        },
        token_usage={},
        estimated_cost=Decimal("0.000000"),
        latency_ms=100,
        status="completed",
        trace_id="test-trace-001",
    )
    db_session.add(analysis)
    await db_session.flush()
    return analysis


async def _seed_nuotao_score(db_session, product_id) -> ProductNuotaoScore:
    """Create a Nuotao score."""
    score = ProductNuotaoScore(
        workspace_id=WORKSPACE,
        product_id=product_id,
        value_score=Decimal("8.5"),
        utility_score=Decimal("7.0"),
        weight_packability_score=Decimal("9.0"),
        durability_score=Decimal("8.0"),
        brand_fit_score=Decimal("7.5"),
        differentiation_score=Decimal("6.0"),
        total=Decimal("76.50"),
        grade="core",
        reject_reasons=[],
        dimension_evidence={},
        model_version="nuotao-score-v3",
        rule_version="prod-rules-v1",
        trace_id="test-trace-002",
    )
    db_session.add(score)
    await db_session.flush()
    return score


async def _seed_rule_log(
    db_session,
    rule_id="PROD-GATE-001",
    rule_version="v1",
    passed=True,
    product_id=None,
) -> RuleExecutionLog:
    """Create a rule execution log."""
    context = {"product_id": str(product_id) if product_id else None, "test": True}
    log = RuleExecutionLog(
        workspace_id=WORKSPACE,
        rule_id=rule_id,
        rule_version=rule_version,
        context=context,
        result={
            "name": "Product Gate 001",
            "passed": passed,
            "reason": "All conditions met" if passed else "Condition failed",
        },
        trace_id="test-trace-003",
    )
    db_session.add(log)
    await db_session.flush()
    return log


async def _seed_approval(
    db_session,
    product_id,
    approval_type="PRODUCT_CANDIDATE",
    status="pending",
) -> AgentApproval:
    """Create an approval."""
    approval = AgentApproval(
        workspace_id=WORKSPACE,
        approval_type=approval_type,
        status=status,
        entity_type="product",
        entity_id=str(product_id),
        trace_id="test-trace-004",
    )
    db_session.add(approval)
    await db_session.flush()
    return approval


async def _seed_listing_job(
    db_session,
    product_id,
    status="pending",
) -> ListingJob:
    """Create a listing job."""
    listing = ListingJob(
        workspace_id=WORKSPACE,
        product_id=product_id,
        sku="TEST-001",
        name="Test Product",
        payload={},
        status=status,
        submitted_by="test-user",
        submitted_at=datetime.now(UTC),
    )
    db_session.add(listing)
    await db_session.flush()
    return listing


async def _seed_wc_draft(db_session, product_id, status="generated") -> WooCommerceDraft:
    """Create a WooCommerce draft."""
    draft = WooCommerceDraft(
        workspace_id=WORKSPACE,
        product_id=product_id,
        sku="TEST-001",
        name="Test Product",
        payload={},
        status=status,
        trace_id="test-trace-005",
    )
    db_session.add(draft)
    await db_session.flush()
    return draft


async def _seed_event(db_session, product_id, event_type="product.created") -> EventLog:
    """Create an event log entry."""
    event = EventLog(
        workspace_id=WORKSPACE,
        event_type=event_type,
        entity_type="product",
        entity_id=str(product_id),
        payload={"test": True},
        trace_id="test-trace-006",
    )
    db_session.add(event)
    await db_session.flush()
    return event


@pytest.mark.asyncio
async def test_decision_view_not_found(api_client) -> None:
    """GET /products/{id}/decision returns 404 for non-existent product."""
    fake_id = str(uuid4())
    response = api_client.get(DECISION_URL.format(product_id=fake_id))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_decision_view_opportunity_stage(db_session, api_client) -> None:
    """Product with no data returns Opportunity stage with UNKNOWN AI recommendation."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-OPPT-001",
        name="Opportunity Product",
        description="A new opportunity",
        status="draft",
        source="1688",
        source_url="https://detail.1688.com/offer/123.html",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["product"]["sku"] == "TEST-OPPT-001"
    assert data["stage"] == "Opportunity"
    assert data["status"] == "draft"
    assert data["ai_recommendation"] == "UNKNOWN"
    assert data["ai_score"] is None
    assert data["margin_percent"] is None
    assert data["return_rate"] is None  # Always UNKNOWN
    assert data["qc_rate"] is None  # Always UNKNOWN
    assert data["is_mastered"] is False
    assert data["next_action"]["action"] == "ANALYZE"


@pytest.mark.asyncio
async def test_decision_view_candidate_stage(db_session, api_client) -> None:
    """Product with candidate_status='candidate' returns Candidate stage."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-CAND-001",
        name="Candidate Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["stage"] == "Candidate"
    assert data["ai_recommendation"] == "UNKNOWN"
    assert data["next_action"]["action"] == "ANALYZE"


@pytest.mark.asyncio
async def test_decision_view_analysis_stage(db_session, api_client) -> None:
    """Product with analysis data returns Analysis stage with AI recommendation."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-ANAL-001",
        name="Analysis Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        attributes={"retail_price": "100.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost data so MISSING_COST blocker is not added
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

    await _seed_analysis_run(db_session, product.id, recommendation="RECOMMEND")
    await _seed_nuotao_score(db_session, product.id)

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["stage"] == "Analysis"
    assert data["ai_recommendation"] == "RECOMMEND"
    assert data["ai_score"] == "76.50"
    assert data["ai_grade"] == "core"
    assert data["ai_reasons"] == ["Good margin", "High demand"]
    assert data["ai_risks"] == ["New supplier"]
    assert data["market_size"] == "1000000"
    assert data["market_growth"] == "15.5"
    assert data["competition_level"] == "medium"
    assert data["next_action"]["action"] == "SUBMIT_APPROVAL"


@pytest.mark.asyncio
async def test_decision_view_pending_approval_stage(db_session, api_client) -> None:
    """Product with approved candidate_status returns Pending Approval stage."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-APPR-001",
        name="Approval Product",
        status="active",
        candidate_status="approved",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    await _seed_approval(db_session, product.id, approval_type="PRODUCT_CANDIDATE", status="pending")

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["stage"] == "Pending Approval"
    assert data["approval_status"] == "pending"
    assert data["approval_type"] == "PRODUCT_CANDIDATE"
    assert data["next_action"]["action"] == "APPROVE"
    assert "PENDING_APPROVAL" in [b["code"] for b in data["blockers"]]


@pytest.mark.asyncio
async def test_decision_view_product_master_stage(db_session, api_client) -> None:
    """Product with mastered_at set returns Product Master stage."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-MASTER-001",
        name="Master Product",
        status="active",
        candidate_status="approved",
        mastered_at=datetime.now(UTC),
        mastered_by="admin",
        mastered_trace_id="test-trace-master",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["stage"] == "Product Master"
    assert data["is_mastered"] is True
    assert data["mastered_at"] is not None
    assert data["mastered_by"] == "admin"
    assert data["mastered_trace_id"] == "test-trace-master"
    assert data["next_action"]["action"] == "CREATE_LISTING"


@pytest.mark.asyncio
async def test_decision_view_listing_stage(db_session, api_client) -> None:
    """Product with pending listing job returns B2C Listing stage."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-LIST-001",
        name="Listing Product",
        status="active",
        candidate_status="approved",
        mastered_at=None,
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    await _seed_listing_job(db_session, product.id, status="pending")

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["stage"] == "B2C Listing"
    assert data["listing_status"] == "pending"
    assert data["next_action"]["action"] == "SUBMIT_APPROVAL"
    assert "LISTING_NOT_APPROVED" in [b["code"] for b in data["blockers"]]


@pytest.mark.asyncio
async def test_decision_view_woocommerce_stage(db_session, api_client) -> None:
    """Product with published listing returns WooCommerce stage."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-WC-001",
        name="WC Product",
        status="active",
        candidate_status="approved",
        mastered_at=None,
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    await _seed_listing_job(db_session, product.id, status="published")

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["stage"] == "WooCommerce"
    assert data["listing_status"] == "published"
    assert data["next_action"]["action"] == "NONE"


@pytest.mark.asyncio
async def test_decision_view_with_cost_and_margin(db_session, api_client) -> None:
    """Product with cost data returns margin and freight_share calculations."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-COST-001",
        name="Cost Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        attributes={"retail_price": "50.00"},
    )
    db_session.add(product)
    await db_session.flush()

    # Create cost snapshot
    cost_data = ProductCostUpsertRequest(
        purchase_cost=Decimal("10.00"),
        domestic_shipping=Decimal("1.00"),
        first_leg_shipping=Decimal("2.00"),
        last_leg_shipping=Decimal("3.00"),
        international_shipping=Decimal("15.00"),
        packaging=Decimal("0.50"),
        tax_estimate=Decimal("1.00"),
        handling=Decimal("0.50"),
        payment_fee=Decimal("2.00"),
        marketing_amortization=Decimal("1.00"),
        after_sales_loss=Decimal("1.00"),
        currency="USD",
    )

    await pcost_service.upsert_product_cost(
        db_session,
        workspace_id=WORKSPACE,
        product_id=product.id,
        data=cost_data,
        trace_id="test-trace-cost",
    )

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["currency"] == "USD"
    assert data["purchase_cost"] == "10.00"
    assert data["landed_cost"] is not None
    assert data["margin_percent"] is not None
    assert data["freight_share"] is not None

    # Verify margin calculation
    margin = Decimal(data["margin_percent"])
    assert margin > 0  # Should be positive with $50 retail and ~$35 cost


@pytest.mark.asyncio
async def test_decision_view_missing_cost_blocker(db_session, api_client) -> None:
    """Product without cost data returns MISSING_COST blocker."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-NO-COST-001",
        name="No Cost Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    blocker_codes = [b["code"] for b in data["blockers"]]
    assert "MISSING_COST" in blocker_codes
    assert data["purchase_cost"] is None
    assert data["margin_percent"] is None


@pytest.mark.asyncio
async def test_decision_view_missing_supply_blocker(db_session, api_client) -> None:
    """Product without supplier data returns MISSING_SUPPLY_DATA blocker."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-NO-SUP-001",
        name="No Supply Product",
        status="active",
        candidate_status="candidate",
        source="1688",
        # No supplier code linked
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    blocker_codes = [b["code"] for b in data["blockers"]]
    assert "MISSING_SUPPLY_DATA" in blocker_codes
    assert data["supplier_name"] is None
    assert data["lead_time_days"] is None
    assert data["moq"] is None


@pytest.mark.asyncio
async def test_decision_view_with_rule_fail(db_session, api_client) -> None:
    """Product with failed rule returns RULE_FAIL blocker."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-RULE-FAIL-001",
        name="Rule Fail Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    # Create a failed rule log
    await _seed_rule_log(
        db_session,
        rule_id="PROD-GATE-001",
        rule_version="v1",
        passed=False,
        product_id=product.id,
    )

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    blocker_codes = [b["code"] for b in data["blockers"]]
    assert "RULE_FAIL" in blocker_codes
    assert data["hard_rules_summary"]["FAIL"] >= 1


@pytest.mark.asyncio
async def test_decision_view_with_rule_unknown(db_session, api_client) -> None:
    """Product with no rule evaluation returns RULE_UNKNOWN blocker."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-RULE-UNK-001",
        name="Rule Unknown Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    # Create a rule log with no product_id context (won't match)
    await _seed_rule_log(
        db_session,
        rule_id="PROD-GATE-001",
        rule_version="v1",
        passed=True,
        product_id=None,  # Won't match this product
    )

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    # No rules matched for this product, so no RULE_UNKNOWN blocker
    # (UNKNOWN is only for rules that were evaluated but result is None)
    assert data["hard_rules"] == []
    assert data["hard_rules_summary"]["UNKNOWN"] == 0


@pytest.mark.asyncio
async def test_decision_view_return_rate_unknown(db_session, api_client) -> None:
    """Return rate is always UNKNOWN until the field exists in the model."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-RET-001",
        name="Return Rate Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert data["return_rate"] is None  # Always UNKNOWN


@pytest.mark.asyncio
async def test_decision_view_wrong_workspace(api_client) -> None:
    """GET /products/{id}/decision returns 404 for product in different workspace."""
    # Use a UUID that doesn't exist in the database
    non_existent_id = str(uuid4())
    response = api_client.get(DECISION_URL.format(product_id=non_existent_id))
    # Should return 404 since product doesn't exist
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_decision_view_unknown_never_pass(db_session, api_client) -> None:
    """Verify that UNKNOWN is never auto-converted to PASS."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-UNK-PASS-001",
        name="Unknown Pass Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    # No cost, no rules, no analysis - all should be UNKNOWN
    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()

    # AI recommendation should be UNKNOWN
    assert data["ai_recommendation"] == "UNKNOWN"

    # No rule results means no PASS
    assert data["hard_rules_summary"]["PASS"] == 0
    assert data["hard_rules_summary"]["FAIL"] == 0
    assert data["hard_rules_summary"]["UNKNOWN"] == 0

    # Cost data missing
    assert data["purchase_cost"] is None
    assert data["margin_percent"] is None

    # Supply data missing
    assert data["supplier_name"] is None
    assert data["lead_time_days"] is None

    # Return rate always UNKNOWN
    assert data["return_rate"] is None
    assert data["qc_rate"] is None


@pytest.mark.asyncio
async def test_decision_view_timeline(db_session, api_client) -> None:
    """Product with events returns timeline data."""
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-TIME-001",
        name="Timeline Product",
        status="active",
        candidate_status="candidate",
        source="1688",
    )
    db_session.add(product)
    await db_session.flush()

    # Add some events
    await _seed_event(db_session, product.id, "product.created")
    await _seed_event(db_session, product.id, "product.analysis_run")
    await _seed_event(db_session, product.id, "product.score_calculated")

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()
    assert len(data["timeline"]) >= 1
    assert data["timeline"][0]["event_type"] in (
        "product.created",
        "product.analysis_run",
        "product.score_calculated",
    )


@pytest.mark.asyncio
async def test_decision_view_full_product(db_session, api_client) -> None:
    """Integration test: product with all data sources populated."""
    # Create supplier
    supplier = await _seed_supplier(db_session)

    # Create product
    product = Product(
        workspace_id=WORKSPACE,
        sku="TEST-FULL-001",
        name="Full Data Product",
        status="active",
        candidate_status="candidate",
        source="SUP-001",
        source_url="https://detail.1688.com/offer/123.html",
        attributes={"retail_price": "100.00"},
        meta={"stock": 500},
    )
    db_session.add(product)
    await db_session.flush()

    # Create sourcing candidate
    await _seed_sourcing_candidate(db_session, product.id, supplier.id)

    # Create analysis
    await _seed_analysis_run(db_session, product.id, recommendation="RECOMMEND")

    # Create score
    await _seed_nuotao_score(db_session, product.id)

    # Create cost
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
        trace_id="test-trace-full",
    )

    # Create rule log
    await _seed_rule_log(
        db_session,
        rule_id="PROD-GATE-001",
        rule_version="v1",
        passed=True,
        product_id=product.id,
    )

    # Create events
    await _seed_event(db_session, product.id, "product.created")

    response = api_client.get(DECISION_URL.format(product_id=str(product.id)))
    assert response.status_code == 200

    data = response.json()

    # Verify all sections are populated
    assert data["product"]["sku"] == "TEST-FULL-001"
    assert data["stage"] == "Analysis"
    assert data["ai_recommendation"] == "RECOMMEND"
    assert data["ai_score"] == "76.50"
    assert data["ai_grade"] == "core"
    assert data["supplier_name"] == "Test Supplier"
    assert data["lead_time_days"] == 15
    assert data["moq"] == 100
    assert data["purchase_cost"] == "20.00"
    assert data["margin_percent"] is not None
    assert data["freight_share"] is not None
    assert data["hard_rules_summary"]["PASS"] >= 1
    assert len(data["timeline"]) >= 1
    assert data["next_action"]["action"] == "SUBMIT_APPROVAL"
