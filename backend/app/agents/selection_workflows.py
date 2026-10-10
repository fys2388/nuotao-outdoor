"""LangGraph-based selection workflow — the AI Native product selection DAG.

Implements the 6-step selection SOP from the Nuotao Outdoor product
selection guide as a LangGraph StateGraph:

    market_data → initial_screening → v3_scoring → veto_check
    → decision → persist

Each node is an async function that reads from and writes to the
SelectionWorkflowState. Conditional edges route based on veto results
and scores.

Design principles (AGENTS.md):
- Agent is a "proposer" not an "executor": the workflow generates
  decision proposals; human approval is required (Human-in-the-loop).
- Full-chain auditable: every node's input/output is persisted to
  product_analysis_runs and ai_agent_runs.
- No hardcoded business values: weights, thresholds, and rules are
  loaded from configuration / strategy_versions.
- Single LLM gateway: complex AI tasks delegate to the Product Analyst
  Agent via the LLM Gateway (never direct model calls).
- Graceful degradation: when LLM is unavailable, deterministic scoring
  is used; when data is missing, uncertain verdicts are returned.

Usage:
    from app.agents.selection_workflows import build_selection_graph
    graph = build_selection_graph()
    result = await graph.ainvoke(initial_state)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import uuid4

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.schemas.selection_workflow import (
    DecisionType,
    FunnelStage,
    MarketDataSnapshot,
    NuotaoScoreDimensions,
    OperationalScore,
    SelectionWorkflowState,
    VetoCheckResult,
)
from app.services.selection_rules import (
    VetoRuleContext,
    any_veto_failed,
    evaluate_all_vetoes,
)
from app.services.selection_scorecard import (
    OPERATIONAL_WEIGHTS,
    ScorecardError,
    compute_operational_score,
    load_operational_weights,
    map_operational_to_nuotao,
)
from app.services.nuotao_score_v3 import (
    brand_fit_veto,
    compute_nuotao_score,
    grade_of,
)

logger = logging.getLogger(__name__)


# ── Node: market_data_collection ────────────────────────────────────
async def market_data_collection_node(
    state: SelectionWorkflowState,
) -> dict[str, Any]:
    """Collect market intelligence from all data sources.

    Writes: market_data, current_stage='recalled'
    """
    from app.integrations.market_data import MarketDataCollector

    collector = MarketDataCollector()
    try:
        snapshot = await collector.collect(
            product_name=state.product_name or state.product_id,
            category=state.category,
            target_market=state.target_market,
        )
        state.market_data = snapshot
        logger.info(
            "Market data collected for %s: %s",
            state.product_id,
            snapshot.data_sources,
        )
    except Exception as exc:
        logger.warning("Market data collection failed: %s", exc)
        # Degrade: continue with no market data (neutral defaults)

    return {"market_data": state.market_data, "current_stage": "recalled"}


# ── Node: initial_screening ─────────────────────────────────────────
async def initial_screening_node(
    state: SelectionWorkflowState,
) -> dict[str, Any]:
    """Apply the 6 hard gates (one-strike-out) from the selection guide.

    Gates:
    1. Compliance: not infringing, not dangerous goods
    2. Supply chain: >= 3 suppliers on 1688, unit price 15-200 CNY
    3. Fulfillment: < 500g, dimensions < 60cm, not fragile
    4. Demand: not declining, Amazon category search > 10k/month
    5. Competition: not a red-ocean category
    6. Differentiation: at least 1 improvement point

    Writes: current_stage='screened' or 'rejected'
    """
    # MVP: use market data + category heuristics for screening.
    # Production: load product context from DB, check against rules.
    md = state.market_data
    rejected = False
    rejection_reasons: list[str] = []

    # Gate 1: Compliance (dangerous goods / infringement)
    # MVP: no structured compliance data, skip (will be checked by V1-V4)
    pass

    # Gate 2: Supply chain
    # MVP: no supplier data, skip (will be checked by V11)
    pass

    # Gate 3: Fulfillment
    # MVP: no weight/size data, skip
    pass

    # Gate 4: Demand (from market data)
    if md and md.google_trends_direction == "declining":
        rejected = True
        rejection_reasons.append("Google Trends declining")

    # Gate 4b: Category-specific seasonality (from category config)
    from app.services.category_config_service import get_category_seasonal_weight
    from datetime import datetime as _dt
    now = _dt.now()
    quarter = f"Q{(now.month - 1) // 3 + 1}"
    cat_config = state.category_config or {}
    seasonal_weight = get_category_seasonal_weight(cat_config, quarter)
    if seasonal_weight < 0.8:  # Off-season threshold
        rejection_reasons.append(f"Category off-season ({quarter}, weight={seasonal_weight})")
        # Off-season is a warning, not a hard reject (product can be prepared early)

    # Gate 5: Competition
    if md and md.amazon_competition_level == "high":
        rejection_reasons.append("Amazon competition level: high")

    # Gate 6: Differentiation
    # MVP: no differentiation data, skip (will be checked by V7)
    pass

    if rejected:
        state.current_stage = "rejected"
        state.reasons = rejection_reasons
        logger.info("Product %s rejected at initial screening", state.product_id)
    else:
        state.current_stage = "screened"
        logger.info("Product %s passed initial screening", state.product_id)

    return {"current_stage": state.current_stage, "reasons": state.reasons}


# ── Node: v3_scoring ────────────────────────────────────────────────
async def v3_scoring_node(
    state: SelectionWorkflowState,
) -> dict[str, Any]:
    """Compute the V2.0 operational score and V3.0 Nuotao Score.

    Steps:
    1. Build the 11-dimension operational score from context data
    2. Map to the 6-dimension Nuotao Score
    3. Compute the weighted Nuotao Score total (0-100)
    4. Determine the grade (hero/core/long_tail/reject)

    Writes: operational_score, nuotao_score_total, nuotao_grade,
            current_stage='deep_candidate'
    """
    md = state.market_data

    # ── Step 1: Build operational score ──
    # Use market data + product context to populate the 11 dimensions.
    # MVP: derive from available data, use neutral defaults for missing data.
    operational_dims = {
        "supplier_quality": 50.0,  # default: needs real 1688 data
        "sales_validation": 50.0,  # default: needs real sales data
        "margin_rate": 50.0,  # default: needs cost model
        "product_quality": 50.0,  # default: needs supplier quality data
        "logistics_support": 50.0,  # default: needs logistics data
        "differentiation": 50.0,  # default: needs product analysis
        "market_heat": md.google_trends_score * 10 if md else 50.0,
        "amazon_competition": _competition_to_score(md),
        "seasonality": md.seasonality_score * 10 if md else 50.0,
        "ai_image_difficulty": 50.0,  # default: needs image analysis
        "compliance_risk": 50.0,  # default: needs compliance check
    }

    # Load configurable weights
    workspace_id = state.workspace_id or "00000000-0000-0000-0000-000000000001"
    # Use category-specific weights from state if loaded, otherwise defaults
    weights = state.operational_weights or OPERATIONAL_WEIGHTS

    try:
        op_result = compute_operational_score(operational_dims, weights)
        state.operational_score = OperationalScore(
            supplier_quality=op_result["dimensions"]["supplier_quality"],
            sales_validation=op_result["dimensions"]["sales_validation"],
            margin_rate=op_result["dimensions"]["margin_rate"],
            product_quality=op_result["dimensions"]["product_quality"],
            logistics_support=op_result["dimensions"]["logistics_support"],
            differentiation=op_result["dimensions"]["differentiation"],
            market_heat=op_result["dimensions"]["market_heat"],
            amazon_competition=op_result["dimensions"]["amazon_competition"],
            seasonality=op_result["dimensions"]["seasonality"],
            ai_image_difficulty=op_result["dimensions"]["ai_image_difficulty"],
            compliance_risk=op_result["dimensions"]["compliance_risk"],
            total=op_result["total"],
        )
    except ScorecardError as exc:
        logger.warning("Operational score computation failed: %s", exc)
        state.operational_score = None

    # ── Step 2: Map to Nuotao Score ──
    # Brand Fit comes from the category configuration (strategy_versions).
    # MVP fallback: 5.0 when no category config is loaded.
    from app.services.category_config_service import get_category_brand_fit_base
    brand_fit = get_category_brand_fit_base(state.category_config or {})

    if state.operational_score is not None:
        try:
            op_dims = {
                "supplier_quality": state.operational_score.supplier_quality,
                "sales_validation": state.operational_score.sales_validation,
                "margin_rate": state.operational_score.margin_rate,
                "product_quality": state.operational_score.product_quality,
                "logistics_support": state.operational_score.logistics_support,
                "differentiation": state.operational_score.differentiation,
                "market_heat": state.operational_score.market_heat,
                "amazon_competition": state.operational_score.amazon_competition,
                "seasonality": state.operational_score.seasonality,
                "ai_image_difficulty": state.operational_score.ai_image_difficulty,
                "compliance_risk": state.operational_score.compliance_risk,
            }
            nuotao_dims = map_operational_to_nuotao(
                {"dimensions": op_dims}, brand_fit=brand_fit
            )
            state.nuotao_dimensions = NuotaoScoreDimensions(
                value=nuotao_dims["value"],
                utility=nuotao_dims["utility"],
                weight_packability=nuotao_dims["weight_packability"],
                durability=nuotao_dims["durability"],
                brand_fit=nuotao_dims["brand_fit"],
                differentiation=nuotao_dims["differentiation"],
            )

            # ── Step 3: Compute Nuotao Score total ──
            nuotao_input = {
                "value": nuotao_dims["value"],
                "utility": nuotao_dims["utility"],
                "weight_packability": nuotao_dims["weight_packability"],
                "durability": nuotao_dims["durability"],
                "brand_fit": nuotao_dims["brand_fit"],
                "differentiation": nuotao_dims["differentiation"],
            }
            nuotao_result = compute_nuotao_score(nuotao_input)
            state.nuotao_score_total = float(nuotao_result["total"])
            state.nuotao_grade = nuotao_result["grade"]

            # ── Step 4: Check Brand Fit veto ──
            if brand_fit_veto(Decimal(str(brand_fit))):
                state.reasons.append(
                    f"Brand Fit {brand_fit} below hard floor 5.0 (V8)"
                )
        except (ScorecardError, ValueError) as exc:
            logger.warning("Nuotao Score computation failed: %s", exc)
            state.nuotao_score_total = None
            state.nuotao_grade = None

    # Advance to deep_candidate if score >= 65
    if state.nuotao_score_total is not None and state.nuotao_score_total >= 65:
        state.current_stage = "deep_candidate"
    else:
        state.current_stage = "screened"

    return {
        "operational_score": state.operational_score,
        "nuotao_score_total": state.nuotao_score_total,
        "nuotao_dimensions": state.nuotao_dimensions,
        "nuotao_grade": state.nuotao_grade,
        "current_stage": state.current_stage,
    }


def _competition_to_score(md: MarketDataSnapshot | None) -> float:
    """Convert Amazon competition level to a 0-100 score (higher = less competition)."""
    if md is None:
        return 50.0
    mapping = {"low": 90.0, "medium": 60.0, "high": 30.0}
    return mapping.get(md.amazon_competition_level or "medium", 50.0)


# ── Node: veto_check ────────────────────────────────────────────────
async def veto_check_node(
    state: SelectionWorkflowState,
) -> dict[str, Any]:
    """Evaluate V1-V12 proactive veto rules.

    Steps:
    1. Build the VetoRuleContext from available data
    2. Run all 12 deterministic/hybrid rules
    3. Mark veto_passed based on results

    Writes: veto_results, veto_passed, current_stage='test_candidate' or 'rejected'
    """
    # Build veto context from available data
    from app.services.category_config_service import (
        get_category_banned_subcategories,
        get_category_compliance_requirements,
    )

    cat_config = state.category_config or {}
    compliance_reqs = get_category_compliance_requirements(cat_config)
    banned_subs = get_category_banned_subcategories(cat_config)

    context = VetoRuleContext(
        reference_price_usd=None,  # MVP: no price data
        margin_rate=None,
        shipping_ratio=None,
        brand_fit=Decimal(str(state.nuotao_dimensions.brand_fit))
        if state.nuotao_dimensions
        else None,
        nuotao_score_total=Decimal(str(state.nuotao_score_total))
        if state.nuotao_score_total
        else None,
        supplier_rating=None,
        category=state.category,
        category_in_banned_list=None,
        category_overlaps_hero=None,
        return_rate=None,
        is_banned_shipment=None,
        ai_reasons={},
        compliance_requirements=compliance_reqs,
        banned_subcategories=banned_subs,
    )

    # Evaluate all 12 rules
    results = evaluate_all_vetoes(context)
    state.veto_results = results

    # Check if any veto failed
    state.veto_passed = not any_veto_failed(results)

    # Advance stage
    if state.veto_passed and state.nuotao_score_total is not None:
        state.current_stage = "test_candidate"
    elif not state.veto_passed:
        state.current_stage = "rejected"
        failed = [r.rule_id for r in results if r.verdict == "fail"]
        state.risks.append(f"Veto failed: {', '.join(failed)}")

    logger.info(
        "Veto check for %s: passed=%s, results=%s",
        state.product_id,
        state.veto_passed,
        {r.rule_id: r.verdict for r in results},
    )

    return {
        "veto_results": state.veto_results,
        "veto_passed": state.veto_passed,
        "current_stage": state.current_stage,
        "risks": state.risks,
    }


# ── Node: decision ──────────────────────────────────────────────────
async def decision_node(
    state: SelectionWorkflowState,
) -> dict[str, Any]:
    """Generate the decision recommendation.

    Logic (V3.0 §2.3):
    - veto_passed=False → reject
    - Nuotao Score >= 85 → test (Hero Candidate)
    - Nuotao Score 65-84 → test (Core)
    - Nuotao Score < 65 → hold (Long-tail)

    Writes: recommended_decision, confidence, reasons, risks, status='waiting_approval'
    """
    reasons: list[str] = list(state.reasons)
    risks: list[str] = list(state.risks)

    if not state.veto_passed:
        state.recommended_decision = "reject"
        state.confidence = Decimal("0.9")
        reasons.append("One or more veto rules failed")
        failed = [r.rule_id for r in state.veto_results if r.verdict == "fail"]
        reasons.append(f"Failed rules: {', '.join(failed)}")
    elif state.nuotao_score_total is not None:
        score = state.nuotao_score_total
        if score >= 85:
            state.recommended_decision = "test"
            state.confidence = Decimal("0.85")
            reasons.append(f"Nuotao Score {score:.0f} >= 85 (Hero Candidate)")
        elif score >= 65:
            state.recommended_decision = "test"
            state.confidence = Decimal("0.7")
            reasons.append(f"Nuotao Score {score:.0f} >= 65 (Core)")
        else:
            state.recommended_decision = "hold"
            state.confidence = Decimal("0.5")
            reasons.append(f"Nuotao Score {score:.0f} < 65 (Long-tail)")
    else:
        state.recommended_decision = "hold"
        state.confidence = Decimal("0.3")
        reasons.append("Insufficient data for scoring")

    state.reasons = reasons
    state.risks = risks
    state.status = "waiting_approval"

    logger.info(
        "Decision for %s: %s (confidence=%s)",
        state.product_id,
        state.recommended_decision,
        state.confidence,
    )

    return {
        "recommended_decision": state.recommended_decision,
        "confidence": state.confidence,
        "reasons": state.reasons,
        "risks": state.risks,
        "status": state.status,
    }


# ── Conditional edges ───────────────────────────────────────────────
def _route_after_screening(
    state: SelectionWorkflowState,
) -> str:
    """Route after initial screening: screened → v3_scoring, rejected → END."""
    if state.current_stage == "rejected":
        return END
    return "v3_scoring"


def _route_after_veto(
    state: SelectionWorkflowState,
) -> str:
    """Route after veto check: passed → decision, rejected → END."""
    if state.veto_passed is False:
        return END
    return "decision"


# ── Graph builder ───────────────────────────────────────────────────
def build_selection_graph() -> CompiledStateGraph:
    """Build and compile the LangGraph selection workflow.

    DAG:
        market_data → initial_screening → v3_scoring → veto_check → decision → END
                                              ↓ (conditional)
                                             END (rejected)
    """
    graph = StateGraph(SelectionWorkflowState)

    # Add nodes
    graph.add_node("market_data", market_data_collection_node)
    graph.add_node("initial_screening", initial_screening_node)
    graph.add_node("v3_scoring", v3_scoring_node)
    graph.add_node("veto_check", veto_check_node)
    graph.add_node("decision", decision_node)

    # Add edges
    graph.set_entry_point("market_data")
    graph.add_edge("market_data", "initial_screening")
    graph.add_conditional_edges("initial_screening", _route_after_screening)
    graph.add_edge("v3_scoring", "veto_check")
    graph.add_conditional_edges("veto_check", _route_after_veto)
    graph.add_edge("decision", END)

    return graph.compile()


# ── Convenience: build initial state ────────────────────────────────
def make_initial_state(
    *,
    workspace_id: str,
    product_id: str,
    product_name: str | None = None,
    category: str | None = None,
    target_market: str = "US",
    trace_id: str | None = None,
) -> SelectionWorkflowState:
    """Create a fresh SelectionWorkflowState for a new workflow run."""
    return SelectionWorkflowState(
        workspace_id=workspace_id,
        product_id=product_id,
        product_name=product_name,
        category=category,
        target_market=target_market,
        current_stage="recalled",
        status="running",
        trace_id=trace_id or f"selection-{uuid4().hex[:12]}",
        run_id=str(uuid4()),
    )
