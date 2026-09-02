"""Rule engine: loads active rules from the database and evaluates them.

Rules are stored in the ``rules`` table (never hardcoded). Evaluation follows
``docs/operating_rules.md``: hard rules gate actions, soft rules produce
scores, and every evaluation/override is written to ``rule_execution_logs``.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rule import Rule, RuleExecutionLog
from app.schemas.rule import (
    CheckResult,
    OverrideResult,
    RuleCreate,
    RuleResult,
    SuggestResult,
)

_MISSING = object()


class RuleEngineError(Exception):
    """Raised when a rule cannot be loaded or evaluated."""


class RuleConflictError(RuleEngineError):
    """Raised when a rule version already exists (unique constraint)."""


def _get_value(context: dict, path: str) -> object:
    """Resolve a dotted path (e.g. ``cost.shipping_ratio``) in the context."""
    current: object = context
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _as_number(value: object) -> float | None:
    """Coerce a value to float when possible (used by ordering operators)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare(actual: object, op: str, expected: object) -> bool:
    """Apply a single comparison operator between context value and rule value."""
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return isinstance(expected, list) and actual in expected
    if op == "contains":
        if isinstance(actual, list):
            return expected in actual
        if isinstance(actual, str):
            return str(expected) in actual
        return False
    if op == "exists":
        return actual is not _MISSING if bool(expected) else actual is _MISSING
    if op in {"gt", "gte", "lt", "lte"}:
        if actual is _MISSING:
            return False
        left = _as_number(actual)
        right = _as_number(expected)
        if left is not None and right is not None:
            if op == "gt":
                return left > right
            if op == "gte":
                return left >= right
            if op == "lt":
                return left < right
            return left <= right
        # Fall back to native comparison for non-numeric values.
        try:
            return {
                "gt": lambda a, b: a > b,
                "gte": lambda a, b: a >= b,
                "lt": lambda a, b: a < b,
                "lte": lambda a, b: a <= b,
            }[op](actual, expected)
        except TypeError:
            return False
    return False


def evaluate_conditions(conditions: dict, context: dict) -> bool:
    """Evaluate a structured condition tree against a context.

    Supported nodes:
    - ``{"field": "a.b", "op": "gt|gte|lt|lte|eq|ne|in|contains|exists", "value": ...}``
    - ``{"and": [cond, ...]}``, ``{"or": [cond, ...]}``, ``{"not": cond}``
    """
    if "and" in conditions and isinstance(conditions["and"], list):
        return all(evaluate_conditions(c, context) for c in conditions["and"])
    if "or" in conditions and isinstance(conditions["or"], list):
        return any(evaluate_conditions(c, context) for c in conditions["or"])
    if "not" in conditions and isinstance(conditions["not"], dict):
        return not evaluate_conditions(conditions["not"], context)

    field = conditions.get("field")
    op = conditions.get("op")
    if isinstance(field, str) and isinstance(op, str):
        value = conditions.get("value", _MISSING)
        return _compare(_get_value(context, field), op, value)
    return False


def _matches_scope(rule: Rule, context: dict) -> bool:
    """Return True when the rule's scope matches the context (empty scope = global)."""
    if not rule.scope:
        return True
    return all(context.get(key) == value for key, value in rule.scope.items())


def _is_effective(rule: Rule, now: datetime) -> bool:
    """Return True when the rule is inside its effective time window."""
    if rule.effective_from is not None and now < rule.effective_from:
        return False
    if rule.effective_to is not None and now > rule.effective_to:
        return False
    return True


def _dedupe_latest(rules: list[Rule]) -> list[Rule]:
    """Keep only the newest version of each rule_id."""
    latest: dict[str, Rule] = {}
    for rule in rules:
        current = latest.get(rule.rule_id)
        if current is None or (rule.created_at, str(rule.id)) > (
            current.created_at,
            str(current.id),
        ):
            latest[rule.rule_id] = rule
    return list(latest.values())


