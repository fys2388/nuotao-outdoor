"""Tests for V3.0 evaluation -> experiment/suggestion handoff (P3-a/P3-b)."""

import pytest
from sqlalchemy import func, select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_suggestion import AgentSuggestion
from app.models.product import Product
from app.models.product_intelligence import ProductExperiment
from app.services.nuotao_handoff import (
    ACTION_HERO_NOMINATION,
    ACTION_MARKET_TEST,
    propose_selection_handoff,
)

pytestmark = pytest.mark.asyncio


async def _product(session, *, sku="NTO-HANDOFF", name="Test Product"):
    product = Product(
        workspace_id=DEFAULT_WORKSPACE_ID,
        sku=sku,
        name=name,
        category="camping-light",
        candidate_status="candidate",
    )
    session.add(product)
    await session.flush()
    return product


async def _suggestion_count(session, action) -> int:
    rows = (
        await session.execute(
            select(AgentSuggestion).where(AgentSuggestion.execution_action == action)
        )
    ).scalars().all()
    return len(rows)


async def test_test_candidate_creates_experiment_and_suggestion(db_session):
    product = await _product(db_session)
    result = await propose_selection_handoff(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=product.id,
        product_name=product.name,
        nuotao_total=78.0,
        grade="core",
        funnel_stage="test_candidate",
        vetoed=False,
    )
    assert "experiment_created" in result["actions"]
    assert "market_test_suggestion_created" in result["actions"]
    assert result["experiment_id"]
    assert len(result["suggestion_ids"]) == 1

    experiments = (
        (
            await db_session.execute(
                select(ProductExperiment).where(ProductExperiment.product_id == product.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(experiments) == 1
    assert experiments[0].status == "proposed"
    assert experiments[0].experiment_type == "nuotao_market_test"
    # Every handoff suggestion awaits a human (never auto-approved).
    suggestion = (
        await db_session.execute(
            select(AgentSuggestion).where(
                AgentSuggestion.execution_action == ACTION_MARKET_TEST
            )
        )
    ).scalars().one()
    assert suggestion.status == "pending_approval"


async def test_repeated_handoff_is_idempotent(db_session):
    product = await _product(db_session, sku="NTO-IDEM")
    common = dict(
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=product.id,
        product_name=product.name,
        nuotao_total=72.0,
        grade="long_tail",
        funnel_stage="test_candidate",
        vetoed=False,
    )
    first = await propose_selection_handoff(db_session, **common)
    second = await propose_selection_handoff(db_session, **common)

    assert "experiment_created" in first["actions"]
    assert second["actions"] == ["experiment_reused"]
    assert second["suggestion_ids"] == []
    assert await _suggestion_count(db_session, ACTION_MARKET_TEST) == 1
    experiment_count = (
        await db_session.execute(
            select(func.count())
            .select_from(ProductExperiment)
            .where(ProductExperiment.product_id == product.id)
        )
    ).scalar()
    assert experiment_count == 1


async def test_hero_gets_nomination_and_market_test(db_session):
    product = await _product(db_session, sku="NTO-HERO")
    result = await propose_selection_handoff(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=product.id,
        product_name=product.name,
        nuotao_total=88.0,
        grade="hero",
        funnel_stage="test_candidate",
        vetoed=False,
    )
    assert "hero_nomination_created" in result["actions"]
    assert "market_test_suggestion_created" in result["actions"]
    assert await _suggestion_count(db_session, ACTION_HERO_NOMINATION) == 1


async def test_rejected_or_vetoed_creates_nothing(db_session):
    product = await _product(db_session, sku="NTO-REJ")
    result = await propose_selection_handoff(
        db_session,
        workspace_id=DEFAULT_WORKSPACE_ID,
        product_id=product.id,
        product_name=product.name,
        nuotao_total=51.5,
        grade="reject",
        funnel_stage="rejected",
        vetoed=False,
    )
    assert result["suggestion_ids"] == []
    assert result["experiment_id"] is None
    total_suggestions = (
        await db_session.execute(select(func.count()).select_from(AgentSuggestion))
    ).scalar()
    assert total_suggestions == 0
