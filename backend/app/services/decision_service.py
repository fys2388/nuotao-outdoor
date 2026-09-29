"""Decision Cockpit service: unified read model aggregation for product decisions.

Aggregates data from Product, ProductAnalysisRun, ProductNuotaoScore, ProductCost,
Supplier, SourcingCandidate, RuleExecutionLog, AgentApproval, EventLog,
WooCommerceDraft, ListingJob, and Product.mastered_* fields into a single
ProductDecisionView.

UNKNOWN semantics: any missing real data is reported as UNKNOWN, never coerced
to 0, PASS, or APPROVE.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_operations import AgentApproval
from app.models.event import EventLog
from app.models.listing_job import ListingJob
from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductAnalysisRun,
    ProductNuotaoScore,
    SourcingCandidate,
    WooCommerceDraft,
)
from app.models.rule import RuleExecutionLog
from app.models.supplier import Supplier
from app.schemas.product import ProductOut
from app.schemas.product_intelligence import (
    DecisionBlocker,
    DecisionNextAction,
    DecisionRuleResult,
    ProductDecisionView,
)


class DecisionServiceError(Exception):
    """Raised when decision aggregation fails."""


def _derive_stage(product: Product, analysis: ProductAnalysisRun | None, score: ProductNuotaoScore | None,
                  cost: ProductCost | None, listing: ListingJob | None, wc_draft: WooCommerceDraft | None) -> str:
    """Derive the user-facing stage from the current real state axes.

    Stage priority (first match wins):
    1. WooCommerce: wc_draft exists and status != 'generated' OR listing published
    2. B2C Listing: listing job exists and status in (pending, approved, processing)
    3. Product Master: product.mastered_at is not None
    4. Pending Approval: approval pending for PRODUCT_CANDIDATE or PRODUCT_MASTER
    5. Analysis: analysis run exists OR score exists
    6. Candidate: product.candidate_status == 'candidate'
    7. Opportunity: default (no data yet)
    """
    # WooCommerce
    if wc_draft and wc_draft.status in ("pushed", "synced"):
        return "WooCommerce"
    if listing and listing.status == "published":
        return "WooCommerce"

    # B2C Listing
    if listing and listing.status in ("pending", "approved", "processing"):
        return "B2C Listing"

    # Product Master
    if product.mastered_at is not None:
        return "Product Master"

    # Pending Approval - check if there's a pending approval
    # (will be checked in the service, but we can check candidate_status)
    if product.candidate_status == "approved":
        return "Pending Approval"

    # Analysis
    if analysis is not None or score is not None:
        return "Analysis"

    # Candidate
    if product.candidate_status == "candidate":
        return "Candidate"

    # Opportunity (default)
    return "Opportunity"


def _get_ai_recommendation(analysis: ProductAnalysisRun | None) -> tuple[str, list[str], list[str]]:
    """Extract AI recommendation, reasons, and risks from analysis output."""
    if analysis is None:
        return "UNKNOWN", [], []

    output = analysis.output or {}
    recommendation = output.get("recommendation", "UNKNOWN")
    reasons = output.get("reasons", [])
    risks = output.get("risks", [])

    # Normalize recommendation
    if recommendation in ("RECOMMEND", "REVIEW", "REJECT"):
        return recommendation, reasons, risks

    # Try alternate keys
    ai_reco = output.get("ai_recommendation")
    if ai_reco in ("RECOMMEND", "REVIEW", "REJECT"):
        return ai_reco, reasons, risks

    # If decision is in output
    decision = output.get("decision")
    if decision in ("test", "hold", "reject"):
        mapping = {"test": "RECOMMEND", "hold": "REVIEW", "reject": "REJECT"}
        return mapping.get(decision, "UNKNOWN"), reasons, risks

    return "UNKNOWN", reasons, risks


def _get_rule_results(rule_logs: list[RuleExecutionLog]) -> list[DecisionRuleResult]:
    """Convert rule execution logs to DecisionRuleResult list."""
    results = []
    for log in rule_logs:
        result_data = log.result or {}
        passed = result_data.get("passed")

        if passed is None:
            result_value = "UNKNOWN"
        elif passed:
            result_value = "PASS"
        else:
            result_value = "FAIL"

        reason = result_data.get("reason") or result_data.get("message") or result_data.get("reasons")
        if isinstance(reason, list):
            reason = "; ".join(str(r) for r in reason)

        results.append(
            DecisionRuleResult(
                rule_id=log.rule_id,
                rule_version=log.rule_version,
                name=result_data.get("name", log.rule_id),
                result=result_value,
                reason=reason,
                trace_id=log.trace_id,
            )
        )

    return results


def _count_rule_results(results: list[DecisionRuleResult]) -> dict[str, int]:
    """Count rule results by status."""
    counts = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}
    for r in results:
        counts[r.result] += 1
    return counts


def _calculate_margin(cost: ProductCost | None, retail_price: Decimal | None) -> Decimal | None:
    """Calculate margin percentage from cost and retail price.

    Returns None if either cost or price is missing (UNKNOWN).
    """
    if cost is None or retail_price is None or cost.total_landed_cost is None or cost.total_landed_cost == 0:
        return None
    if retail_price <= 0:
        return None

    margin = (retail_price - cost.total_landed_cost) / retail_price * 100
    return round(margin, 2)


def _calculate_freight_share(cost: ProductCost | None) -> Decimal | None:
    """Calculate freight share as international_shipping / landed_cost.

    Returns None if either is missing or zero (UNKNOWN).
    """
    if cost is None or cost.total_landed_cost is None or cost.total_landed_cost == 0:
        return None
    if cost.international_shipping is None or cost.international_shipping == 0:
        return None

    share = cost.international_shipping / cost.total_landed_cost * 100
    return round(share, 2)


def _get_retail_price(product: Product) -> Decimal | None:
    """Extract retail price from product attributes or meta."""
    # Try attributes first
    if product.attributes and isinstance(product.attributes, dict):
        price = product.attributes.get("retail_price") or product.attributes.get("price")
        if price is not None:
            try:
                return Decimal(str(price))
            except Exception:
                pass

    # Try meta
    if product.meta and isinstance(product.meta, dict):
        price = product.meta.get("retail_price") or product.meta.get("price")
        if price is not None:
            try:
                return Decimal(str(price))
            except Exception:
                pass

    return None


def _identify_blockers(
    product: Product,
    cost: ProductCost | None,
    supplier: Supplier | None,
    sourcing: SourcingCandidate | None,
    rule_results: list[DecisionRuleResult],
    approval: AgentApproval | None,
    listing: ListingJob | None,
    wc_draft: WooCommerceDraft | None,
) -> list[DecisionBlocker]:
    """Identify blockers preventing progress in the product lifecycle."""
    blockers = []

    # MISSING_COST: no cost data
    if cost is None:
        blockers.append(
            DecisionBlocker(
                code="MISSING_COST",
                severity="high",
                message="Product has no cost data recorded.",
                source="ProductCost",
                action="Enter product cost in Cost Management.",
            )
        )

    # MISSING_SUPPLY_DATA: no supplier or sourcing data
    if supplier is None and sourcing is None:
        blockers.append(
            DecisionBlocker(
                code="MISSING_SUPPLY_DATA",
                severity="medium",
                message="No supplier or sourcing data available.",
                source="Supplier/SourcingCandidate",
                action="Add supplier or sourcing candidate.",
            )
        )
    elif sourcing is None and supplier is not None:
        # Supplier exists but no sourcing candidate with lead_time/moq
        if not supplier.contact.get("lead_time_days") and not supplier.contact.get("moq"):
            blockers.append(
                DecisionBlocker(
                    code="MISSING_SUPPLY_DATA",
                    severity="low",
                    message="Supplier exists but lead time and MOQ are not recorded.",
                    source="SupplierProfile",
                    action="Update supplier profile with lead time and MOQ.",
                )
            )

    # RULE_FAIL: any hard rule failed
    fail_count = sum(1 for r in rule_results if r.result == "FAIL")
    if fail_count > 0:
        failing_rules = [r.rule_id for r in rule_results if r.result == "FAIL"]
        blockers.append(
            DecisionBlocker(
                code="RULE_FAIL",
                severity="high",
                message=f"{fail_count} hard rule(s) failed: {', '.join(failing_rules[:3])}",
                source="RuleExecutionLog",
                action="Review failed rules and take corrective action.",
            )
        )

    # RULE_UNKNOWN: any hard rule has UNKNOWN result
    unknown_count = sum(1 for r in rule_results if r.result == "UNKNOWN")
    if unknown_count > 0:
        unknown_rules = [r.rule_id for r in rule_results if r.result == "UNKNOWN"]
        blockers.append(
            DecisionBlocker(
                code="RULE_UNKNOWN",
                severity="medium",
                message=f"{unknown_count} hard rule(s) have UNKNOWN result (no evaluation): {', '.join(unknown_rules[:3])}",
                source="RuleExecutionLog",
                action="Run rule evaluation to get results.",
            )
        )

    # MISSING_ANALYSIS: no analysis run
    if not product.candidate_status and not product.mastered_at:
        # Only flag if product is not mastered and has no candidate status
        # (meaning it's a raw opportunity)
        pass  # Not a blocker, just early stage

    # PENDING_APPROVAL: approval is pending
    if approval and approval.status == "pending":
        blockers.append(
            DecisionBlocker(
                code="PENDING_APPROVAL",
                severity="medium",
                message=f"Approval is pending (type: {approval.approval_type}).",
                source="AgentApproval",
                action="Complete the approval decision.",
            )
        )

    # LISTING_NOT_APPROVED: listing exists but not approved
    if listing and listing.status == "pending":
        blockers.append(
            DecisionBlocker(
                code="LISTING_NOT_APPROVED",
                severity="medium",
                message="Listing job is pending review.",
                source="ListingJob",
                action="Review and approve the listing job.",
            )
        )

    # WC_SYNC_FAILED: WC sync failed
    if listing and listing.status == "failed":
        blockers.append(
            DecisionBlocker(
                code="WC_SYNC_FAILED",
                severity="high",
                message="WooCommerce sync failed.",
                source="ListingJob",
                action="Check WC sync logs and retry.",
            )
        )

    return blockers


def _derive_next_action(
    product: Product,
    stage: str,
    cost: ProductCost | None,
    rule_results: list[DecisionRuleResult],
    blockers: list[DecisionBlocker],
    approval: AgentApproval | None,
    listing: ListingJob | None,
) -> DecisionNextAction:
    """Derive the recommended next action from the current state."""
    blocker_codes = [b.code for b in blockers]

    # High severity blockers take priority (but not for early stages)
    early_stages = ("Opportunity", "Candidate")
    is_early_stage = stage in early_stages

    # WC_SYNC_FAILED always overrides
    if "WC_SYNC_FAILED" in blocker_codes:
        return DecisionNextAction(
            action="SYNC_WC",
            reason="WooCommerce sync failed. Check logs and retry.",
            blockers=blocker_codes,
        )

    # RULE_FAIL always overrides
    if "RULE_FAIL" in blocker_codes:
        return DecisionNextAction(
            action="SUPPLEMENT_DATA",
            reason="Hard rules failed. Review and fix failing conditions.",
            blockers=blocker_codes,
        )

    # LISTING_NOT_APPROVED overrides
    if "LISTING_NOT_APPROVED" in blocker_codes:
        return DecisionNextAction(
            action="SUBMIT_APPROVAL",
            reason="Listing job is pending review.",
            blockers=blocker_codes,
        )

    # PENDING_APPROVAL overrides
    if "PENDING_APPROVAL" in blocker_codes:
        return DecisionNextAction(
            action="APPROVE",
            reason="Approval is pending. Complete the approval decision.",
            blockers=blocker_codes,
        )

    # MISSING_COST only overrides for Analysis stage (need cost to make decision)
    if "MISSING_COST" in blocker_codes and stage == "Analysis":
        return DecisionNextAction(
            action="SUPPLEMENT_DATA",
            reason="Product cost data is missing. Enter cost to enable margin analysis.",
            blockers=blocker_codes,
        )

    # Stage-based actions
    if stage == "Opportunity":
        return DecisionNextAction(
            action="ANALYZE",
            reason="Product is in Opportunity stage. Run analysis to get AI recommendation.",
            blockers=blocker_codes,
        )

    if stage == "Candidate":
        return DecisionNextAction(
            action="ANALYZE",
            reason="Product is a Candidate. Run analysis to evaluate viability.",
            blockers=blocker_codes,
        )

    if stage == "Analysis":
        return DecisionNextAction(
            action="SUBMIT_APPROVAL",
            reason="Analysis complete. Submit for human approval.",
            blockers=blocker_codes,
        )

    if stage == "Pending Approval":
        return DecisionNextAction(
            action="APPROVE",
            reason="Product is pending approval. Complete the approval decision.",
            blockers=blocker_codes,
        )

    if stage == "Product Master":
        return DecisionNextAction(
            action="CREATE_LISTING",
            reason="Product is a Master. Create a B2C listing job.",
            blockers=blocker_codes,
        )

    if stage == "B2C Listing":
        return DecisionNextAction(
            action="VALIDATE_LISTING",
            reason="Listing job is active. Validate and approve.",
            blockers=blocker_codes,
        )

    if stage == "WooCommerce":
        return DecisionNextAction(
            action="NONE",
            reason="Product is published on WooCommerce. No immediate action required.",
            blockers=blocker_codes,
        )

    # Fallback
    return DecisionNextAction(
        action="NONE",
        reason="No immediate action required.",
        blockers=blocker_codes,
    )


def _extract_timeline(events: list[EventLog]) -> list[dict[str, Any]]:
    """Extract recent events for the timeline."""
    timeline = []
    for event in events[:20]:  # Limit to 20 most recent
        timeline.append(
            {
                "event_type": event.event_type,
                "timestamp": event.created_at.isoformat() if event.created_at else None,
                "payload": event.payload,
                "trace_id": event.trace_id,
            }
        )
    return timeline


async def get_product_decision_view(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    trace_id: str | None = None,
) -> ProductDecisionView | None:
    """Aggregate all decision-relevant data for a product into a ProductDecisionView.

    Returns None if the product does not exist or is not in the workspace.

    Performance: uses batch queries to minimize N+1 issues.
    """
    # 1. Load the product
    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
                Product.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if product is None:
        return None

    # 2. Load related data in parallel (batch queries)
    # Analysis run
    analysis = (
        await session.execute(
            select(ProductAnalysisRun)
            .where(
                ProductAnalysisRun.workspace_id == workspace_id,
                ProductAnalysisRun.product_id == product_id,
            )
            .order_by(ProductAnalysisRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Nuotao Score
    score = (
        await session.execute(
            select(ProductNuotaoScore)
            .where(
                ProductNuotaoScore.workspace_id == workspace_id,
                ProductNuotaoScore.product_id == product_id,
            )
            .order_by(ProductNuotaoScore.scored_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Cost
    cost = (
        await session.execute(
            select(ProductCost)
            .where(
                ProductCost.workspace_id == workspace_id,
                ProductCost.product_id == product_id,
            )
            .order_by(ProductCost.valid_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Supplier (via sourcing candidate or product source)
    supplier = None
    if product.source:
        supplier = (
            await session.execute(
                select(Supplier).where(
                    Supplier.workspace_id == workspace_id,
                    Supplier.code == product.source,
                )
            )
        ).scalar_one_or_none()

    # Sourcing candidate (for lead_time, moq)
    sourcing = (
        await session.execute(
            select(SourcingCandidate)
            .where(
                SourcingCandidate.workspace_id == workspace_id,
                SourcingCandidate.product_id == product_id,
                SourcingCandidate.status == "active",
            )
            .order_by(SourcingCandidate.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Rule execution logs (most recent per rule)
    rule_logs = (
        await session.execute(
            select(RuleExecutionLog)
            .where(
                RuleExecutionLog.workspace_id == workspace_id,
            )
            .order_by(RuleExecutionLog.created_at.desc())
            .limit(50)
        )
    ).scalars().all()

    # Filter to rules that have this product in context
    product_rule_logs = [
        log for log in rule_logs
        if log.context and str(product_id) in str(log.context.get("product_id", ""))
    ]
    if not product_rule_logs:
        # Also try rules where product_id is stored as string in context
        product_rule_logs = [
            log for log in rule_logs
            if log.context and product_id.hex in str(log.context)
        ]

    # Approval (most recent for this product)
    approval = (
        await session.execute(
            select(AgentApproval)
            .where(
                AgentApproval.workspace_id == workspace_id,
                AgentApproval.entity_type == "product",
                AgentApproval.entity_id == str(product_id),
            )
            .order_by(AgentApproval.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Listing job (most recent)
    listing = (
        await session.execute(
            select(ListingJob)
            .where(
                ListingJob.workspace_id == workspace_id,
                ListingJob.product_id == product_id,
            )
            .order_by(ListingJob.submitted_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # WooCommerce draft (most recent)
    wc_draft = (
        await session.execute(
            select(WooCommerceDraft)
            .where(
                WooCommerceDraft.workspace_id == workspace_id,
                WooCommerceDraft.product_id == product_id,
            )
            .order_by(WooCommerceDraft.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Event log (recent events for timeline)
    events = (
        await session.execute(
            select(EventLog)
            .where(
                EventLog.workspace_id == workspace_id,
                EventLog.entity_type == "product",
                EventLog.entity_id == str(product_id),
            )
            .order_by(EventLog.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    # 3. Compute derived values
    stage = _derive_stage(product, analysis, score, cost, listing, wc_draft)
    ai_reco, ai_reasons, ai_risks = _get_ai_recommendation(analysis)
    rule_results = _get_rule_results(product_rule_logs)
    rule_summary = _count_rule_results(rule_results)
    retail_price = _get_retail_price(product)
    margin = _calculate_margin(cost, retail_price)
    freight_share = _calculate_freight_share(cost)
    blockers = _identify_blockers(
        product, cost, supplier, sourcing, rule_results, approval, listing, wc_draft
    )
    next_action = _derive_next_action(
        product, stage, cost, rule_results, blockers, approval, listing
    )
    timeline = _extract_timeline(events)

    # 4. Build the view
    return ProductDecisionView(
        product=ProductOut.model_validate(product),
        stage=stage,
        status=product.status,

        # AI Recommendation
        ai_recommendation=ai_reco,
        ai_score=score.total if score else None,
        ai_grade=score.grade if score else None,
        ai_reasons=ai_reasons,
        ai_risks=ai_risks,
        ai_trace_id=(analysis.trace_id if analysis else score.trace_id if score else None),
        ai_analysis_version=analysis.prompt_version if analysis else None,
        ai_rule_version=score.rule_version if score else None,

        # Market Analysis (from analysis output)
        market_size=analysis.output.get("market_size") if analysis and isinstance(analysis.output, dict) else None,
        market_growth=analysis.output.get("market_growth") if analysis and isinstance(analysis.output, dict) else None,
        competition_level=analysis.output.get("competition_level") if analysis and isinstance(analysis.output, dict) else None,
        seasonality=analysis.output.get("seasonality") if analysis and isinstance(analysis.output, dict) else None,
        target_customer=analysis.output.get("target_customer") if analysis and isinstance(analysis.output, dict) else None,

        # Cost
        currency=cost.currency if cost else None,
        purchase_cost=cost.purchase_cost if cost else None,
        landed_cost=cost.total_landed_cost if cost else None,
        total_cost=cost.total_cost if cost else None,
        margin_percent=margin,
        return_rate=None,  # Always UNKNOWN until field exists
        freight_share=freight_share,

        # Supply Chain
        supplier_code=supplier.code if supplier else (product.source if product.source else None),
        supplier_name=supplier.name if supplier else None,
        supplier_rating=supplier.rating if supplier else None,
        supplier_status=supplier.status if supplier else None,
        lead_time_days=sourcing.lead_time_days if sourcing else None,
        moq=sourcing.moq if sourcing else None,
        qc_rate=None,  # Always UNKNOWN until field exists

        # Hard Rules
        hard_rules=rule_results,
        hard_rules_summary=rule_summary,

        # Approval
        approval_status=approval.status if approval else None,
        approval_type=approval.approval_type if approval else None,
        approval_actor=approval.actor if approval else None,
        approval_action=approval.action if approval else None,
        approval_note=approval.note if approval else None,
        approval_decided_at=approval.decided_at if approval else None,
        approval_trace_id=approval.trace_id if approval else None,

        # Product Master
        is_mastered=product.mastered_at is not None,
        mastered_at=product.mastered_at,
        mastered_by=product.mastered_by,
        mastered_trace_id=product.mastered_trace_id,

        # Listing / WooCommerce
        listing_status=listing.status if listing else None,
        listing_submitted_by=listing.submitted_by if listing else None,
        listing_reviewed_by=listing.reviewed_by if listing else None,
        listing_published_at=listing.published_at if listing else None,
        wc_product_id=listing.wc_product_id if listing else None,
        wc_draft_status=wc_draft.status if wc_draft else None,

        # Blockers
        blockers=blockers,

        # Next Action
        next_action=next_action,

        # Timeline
        timeline=timeline,

        # Traceability
        trace_id=trace_id,
    )


# --------------------------------------------------------------------------- #
# Phase 3C-3: Decision Write Model
# --------------------------------------------------------------------------- #

from datetime import UTC, datetime

from sqlalchemy import func

from app.schemas.product_intelligence import (
    ProductDecisionRequest,
    ProductDecisionResult,
)


class DecisionWriteError(Exception):
    """Raised when a decision cannot be applied."""

    def __init__(self, message: str, decision: str | None = None, previous_status: str | None = None,
                 current_status: str | None = None, idempotency_key: str | None = None,
                 trace_id: str | None = None):
        super().__init__(message)
        self.message = message
        self.decision = decision
        self.previous_status = previous_status
        self.current_status = current_status
        self.idempotency_key = idempotency_key
        self.trace_id = trace_id


# Candidate lifecycle transitions (mirrors _CANDIDATE_TRANSITIONS in product_intelligence.py)
_CANDIDATE_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"candidate"},
    "candidate": {"approved", "rejected"},
    "approved": {"testing", "rejected"},
    "testing": {"winner", "rejected"},
    "winner": set(),
    "rejected": set(),
}

# Mapping from Human Decision to target candidate_status
_DECISION_TO_STATUS: dict[str, str] = {
    "CONTINUE": "",  # Dynamic based on current status
    "REJECT": "rejected",
    "SUPPLEMENT_DATA": "",  # No state change
    "APPROVE": "",  # Dynamic based on current status
}


def _get_next_candidate_status(current: str | None) -> str | None:
    """Get the next legal candidate_status for CONTINUE/APPROVE."""
    if current is None:
        return "candidate"
    if current == "candidate":
        return "approved"
    if current == "approved":
        return "testing"
    if current == "testing":
        return "winner"
    return None  # Terminal state


def _check_hard_rules(results: list[DecisionRuleResult]) -> list[str]:
    """Check if any hard rules failed or are unknown."""
    failures = []
    for r in results:
        if r.result == "FAIL":
            failures.append(f"RULE_FAIL: {r.rule_id}")
        elif r.result == "UNKNOWN":
            failures.append(f"RULE_UNKNOWN: {r.rule_id}")
    return failures


async def _check_pricing_available(session: AsyncSession, product: Product) -> bool:
    """Check if pricing is available for candidate -> approved transition."""
    from app.services.listing_gate import resolve_prices
    from app.services.product_cost_service import latest_cost_for_product
    from decimal import Decimal

    meta = product.meta if isinstance(product.meta, dict) else {}
    prices = resolve_prices(meta)
    if not prices.get("regular_price"):
        return False

    cost = await latest_cost_for_product(
        session,
        workspace_id=product.workspace_id,
        product_id=product.id,
    )
    if cost is None:
        return False

    pc = getattr(cost, "purchase_cost", None)
    try:
        pc_val = Decimal(str(pc or 0))
    except (ValueError, TypeError):
        pc_val = Decimal("0")

    return pc is not None and pc_val > 0


async def _find_existing_decision_event(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    idempotency_key: str,
) -> EventLog | None:
    """Find an existing decision event by idempotency key."""
    events = (
        await session.execute(
            select(EventLog)
            .where(
                EventLog.workspace_id == workspace_id,
                EventLog.entity_type == "product",
                EventLog.entity_id == str(product_id),
                EventLog.event_type.in_(
                    [
                        "product.decision.continue",
                        "product.decision.reject",
                        "product.decision.supplement_data_requested",
                        "product.decision.approve",
                        "product.decision.failed",
                    ]
                ),
            )
            .order_by(EventLog.created_at.desc())
        )
    ).scalars().all()
    # Search for a matching idempotency key in the payload
    for event in events:
        payload = event.payload or {}
        if payload.get("idempotency_key") == idempotency_key:
            return event
    return None


async def apply_product_decision(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_id: UUID,
    request: ProductDecisionRequest,
    actor: str,
    trace_id: str | None = None,
) -> ProductDecisionResult:
    """Apply a human decision to a product.

    Reuses existing services:
    - update_candidate_status() for lifecycle changes
    - event_service.create_event() for audit

    Idempotency: same idempotency_key returns stable result.
    Permissions: checked by caller (API layer).
    """
    from app.services import event_service, product_intelligence as pi

    # Generate or validate idempotency key
    idempotency_key = request.idempotency_key or (
        f"decision-{product_id.hex[:8]}-{request.decision}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    )

    # Check for existing decision with same idempotency key
    existing_event = await _find_existing_decision_event(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        idempotency_key=idempotency_key,
    )

    if existing_event:
        # Return stable result (idempotent)
        payload = existing_event.payload or {}
        return ProductDecisionResult(
            success=payload.get("success", True),
            decision=request.decision,
            previous_status=payload.get("from_status"),
            current_status=payload.get("to_status"),
            stage=payload.get("stage", "UNKNOWN"),
            reason=payload.get("reason"),
            error=payload.get("error"),
            next_action=payload.get("next_action", "NONE"),
            blockers=[],
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            timestamp=existing_event.created_at,
            event_id=existing_event.id,
        )

    # Load product
    # Expire all objects to ensure we get the latest status from the database
    session.expire_all()
    product = (
        await session.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.id == product_id,
            )
        )
    ).scalar_one_or_none()
    if product:
        await session.refresh(product)

    if product is None:
        raise DecisionWriteError(
            "Product not found",
            decision=request.decision,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )

    previous_status = product.candidate_status
    previous_stage = _derive_stage(product, None, None, None, None, None)

    # Load decision view for blockers/rules check
    view = await get_product_decision_view(
        session,
        workspace_id=workspace_id,
        product_id=product_id,
        trace_id=trace_id,
    )
    rule_failures = _check_hard_rules(view.hard_rules if view else [])

    # Validate decision based on current state
    error_message = None
    success = True
    current_status = previous_status
    current_stage = previous_stage
    next_action = "NONE"
    event_type = None
    event_payload = {}

    # Check if product is in terminal state
    if previous_status in ("winner", "rejected"):
        if request.decision not in ("SUPPLEMENT_DATA",):
            error_message = (
                f"Product is in terminal state '{previous_status}'. "
                f"Only SUPPLEMENT_DATA is allowed."
            )
            success = False
            next_action = "NONE"
            event_type = "product.decision.failed"
    elif request.decision == "SUPPLEMENT_DATA":
        # SUPPLEMENT_DATA: no state change, just record the request
        if not request.supplement_fields:
            error_message = "SUPPLEMENT_DATA requires supplement_fields"
            success = False
            event_type = "product.decision.failed"
        else:
            event_type = "product.decision.supplement_data_requested"
            event_payload = {
                "decision": request.decision,
                "reason": request.reason,
                "supplement_fields": request.supplement_fields,
                "actor": actor,
                "idempotency_key": idempotency_key,
                "success": True,
                "from_status": previous_status,
                "to_status": previous_status,
                "stage": previous_stage,
                "next_action": "SUPPLEMENT_DATA",
            }
            next_action = "SUPPLEMENT_DATA"
            success = True
    elif request.decision in ("CONTINUE", "APPROVE"):
        # Check hard rules before advancing
        rule_fail_blockers = [f for f in rule_failures if "RULE_FAIL" in f]
        if rule_fail_blockers and request.decision == "APPROVE":
            error_message = (
                f"Cannot APPROVE with failed hard rules: {', '.join(rule_fail_blockers)}. "
                f"Rule UNKNOWN cannot auto-PASS."
            )
            success = False
            next_action = "SUPPLEMENT_DATA"
            event_type = "product.decision.failed"
        else:
            # Determine target status
            target_status = _get_next_candidate_status(previous_status)
            if target_status is None:
                error_message = f"Cannot advance from terminal state '{previous_status}'"
                success = False
                next_action = "NONE"
                event_type = "product.decision.failed"
            else:
                # Check pricing for candidate -> approved
                if previous_status == "candidate" and target_status == "approved":
                    if not await _check_pricing_available(session, product):
                        error_message = (
                            "Cannot advance from candidate to approved: "
                            "pricing (retail price + purchase cost) is required."
                        )
                        success = False
                        next_action = "SUPPLEMENT_DATA"
                        event_type = "product.decision.failed"
                    else:
                        # Call existing service to update candidate status
                        try:
                            await pi.update_candidate_status(
                                session,
                                workspace_id=workspace_id,
                                product_id=product_id,
                                new_status=target_status,
                                actor=actor,
                                trace_id=trace_id,
                            )
                            current_status = target_status
                        except pi.ProductIntelligenceError as exc:
                            error_message = str(exc)
                            success = False
                            next_action = "SUPPLEMENT_DATA" if "pricing" in str(exc).lower() else "NONE"
                            event_type = "product.decision.failed"
                else:
                    # Call existing service to update candidate status for other transitions
                    try:
                        await pi.update_candidate_status(
                            session,
                            workspace_id=workspace_id,
                            product_id=product_id,
                            new_status=target_status,
                            actor=actor,
                            trace_id=trace_id,
                        )
                        current_status = target_status
                    except pi.ProductIntelligenceError as exc:
                        error_message = str(exc)
                        success = False
                        next_action = "NONE"
                        event_type = "product.decision.failed"
                # Continue with event creation after status update
                if success and current_status != previous_status:
                    # Re-derive stage after status change
                    product = (
                        await session.execute(
                            select(Product).where(
                                Product.workspace_id == workspace_id,
                                Product.id == product_id,
                            )
                        )
                    ).scalar_one()
                    current_stage = _derive_stage(
                        product, None, None, None, None, None
                    )
                    event_type = (
                        "product.decision.approve" if request.decision == "APPROVE"
                        else "product.decision.continue"
                    )
                    event_payload = {
                        "decision": request.decision,
                        "reason": request.reason,
                        "actor": actor,
                        "idempotency_key": idempotency_key,
                        "success": True,
                        "from_status": previous_status,
                        "to_status": current_status,
                        "stage": current_stage,
                        "next_action": "CREATE_LISTING" if current_status == "approved" else "NONE",
                    }
                    next_action = "CREATE_LISTING" if current_status == "approved" else "NONE"
    elif request.decision == "REJECT":
        # Check hard rules - reject is always allowed (terminal state)
        if previous_status in ("winner", "rejected"):
            error_message = f"Product is already in terminal state '{previous_status}'"
            success = False
            next_action = "NONE"
            event_type = "product.decision.failed"
        else:
            # Call existing service to update candidate status
            try:
                await pi.update_candidate_status(
                    session,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    new_status="rejected",
                    actor=actor,
                    trace_id=trace_id,
                )
                current_status = "rejected"
                current_stage = "Rejected"
                event_type = "product.decision.reject"
                event_payload = {
                    "decision": request.decision,
                    "reason": request.reason,
                    "actor": actor,
                    "idempotency_key": idempotency_key,
                    "success": True,
                    "from_status": previous_status,
                    "to_status": current_status,
                    "stage": current_stage,
                    "next_action": "NONE",
                }
                next_action = "NONE"
            except pi.ProductIntelligenceError as exc:
                error_message = str(exc)
                success = False
                next_action = "NONE"
                event_type = "product.decision.failed"
    else:
        error_message = f"Unknown decision type: {request.decision}"
        success = False
        next_action = "NONE"
        event_type = "product.decision.failed"

    # Create event for audit
    event_id = None
    if event_type:
        event_payload.update({
            "trace_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        event = await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type=event_type,
            entity_type="product",
            entity_id=str(product_id),
            payload=event_payload,
            trace_id=trace_id,
            commit=False,  # Let caller commit
        )
        event_id = event.id
        await session.flush()

    # Return result
    return ProductDecisionResult(
        success=success,
        decision=request.decision,
        previous_status=previous_status,
        current_status=current_status,
        stage=current_stage,
        reason=request.reason,
        error=error_message,
        next_action=next_action,
        blockers=view.blockers if view and not success else [],
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        timestamp=datetime.now(UTC),
        event_id=event_id,
    )