async def _load_rules(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    rule_id: str | None = None,
    category: str | None = None,
    version: str | None = None,
) -> list[Rule]:
    """Load active rules from the database for the given workspace."""
    stmt = select(Rule).where(
        Rule.workspace_id == workspace_id,
        Rule.status == "active",
    )
    if rule_id is not None:
        stmt = stmt.where(Rule.rule_id == rule_id)
    if category is not None:
        stmt = stmt.where(Rule.category == category)
    if version is not None:
        stmt = stmt.where(Rule.version == version)
    rows = (await session.execute(stmt)).scalars().all()
    if rule_id is not None:
        rows = _dedupe_latest(list(rows))
    return list(rows)


async def _log_execution(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    rule: Rule,
    context: dict,
    result: dict,
    trace_id: str,
) -> None:
    """Persist one rule evaluation/override for audit."""
    session.add(
        RuleExecutionLog(
            workspace_id=workspace_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            context=context,
            result=result,
            trace_id=trace_id,
        )
    )


def _rule_result(
    rule: Rule,
    *,
    passed: bool,
    trace_id: str,
    score: float | None = None,
) -> RuleResult:
    """Build a RuleResult with a human-readable reason."""
    message = rule.then_result.get("passed_message" if passed else "failed_message")
    reasons = [message or f"condition {'met' if passed else 'not met'}"]
    return RuleResult(
        rule_id=rule.rule_id,
        name=rule.name,
        rule_version=rule.version,
        rule_type=rule.rule_type,
        passed=passed,
        score=score,
        reasons=reasons,
        trace_id=trace_id,
    )


async def check(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    context: dict,
    rule_id: str | None = None,
    group: str | None = None,
    trace_id: str | None = None,
) -> CheckResult:
    """Evaluate a rule (or a group) and return pass/fail per rule.

    Either ``rule_id`` or ``group`` must be provided.
    """
    if rule_id is None and group is None:
        raise RuleEngineError("either rule_id or group is required")

    trace_id = trace_id or uuid4().hex
    now = datetime.now(UTC)
    rules = await _load_rules(
        session,
        workspace_id=workspace_id,
        rule_id=rule_id,
        category=group,
    )
    rules = _dedupe_latest(rules)
    if rule_id is not None and not rules:
        raise RuleEngineError(f"active rule '{rule_id}' not found")

    results: list[RuleResult] = []
    for rule in rules:
        if not _is_effective(rule, now) or not _matches_scope(rule, context):
            continue
        passed = evaluate_conditions(rule.when_conditions, context)
        result = _rule_result(rule, passed=passed, trace_id=trace_id)
        results.append(result)
        await _log_execution(
            session,
            workspace_id=workspace_id,
            rule=rule,
            context=context,
            result=result.model_dump(),
            trace_id=trace_id,
        )
    await session.commit()
    return CheckResult(
        all_passed=bool(results) and all(r.passed for r in results),
        results=results,
    )


async def evaluate(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    rule_id: str,
    context: dict,
    version: str | None = None,
    trace_id: str | None = None,
) -> RuleResult:
    """Evaluate a single rule (hard/flow) and return its outcome."""
    trace_id = trace_id or uuid4().hex
    now = datetime.now(UTC)
    rules = [
        rule
        for rule in await _load_rules(
            session,
            workspace_id=workspace_id,
            rule_id=rule_id,
            version=version,
        )
        if _is_effective(rule, now)
    ]
    if not rules:
        raise RuleEngineError(f"active rule '{rule_id}' not found")

    rule = max(rules, key=lambda r: (r.created_at, str(r.id)))
    passed = evaluate_conditions(rule.when_conditions, context) and _matches_scope(rule, context)
    score: float | None = None
    if rule.rule_type == "soft":
        if passed:
            score = float(rule.then_result.get("score") or rule.params.get("pass_score") or 0)
        else:
            score = float(rule.params.get("fail_score") or 0)

    result = _rule_result(rule, passed=passed, trace_id=trace_id, score=score)
    await _log_execution(
        session,
        workspace_id=workspace_id,
        rule=rule,
        context=context,
        result=result.model_dump(),
        trace_id=trace_id,
    )
    await session.commit()
    return result


