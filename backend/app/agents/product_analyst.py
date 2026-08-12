"""Product Analyst Agent v1 (M2.2).

The first AI product-analysis capability of Nuotao AI OS. It is strictly
**analyse + suggest + audit** - it never executes business actions.

Permissions
-----------
- READ:  product data (via the Product Context Builder; no direct writes)
- WRITE: ``product_analysis_runs`` (audit) and ``product_decisions``
  (proposals with ``approval_status=pending`` only)
- FORBIDDEN: approve, publish, purchase, start experiments, or mutate any
  product/cost/supplier/order row.

Flow
----
Product Context -> Prompt (registry) -> LLM Gateway -> Structured Output
-> Validation (schema + business gates + rule veto) -> audit rows.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AiAgentRun
from app.models.product_intelligence import ProductAnalysisRun, ProductDecision
from app.schemas.product_analyst import (
    ProductAnalysisOutput,
    ProductAnalysisResultOut,
)
from app.services import event_service, llm_gateway, product_context, prompt_registry
from app.services.llm_gateway import LLMError, LLMRequest, parse_json_content

logger = logging.getLogger(__name__)

AGENT_NAME = "product-analyst"
PROMPT_NAME = "PRODUCT_ANALYST"
TRIGGER = "api:product-analyst:analyze"

# Business gate (mirrors operating rules): an UNKNOWN product cost must never
# produce a high-confidence profitability conclusion or a "test" decision.
UNKNOWN_COST_MAX_CONFIDENCE = Decimal("0.500")

GatewayComplete = Callable[..., Awaitable[llm_gateway.LLMResponse]]


class ProductAnalystError(Exception):
    """Raised when the analyst cannot produce a validated recommendation."""


@dataclass
class ProductAnalysisResult:
    """Outcome of one analyst run (success or failure audit)."""

    analysis_run: ProductAnalysisRun
    decision: ProductDecision | None = None
    output: ProductAnalysisOutput | None = None


def _json_safe(value: Any) -> Any:
    """Recursively convert Decimals/UUIDs/datetimes for JSON storage."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _as_decimal(value: Any) -> Decimal | None:
    """Parse a JSON-safe numeric string back to Decimal when possible."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return None


async def _load_product(session: AsyncSession, *, workspace_id: UUID, product_id: UUID) -> None:
    """Verify the product exists (read-only); raises ProductAnalystError."""
    from app.models.product import Product

    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        raise ProductAnalystError("product not found")


def _rule_context(context: dict, *, recommended_price: Decimal | None = None) -> dict:
    """Build the rule-engine context from a product context (JSON-safe)."""
    cost_status = context.get("landed_cost", {}).get("cost_status", "UNKNOWN")
    total_cost = _as_decimal(context.get("cost", {}).get("total_cost")) or Decimal("0")
    weight = _as_decimal(context.get("product", {}).get("weight_kg"))
    margin_rate: Decimal | None = None
    shipping_ratio: Decimal | None = None
    landed = _as_decimal(context.get("landed_cost", {}).get("total_landed_cost"))
    if landed is not None and landed > Decimal("0"):
        price = recommended_price
        if price is not None and price > Decimal("0"):
            margin_rate = ((price - landed) / price).quantize(Decimal("0.0001"))
            international = _as_decimal(
                context.get("landed_cost", {}).get("international_shipping")
            ) or Decimal("0")
            if international > Decimal("0"):
                shipping_ratio = (international / price).quantize(Decimal("0.0001"))
    return {
        "product": {"weight_kg": float(weight) if weight is not None else None},
        "cost": {"total_cost": float(total_cost)},
        "profit": {
            "margin_rate": float(margin_rate) if margin_rate is not None else None,
            "cost_status": cost_status,
        },
        "logistics": {
            "shipping_ratio": float(shipping_ratio) if shipping_ratio is not None else None,
            "weight_kg": float(weight) if weight is not None else None,
        },
    }


def _validate_output(
    output: ProductAnalysisOutput,
    *,
    context: dict,
) -> tuple[bool, list[str]]:
    """Apply business gates on top of schema validation.

    Returns ``(valid, failures)``. Failures include:
    - cost_status UNKNOWN combined with a "test" decision or confidence > 0.5
      (PROFIT-003 gate, mirroring the deterministic chain).

    Hard-rule vetoes are *not* failures here: they are enforced afterwards by
    downgrading the proposal to "reject" (see ``analyze_product``).
    """
    failures: list[str] = []
    cost_status = context.get("landed_cost", {}).get("cost_status", "UNKNOWN")

    if cost_status == "UNKNOWN":
        if output.decision == "test":
            failures.append("cost_status UNKNOWN forbids a 'test' decision (PROFIT-003 gate)")
        if output.confidence > UNKNOWN_COST_MAX_CONFIDENCE:
            failures.append(
                "cost_status UNKNOWN caps confidence at "
                f"{UNKNOWN_COST_MAX_CONFIDENCE} (PROFIT-003 gate)"
            )
    return (not failures, failures)


def _decision_reasons(
    output: ProductAnalysisOutput,
    *,
    enforced_reject: bool,
    rule_results: list[dict],
) -> list[str]:
    """Explainable reasons for the persisted decision proposal."""
    reasons = [
        f"AI market reasoning: {output.market_reasoning[:800]}",
        f"model confidence {output.confidence}",
    ]
    if enforced_reject:
        reasons.append("hard product gate failed; decision enforced to reject")
    for result in rule_results:
        if not result.get("passed", True):
            reasons.append(
                f"rule {result.get('rule_id')} v{result.get('version')}: "
                f"{result.get('failed_message', 'failed')}"
            )
    return reasons[:10]


async def _persist_failure(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    context: dict,
    error: str,
    provider: str | None,
    model: str | None,
    tokens: dict[str, int],
    cost: Decimal,
    latency_ms: int,
    prompt_version: str | None,
    trace_id: str | None,
) -> ProductAnalysisRun:
    """Record a failed run for audit; no decision is proposed."""
    run = ProductAnalysisRun(
        workspace_id=workspace_id,
        product_id=product_id,
        provider=provider or "unknown",
        model=model or "unknown",
        prompt_version=prompt_version,
        input_snapshot=context,
        output={"error": error},
        token_usage=tokens,
        estimated_cost=cost,
        latency_ms=latency_ms,
        status="failed",
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()
    agent_run = AiAgentRun(
        workspace_id=workspace_id,
        agent=AGENT_NAME,
        trigger=TRIGGER,
        input={"product_id": str(product_id)},
        plan={"steps": ["build_context", "prompt", "llm", "validate"]},
        tool_calls=[],
        output={"error": error},
        approval={"required": False, "status": "not_required"},
        cost=cost,
        status="failed",
        trace_id=trace_id,
        completed_at=datetime.now(UTC),
    )
    session.add(agent_run)
    await session.flush()
    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.analyst.failed",
        entity_type="product",
        entity_id=str(product_id),
        payload={"error": error[:500]},
        trace_id=trace_id,
    )
    return run


async def analyze_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    gateway_complete: GatewayComplete | None = None,
    trace_id: str | None = None,
    prompt_name: str | None = None,
    re_raise_llm_errors: bool = False,
) -> ProductAnalysisResult:
    """Run the Product Analyst Agent v1 pipeline for a product.

    Never approves/publishes/purchases anything: it only persists an audit
    run and, on success, a pending decision proposal.

    Args:
        gateway_complete: optional injected LLM callable (tests mock this).
        prompt_name: registry prompt to use (defaults to PRODUCT_ANALYST);
            the M5.2 worker passes the runtime-bound AGENT_<ID> prompt.
        re_raise_llm_errors: when True, LLM gateway errors propagate
            unwrapped so the M5.1 worker can classify and retry them.
    """
    await _load_product(session, workspace_id=workspace_id, product_id=product_id)

    # 1. Product context (read-only).
    context = await product_context.build_product_context(
        session, workspace_id=workspace_id, product_id=product_id, trace_id=trace_id
    )
    context = _json_safe(context)

    # 2. Prompt from the registry (never hardcoded).
    prompt_name = prompt_name or PROMPT_NAME
    prompt = await prompt_registry.get_active_prompt(
        session, workspace_id=workspace_id, name=prompt_name
    )
    rendered = await prompt_registry.render_prompt(
        session,
        workspace_id=workspace_id,
        name=prompt_name,
        variables={
            "context_json": json.dumps(context, ensure_ascii=False),
            "output_schema": json.dumps(
                ProductAnalysisOutput.model_json_schema(), ensure_ascii=False
            ),
        },
        trace_id=trace_id,
    )

    # 3. LLM Gateway call (single entry point; no direct model access).
    request = LLMRequest(
        messages=[
            {"role": "system", "content": rendered.text},
            {
                "role": "user",
                "content": (
                    "Analyze the provided product context and respond ONLY with "
                    "a JSON object matching the output schema."
                ),
            },
        ],
        task_type="product_analyst",
        response_format="json_object",
        temperature=0.2,
    )
    caller = gateway_complete or llm_gateway.complete
    try:
        response = await caller(request, trace_id=trace_id)
    except LLMError as exc:
        if re_raise_llm_errors:
            # Let the M5.1 worker classify and retry provider/network/timeout.
            raise
        raise ProductAnalystError(f"LLM call failed: {exc}") from exc

    # 4. Structured output + validation.
    try:
        parsed = parse_json_content(response.content)
        output = ProductAnalysisOutput.model_validate(parsed)
    except (LLMError, ValueError) as exc:
        await _persist_failure(
            session,
            workspace_id=workspace_id,
            product_id=product_id,
            context=context,
            error=f"invalid structured output: {exc}",
            provider=response.provider,
            model=response.model,
            tokens=response.tokens,
            cost=response.cost,
            latency_ms=response.latency_ms,
            prompt_version=prompt.version,
            trace_id=trace_id,
        )
        raise ProductAnalystError(f"invalid structured output: {exc}") from exc

    # Rule gate check (rules loaded from the database; deterministic veto).
    from app.services import rule_engine

    rule_results_raw = await rule_engine.check(
        session,
        workspace_id=workspace_id,
        group="PRODUCT",
        context=_rule_context(context, recommended_price=output.pricing.recommended_price),
        trace_id=trace_id,
    )
    rule_results = [result.model_dump() for result in rule_results_raw.results]
    vetoed = any(
        result.get("rule_type") == "hard" and not result.get("passed", True)
        for result in rule_results
    )
    valid, failures = _validate_output(output, context=context)
    if not valid:
        await _persist_failure(
            session,
            workspace_id=workspace_id,
            product_id=product_id,
            context=context,
            error="; ".join(failures),
            provider=response.provider,
            model=response.model,
            tokens=response.tokens,
            cost=response.cost,
            latency_ms=response.latency_ms,
            prompt_version=prompt.version,
            trace_id=trace_id,
        )
        raise ProductAnalystError("output failed validation: " + "; ".join(failures))

    # Deterministic enforcement: a hard veto overrides the LLM decision.
    enforced_reject = vetoed and output.decision != "reject"
    decision_value = "reject" if enforced_reject else output.decision

    # 5. Audit: analysis run + decision proposal + agent run + event.
    score_total = _as_decimal(context.get("score", {}).get("total"))
    max_cac = output.pricing.max_cac
    if max_cac is None and output.pricing.recommended_price is not None:
        landed = _as_decimal(context["landed_cost"]["total_landed_cost"]) or Decimal("0")
        if landed > Decimal("0"):
            max_cac = (output.pricing.recommended_price - landed).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )

    output_payload = _json_safe(output.model_dump())
    output_payload["enforced_decision"] = "reject" if enforced_reject else None
    run = ProductAnalysisRun(
        workspace_id=workspace_id,
        product_id=product_id,
        provider=response.provider,
        model=response.model,
        prompt_version=prompt.version,
        input_snapshot=context,
        output=output_payload,
        token_usage=response.tokens,
        estimated_cost=response.cost,
        latency_ms=response.latency_ms,
        status="completed",
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()

    decision = ProductDecision(
        workspace_id=workspace_id,
        product_id=product_id,
        decision=decision_value,
        score=score_total,
        confidence=output.confidence,
        reasons=_decision_reasons(
            output, enforced_reject=enforced_reject, rule_results=rule_results
        ),
        risks=_json_safe(output.risks),
        recommended_price=output.pricing.recommended_price,
        max_cac=max_cac,
        test_quantity=output.test_plan.quantity if decision_value == "test" else None,
        test_days=output.test_plan.days if decision_value == "test" else None,
        approval_status="pending",
        trace_id=trace_id,
    )
    session.add(decision)
    await session.flush()

    agent_run = AiAgentRun(
        workspace_id=workspace_id,
        agent=AGENT_NAME,
        trigger=TRIGGER,
        input={"product_id": str(product_id), "prompt_version": prompt.version},
        plan={
            "steps": [
                "build_product_context",
                "load_prompt",
                "llm_gateway",
                "validate_structured_output",
                "rule_gate_check",
            ]
        },
        tool_calls=[
            {
                "tool": "llm_gateway.complete",
                "provider": response.provider,
                "model": response.model,
                "tokens": response.tokens,
                "latency_ms": response.latency_ms,
            }
        ],
        output=_json_safe(output.model_dump()),
        approval={"required": True, "status": "pending", "target": "product_decisions"},
        cost=response.cost,
        status="completed",
        trace_id=trace_id,
        completed_at=datetime.now(UTC),
    )
    session.add(agent_run)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type="product.analyst.analyzed",
        entity_type="product",
        entity_id=str(product_id),
        payload={
            "run_id": str(run.id),
            "decision": decision_value,
            "confidence": str(output.confidence),
            "recommended_price": (
                str(output.pricing.recommended_price)
                if output.pricing.recommended_price is not None
                else None
            ),
            "provider": response.provider,
            "model": response.model,
            "estimated_cost": str(response.cost),
            "approval_status": "pending",
        },
        trace_id=trace_id,
    )
    logger.info(
        "product analyst %s decision=%s confidence=%s cost=%s trace=%s",
        product_id,
        decision_value,
        output.confidence,
        response.cost,
        trace_id,
    )
    return ProductAnalysisResult(analysis_run=run, decision=decision, output=output)


async def latest_runs(
    session: AsyncSession, *, workspace_id: UUID, product_id: UUID, limit: int = 20
) -> list[ProductAnalysisRun]:
    """List the most recent analyst runs for a product (newest first)."""
    rows = (
        (
            await session.execute(
                select(ProductAnalysisRun)
                .where(
                    ProductAnalysisRun.workspace_id == workspace_id,
                    ProductAnalysisRun.product_id == product_id,
                    ProductAnalysisRun.provider != "deterministic",
                )
                .order_by(ProductAnalysisRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def to_result_out(
    result: ProductAnalysisResult,
    *,
    prompt_version: str | None = None,
) -> ProductAnalysisResultOut:
    """Serialize a run result for the API response."""
    run = result.analysis_run
    decision = result.decision
    output = result.output
    return ProductAnalysisResultOut(
        analysis_run_id=run.id,
        provider=run.provider,
        model=run.model,
        prompt_version=prompt_version or run.prompt_version or "",
        decision_proposal_id=decision.id if decision else None,
        decision=decision.decision if decision else (output.decision if output else None),
        confidence=decision.confidence if decision else (output.confidence if output else None),
        recommended_price=(
            decision.recommended_price
            if decision
            else (output.pricing.recommended_price if output else None)
        ),
        max_cac=decision.max_cac if decision else (output.pricing.max_cac if output else None),
        test_quantity=decision.test_quantity if decision else None,
        test_days=decision.test_days if decision else None,
        tokens=run.token_usage,
        estimated_cost=run.estimated_cost,
        latency_ms=run.latency_ms,
        trace_id=run.trace_id,
        status=run.status,
        approval_status=decision.approval_status if decision else None,
    )
