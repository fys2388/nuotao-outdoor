"""Tests for the V3.0 small-batch test loop services (P3-a)."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_suggestion import AgentSuggestion
from app.models.product import Product
from app.models.product_intelligence import ProductExperiment, ProductNuotaoScore
from app.services.nuotao_test_loop import (
    ACTION_DROP_AFTER_TEST,
    promote_to_hero,
    record_test_result,
    start_market_test,
)

pytestmark = pytest.mark.asyncio


async def _product(session, *, stage="test_candidate", sku="NTO-LOOP"):
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku=sku,
        name=sku,
        category="camping-light",
        candidate_status="candidate",
        funnel_stage=stage,
    )
    session.add(product)
    await session.flush()
    return product


async def _score(session, product, grade="hero", total="88"):
    session.add(
        ProductNuotaoScore(
            workspace_id=DEFAULT_WORKSPACE_ID,
            product_id=product.id,
            value_score=Decimal("8"),
            utility_score=Decimal("8"),
            weight_packability_score=Decimal("8"),
            durability_score=Decimal("8"),
            brand_fit_score=Decimal("8"),
            differentiation_score=Decimal("8"),
            total=Decimal(total),
            grade=grade,
            reject_reasons=[],
            dimension_evidence={},
            model_version="nuotao-score-v3.0",
            rule_version="veto-v3.0",
        )
    )


async def _experiment(session, product, status="proposed"):
    experiment = ProductExperiment(
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=product.id,
        experiment_type="nuotao_market_test",
        status=status,
    )
    session.add(experiment)
    await session.flush()
    return experiment


async def test_full_loop_to_hero(db_session):
    product = await _product(db_session)
    await _score(db_session, product)
    await _experiment(db_session, product)

    started = await start_market_test(db_session, product.id, actor="ops-alice")
    assert started["funnel_stage"] == "testing"
    assert started["experiment_status"] == "running"

    recorded = await record_test_result(
        db_session,
        product.id,
        actor="ops-alice",
        actual={"conversion_rate": 0.04, "roas": 2.4, "return_rate": 0.05},
        success=True,
    )
    assert recorded["experiment_status"] == "passed"

    promoted = await promote_to_hero(db_session, product.id, actor="boss-bob")
    assert promoted["funnel_stage"] == "hero"
    experiment = (
        (
            await db_session.execute(
                select(ProductExperiment).where(ProductExperiment.product_id == product.id)
            )
        )
        .scalars()
        .one()
    )
    assert experiment.status == "completed"
    assert experiment.approved_by == "boss-bob"


async def test_start_requires_test_candidate_stage(db_session):
    product = await _product(db_session, stage="recalled", sku="NTO-BADSTAGE")
    await _experiment(db_session, product)
    with pytest.raises(ValueError):
        await start_market_test(db_session, product.id, actor="ops")


async def test_failed_test_proposes_drop(db_session):
    product = await _product(db_session, stage="testing", sku="NTO-FAIL")
    await _experiment(db_session, product, status="running")
    result = await record_test_result(
        db_session,
        product.id,
        actor="ops",
        actual={"conversion_rate": 0.004},
        success=False,
    )
    assert result["experiment_status"] == "failed"
    drop = (
        (
            await db_session.execute(
                select(AgentSuggestion).where(
                    AgentSuggestion.execution_action == ACTION_DROP_AFTER_TEST
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(drop) == 1
    assert drop[0].status == "pending_approval"
    # Failed test must not auto-reject the product.
    assert product.funnel_stage == "testing"


async def test_promote_requires_passed_unless_forced(db_session):
    product = await _product(db_session, stage="testing", sku="NTO-GATE")
    await _experiment(db_session, product, status="running")
    with pytest.raises(ValueError):
        await promote_to_hero(db_session, product.id, actor="boss")
    forced = await promote_to_hero(db_session, product.id, actor="boss", force=True)
    assert forced["funnel_stage"] == "hero"
    assert forced["forced"] is True
