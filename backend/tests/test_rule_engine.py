"""Tests for the rule engine (condition evaluator + database-backed flows)."""

import pytest
from sqlalchemy import select

from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.rule import RuleExecutionLog
from app.schemas.rule import RuleCreate
from app.services import rule_engine

WORKSPACE = DEFAULT_WORKSPACE_ID


def test_evaluate_conditions_leaf_operators() -> None:
    """Leaf comparison operators behave as specified."""
    ctx = {
        "cost": {"shipping_ratio": 0.35, "weight_kg": 1.5},
        "tags": ["camping"],
        "title": "headlamp",
        "category": "camping",
    }
    assert rule_engine.evaluate_conditions(
        {"field": "cost.shipping_ratio", "op": "lte", "value": 0.4}, ctx
    )
    assert rule_engine.evaluate_conditions(
        {"field": "cost.shipping_ratio", "op": "gt", "value": 0.3},
        ctx,
    )
    assert not rule_engine.evaluate_conditions(
        {"field": "cost.shipping_ratio", "op": "gt", "value": 0.4},
        ctx,
    )
    assert rule_engine.evaluate_conditions(
        {"field": "cost.weight_kg", "op": "lt", "value": 2},
        ctx,
    )
    assert rule_engine.evaluate_conditions(
        {"field": "tags", "op": "contains", "value": "camping"},
        ctx,
    )
    assert rule_engine.evaluate_conditions(
        {"field": "title", "op": "contains", "value": "lamp"},
        ctx,
    )
    assert rule_engine.evaluate_conditions(
        {
            "field": "category",
            "op": "in",
            "value": ["camping", "hiking"],
        },
        ctx,
    )
    assert not rule_engine.evaluate_conditions(
        {"field": "missing.field", "op": "eq", "value": None}, ctx
    )


def test_evaluate_conditions_composites() -> None:
    """and/or/not trees compose correctly."""
    ctx = {"a": 5, "b": 10}
    assert rule_engine.evaluate_conditions(
        {
            "and": [
                {"field": "a", "op": "gt", "value": 1},
                {"field": "b", "op": "lt", "value": 20},
            ]
        },
        ctx,
    )
    assert rule_engine.evaluate_conditions(
        {
            "or": [
                {"field": "a", "op": "gt", "value": 100},
                {"field": "b", "op": "eq", "value": 10},
            ]
        },
        ctx,
    )
    assert rule_engine.evaluate_conditions({"not": {"field": "a", "op": "eq", "value": 99}}, ctx)
    assert not rule_engine.evaluate_conditions(
        {
            "and": [
                {"field": "a", "op": "gt", "value": 1},
                {"field": "b", "op": "gt", "value": 100},
            ]
        },
        ctx,
    )


async def _seed_rule(
    db_session,
    *,
    rule_id="PROD-TEST-001",
    category="PROD-SEL",
    rule_type="hard",
    version="v1",
    conditions=None,
    then_result=None,
    params=None,
):
    return await rule_engine.create_rule(
        db_session,
        workspace_id=WORKSPACE,
        data=RuleCreate(
            rule_id=rule_id,
            name="test rule",
            category=category,
            rule_type=rule_type,
            version=version,
            status="active",
            when_conditions=conditions
            or {"field": "cost.shipping_ratio", "op": "lte", "value": 0.4},
            then_result=then_result or {"passed_message": "ok", "failed_message": "too high"},
            params=params or {},
            approval_level="L0",
        ),
    )


