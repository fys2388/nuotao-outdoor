"""Integration tests for the V3.0 selection orchestration service (SQLite in-memory)."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductNuotaoScore,
    ProductScore,
    SourcingCandidate,
)
from app.models.supplier import Supplier
from app.services.nuotao_selection_service import evaluate_product, evaluate_products

pytestmark = pytest.mark.asyncio


async def _product(session, *, sku, category="camping-light", meta=None, weight="0.5"):
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku=sku,
        name=sku,
        category=category,
        weight_kg=Decimal(weight),
        meta=meta or {},
        candidate_status="candidate",
    )
    session.add(product)
    await session.flush()
    return product


async def _operational_score(session, product, total="85"):
    session.add(
        ProductScore(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            profit=8, logistics=8, demand=8, competition=9,
            differentiation=8, compliance=8, total=Decimal(total),
            model_version="heuristic-v1", rule_version="m2.1-v1",
        )
    )


async def _supplier(session, product, rating):
    supplier = Supplier(
        workspace_id=DEFAULT_WORKSPACE_ID,
        code=f"S-{rating}-{uuid4().hex[:6]}",
        name="factory",
        rating=rating,
    )
    session.add(supplier)
    await session.flush()
    session.add(
        SourcingCandidate(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            supplier_id=supplier.id,
            supplier_code=supplier.code,
        )
    )
    await session.flush()
    return supplier


async def test_healthy_product_advances_to_test_candidate(db_session):
    product = await _product(
        db_session, sku="NTO-GOOD",
        meta={"sale_price": "30"},
    )
    await _operational_score(db_session, product)
    await _supplier(db_session, product, "B")
    db_session.add(
        ProductCost(
            workspace_id=DEFAULT_WORKSPACE_ID, product_id=product.id,
            total_landed_cost=Decimal("12"), international_shipping=Decimal("3"),
            payment_fee=Decimal("1"), marketing_amortization=Decimal("1"),
        )
    )
    await db_session.flush()

    result = await evaluate_product(db_session, product.id)

    assert result["veto"]["vetoed"] is False
    assert result["funnel_stage"] == "test_candidate"
    assert result["grade"] == "core"
    assert Decimal("70") <= Decimal(str(result["nuotao_total"])) <= Decimal("85")
    assert len(result["veto"]["findings"]) == 12
    # Persisted append-only + product snapshot updated.
    rows = (
        await db_session.execute(select(ProductNuotaoScore))
    ).scalars().all()
    assert len(rows) == 1
    await db_session.refresh(product)
    assert product.funnel_stage == "test_candidate"
    assert product.reject_reasons == []


async def test_commercial_vetoes_reject_product(db_session):
    product = await _product(db_session, sku="NTO-BAD", meta={"sale_price": "15"})
    await _operational_score(db_session, product)
    await _supplier(db_session, product, "D")
    db_session.add(
        ProductCost(
            workspace_id=DEFAULT_WORKSPACE_ID, product_id=product.id,
            total_landed_cost=Decimal("14"), international_shipping=Decimal("7"),
        )
    )
    await db_session.flush()

    result = await evaluate_product(db_session, product.id)

    assert result["veto"]["vetoed"] is True
    assert {"V9", "V10", "V11"}.issubset(set(result["veto"]["failed"]))
    assert result["funnel_stage"] == "rejected"
    await db_session.refresh(product)
    failed_ids = {item["rule_id"] for item in product.reject_reasons}
    assert {"V9", "V10", "V11"}.issubset(failed_ids)


async def test_missing_data_is_pending_not_fabricated_and_low_score_rejects(db_session):
    product = await _product(db_session, sku="NTO-EMPTY")

    result = await evaluate_product(db_session, product.id)

    # No hard veto without data, but missing rules are explicitly pending.
    assert result["veto"]["vetoed"] is False
    for rule in ("V6", "V9", "V10", "V11", "V12"):
        assert rule in result["veto"]["pending"]
    # Neutral dimensions -> below 65 -> rejected on score, not on a fake veto.
    assert result["grade"] == "reject"
    assert result["funnel_stage"] == "rejected"


async def test_evaluation_is_append_only(db_session):
    product = await _product(db_session, sku="NTO-APPEND", meta={"sale_price": "30"})
    await _operational_score(db_session, product)
    await _supplier(db_session, product, "A")

    await evaluate_product(db_session, product.id)
    await evaluate_product(db_session, product.id)
    rows = (await db_session.execute(select(ProductNuotaoScore))).scalars().all()
    assert len(rows) == 2


async def test_batch_skips_soft_deleted_and_missing(db_session):
    from datetime import UTC, datetime

    live = await _product(db_session, sku="NTO-LIVE")
    gone = await _product(db_session, sku="NTO-GONE")
    gone.deleted_at = datetime.now(UTC)
    await db_session.flush()

    result = await evaluate_products(db_session, [live.id, gone.id, uuid4()])

    assert result["count"] == 1
    assert len(result["skipped"]) == 2
    assert result["errors"] == []


async def test_ai_assessment_from_latest_run_closes_and_can_veto(db_session):
    product = await _product(db_session, sku="NTO-AI", meta={"sale_price": "30"})
    await _operational_score(db_session, product)
    await _supplier(db_session, product, "B")
    db_session.add(
        ProductAnalysisRun(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            provider="newton",
            model="test",
            prompt_version="v3",
            input_snapshot={},
            output={
                "nuotao_assessment": {
                    "brand_fit": 8,
                    "veto_signals": {
                        "V1": {"verdict": "fail", "reason": "外观专利近似"},
                        "V2": "pass",
                        "V3": "pass",
                        "V5": "pass",
                    },
                }
            },
            token_usage={},
            estimated_cost=Decimal("0"),
            latency_ms=1,
            status="completed",
        )
    )
    await db_session.flush()

    result = await evaluate_product(db_session, product.id)

    # AI fail on V1 hard-vetoes an otherwise healthy product.
    assert "V1" in result["veto"]["failed"]
    assert result["veto"]["vetoed"] is True
    assert result["funnel_stage"] == "rejected"
    # AI pass closes the other AI-owned rules.
    assert not set(result["veto"]["pending"]) & {"V2", "V3", "V5"}
    # Brand Fit override and provenance recorded.
    assert result["dimensions"]["brand_fit"] == 8.0
    assert result["evidence"]["ai_assessment_source"] == "latest_analyst_run"
    assert result["evidence"]["ai_vetos_closed"] == ["V1", "V2", "V3", "V5"]