async def suggest(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    group: str,
    context: dict,
    trace_id: str | None = None,
) -> SuggestResult:
    """Score all soft rules in a group and aggregate a weighted total."""
    trace_id = trace_id or uuid4().hex
    now = datetime.now(UTC)
    rules = [
        rule
        for rule in await _load_rules(
            session,
            workspace_id=workspace_id,
            category=group,
        )
        if rule.rule_type == "soft"
    ]
    rules = _dedupe_latest(rules)

    results: list[RuleResult] = []
    weighted_sum = 0.0
    weight_sum = 0.0
    for rule in rules:
        if not _is_effective(rule, now) or not _matches_scope(rule, context):
            continue
        passed = evaluate_conditions(rule.when_conditions, context)
        score = (
            float(rule.then_result.get("score") or rule.params.get("pass_score") or 0)
            if passed
            else float(rule.params.get("fail_score") or 0)
        )
        weight = float(rule.then_result.get("weight") or rule.params.get("weight") or 1)
        weighted_sum += score * weight
        weight_sum += weight

        result = _rule_result(rule, passed=passed, trace_id=trace_id, score=score)
        results.append(result)
        await _log_execution(
            session,
            workspace_id=workspace_id,
            rule=rule,
            context=context,
            result=result.model_dump(),
            trace_id=trace_id,
        )
    await session.commit()

    aggregate = weighted_sum / weight_sum if weight_sum > 0 else None
    return SuggestResult(
        group=group,
        aggregate_score=round(aggregate, 2) if aggregate is not None else None,
        results=results,
    )


async def override(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    rule_id: str,
    context: dict,
    reason: str,
    actor: str,
    trace_id: str | None = None,
) -> OverrideResult:
    """Record a human override of a rule decision (audited, not executed).

    Enforcement of the L2 approval workflow is wired in the agent layer;
    this skeleton guarantees the override is fully audited.
    """
    trace_id = trace_id or uuid4().hex
    now = datetime.now(UTC)
    rules = [
        rule
        for rule in await _load_rules(
            session,
            workspace_id=workspace_id,
            rule_id=rule_id,
        )
        if _is_effective(rule, now)
    ]
    if not rules:
        raise RuleEngineError(f"active rule '{rule_id}' not found")

    rule = max(rules, key=lambda r: (r.created_at, str(r.id)))
    result = {
        "overridden": True,
        "reason": reason,
        "actor": actor,
        "approval_level": rule.approval_level,
    }
    await _log_execution(
        session,
        workspace_id=workspace_id,
        rule=rule,
        context=context,
        result=result,
        trace_id=trace_id,
    )
    await session.commit()
    return OverrideResult(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        overridden=True,
        reason=reason,
        actor=actor,
        trace_id=trace_id,
    )


async def create_rule(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: RuleCreate,
) -> Rule:
    """Create a new versioned rule; raises RuleConflictError on duplicates."""
    rule = Rule(workspace_id=workspace_id, **data.model_dump())
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise RuleConflictError(
            f"rule '{data.rule_id}' version '{data.version}' already exists"
        ) from exc
    await session.refresh(rule)
    return rule


async def list_rules(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    category: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Rule]:
    """List rules for a workspace with optional filters."""
    stmt = select(Rule).where(Rule.workspace_id == workspace_id)
    if category is not None:
        stmt = stmt.where(Rule.category == category)
    if status is not None:
        stmt = stmt.where(Rule.status == status)
    stmt = stmt.order_by(Rule.created_at.desc(), Rule.id).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars().all())


async def get_rule(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    rule_id: str,
) -> Rule:
    """Return the newest version of a rule."""
    rules = await _load_rules(session, workspace_id=workspace_id, rule_id=rule_id)
    if not rules:
        raise RuleEngineError(f"active rule '{rule_id}' not found")
    return max(rules, key=lambda r: (r.created_at, str(r.id)))