@pytest.mark.asyncio
async def test_check_hard_rule_pass_and_fail(db_session) -> None:
    """check() returns pass/fail per rule and persists audit logs."""
    await _seed_rule(db_session)

    ok = await rule_engine.check(
        db_session,
        workspace_id=WORKSPACE,
        rule_id="PROD-TEST-001",
        context={"cost": {"shipping_ratio": 0.35}},
    )
    assert ok.all_passed is True
    assert ok.results[0].passed is True
    assert ok.results[0].rule_type == "hard"

    bad = await rule_engine.check(
        db_session,
        workspace_id=WORKSPACE,
        rule_id="PROD-TEST-001",
        context={"cost": {"shipping_ratio": 0.55}},
    )
    assert bad.all_passed is False
    assert bad.results[0].passed is False
    assert "too high" in bad.results[0].reasons[0]

    logs = (await db_session.execute(select(RuleExecutionLog))).scalars().all()
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_check_group(db_session) -> None:
    """check() on a group evaluates all hard rules in the category."""
    await _seed_rule(db_session, rule_id="PROD-TEST-001")
    await _seed_rule(
        db_session,
        rule_id="PROD-TEST-002",
        conditions={"field": "cost.weight_kg", "op": "lte", "value": 5},
    )

    result = await rule_engine.check(
        db_session,
        workspace_id=WORKSPACE,
        group="PROD-SEL",
        context={"cost": {"shipping_ratio": 0.3, "weight_kg": 8}},
    )
    assert result.all_passed is False
    assert {r.rule_id: r.passed for r in result.results} == {
        "PROD-TEST-001": True,
        "PROD-TEST-002": False,
    }


@pytest.mark.asyncio
async def test_evaluate_soft_rule_score(db_session) -> None:
    """evaluate() on a soft rule returns a score."""
    await _seed_rule(
        db_session,
        rule_id="PROD-SCORE-001",
        category="PROD-SCORE",
        rule_type="soft",
        conditions={"field": "cost.target_margin", "op": "gte", "value": 0.45},
        then_result={"score": 10, "weight": 3},
        params={"pass_score": 10, "fail_score": 4, "weight": 3},
    )
    result = await rule_engine.evaluate(
        db_session,
        workspace_id=WORKSPACE,
        rule_id="PROD-SCORE-001",
        context={"cost": {"target_margin": 0.5}},
    )
    assert result.passed is True
    assert result.score == 10.0


@pytest.mark.asyncio
async def test_suggest_weighted_aggregate(db_session) -> None:
    """suggest() aggregates weighted soft-rule scores."""
    await _seed_rule(
        db_session,
        rule_id="PROD-SCORE-001",
        category="PROD-SCORE",
        rule_type="soft",
        conditions={"field": "cost.target_margin", "op": "gte", "value": 0.45},
        params={"pass_score": 10, "fail_score": 4, "weight": 3},
    )
    await _seed_rule(
        db_session,
        rule_id="PROD-SCORE-002",
        category="PROD-SCORE",
        rule_type="soft",
        conditions={"field": "cost.shipping_ratio", "op": "lte", "value": 0.2},
        params={"pass_score": 8, "fail_score": 3, "weight": 2},
    )

    result = await rule_engine.suggest(
        db_session,
        workspace_id=WORKSPACE,
        group="PROD-SCORE",
        context={"cost": {"target_margin": 0.5, "shipping_ratio": 0.25}},
    )
    # first rule passes (10*3), second fails (3*2) -> (30+6)/5 = 7.2
    assert result.aggregate_score == 7.2
    scores = {r.rule_id: r.score for r in result.results}
    assert scores == {"PROD-SCORE-001": 10.0, "PROD-SCORE-002": 3.0}


@pytest.mark.asyncio
async def test_override_is_audited(db_session) -> None:
    """override() records an audited override without executing anything."""
    await _seed_rule(db_session)
    result = await rule_engine.override(
        db_session,
        workspace_id=WORKSPACE,
        rule_id="PROD-TEST-001",
        context={"cost": {"shipping_ratio": 0.55}},
        reason="promotional campaign approved",
        actor="founder@nuotao.com",
    )
    assert result.overridden is True
    assert result.actor == "founder@nuotao.com"

    logs = (await db_session.execute(select(RuleExecutionLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].result["overridden"] is True
    assert logs[0].result["actor"] == "founder@nuotao.com"


@pytest.mark.asyncio
async def test_create_rule_conflict(db_session) -> None:
    """Creating the same rule_id + version twice raises a conflict."""
    await _seed_rule(db_session)
    with pytest.raises(rule_engine.RuleConflictError):
        await _seed_rule(db_session)


@pytest.mark.asyncio
async def test_check_unknown_rule_raises(db_session) -> None:
    """check() on a missing rule raises RuleEngineError."""
    with pytest.raises(rule_engine.RuleEngineError):
        await rule_engine.check(
            db_session,
            workspace_id=WORKSPACE,
            rule_id="DOES-NOT-EXIST",
            context={},
        )
