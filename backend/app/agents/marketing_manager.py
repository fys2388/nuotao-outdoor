"""Marketing Manager Agent v2.

AI marketing analysis capability for Nuotao AI OS. Strictly
**analyse + suggest + audit** - never executes marketing actions.

Permissions
-----------
- READ:  marketing data, campaign metrics, customer segments (via services)
- WRITE: marketing_analysis_runs (audit) and marketing_suggestions
  (proposals with approval_status=pending only)
- FORBIDDEN: launch campaigns, change prices, send emails, mutate any
  marketing/customer/order row.

Flow
----
Marketing Context -> Prompt (registry) -> LLM Gateway -> Structured Output
-> Validation (schema + business gates + truthfulness gates) -> audit rows.

v2 changes
----------
- Truthfulness rules v1.0: every number must carry a source (R1);
  campaign revenue must reconcile with customer-segment revenue and gaps
  must be disclosed (R2); predictions require a model/formula (R3);
  small samples forbid statistical conclusions (R4); planned campaigns
  are N/A not 0.00 and get no pause/delete instructions (R5); truncated
  output is rejected (R6); all runs are audited (R7).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.generic_agent import GenericAgentResult, run_generic_agent
from app.models.agent import AiAgentRun

logger = logging.getLogger(__name__)

AGENT_ID = "marketing_manager"
AGENT_NAME = "Marketing Manager"
PROMPT_NAME = "AGENT_MARKETING_MANAGER"
PROMPT_VERSION = "v2"
TRIGGER = "api:marketing:analyze"

TRUTHFULNESS_RULES = """\
## Truthfulness Rules (MANDATORY, report-truthfulness v1.0)
1. EVERY number in your output must trace to a source present in the Context
   (ad platform / CRM / GA4 / payment). Never invent spend, revenue, ROAS,
   conversion, AOV or growth figures. If a source is missing, write "unknown"
   instead of guessing.
2. RECONCILE before reporting totals: campaign-level revenue MUST equal the
   sum of customer-segment revenue (same currency, same period). If a gap
   exists, report the gap amount and percentage explicitly; never hide it,
   never silently omit it.
3. PREDICTIONS REQUIRE A MODEL. Any "expected impact" containing concrete
   numbers (dollars, %, x-times) MUST carry both `basis` (evidence/assumption)
   and `formula` (calculation). Without a model, write scenario wording only:
   "if X then Y, assuming Z" - never present invented forecasts as facts.
4. SMALL SAMPLES FORBID CONCLUSIONS. With fewer than 30 customers in a
   segment, only describe ("1 customer, $449.90"); never state ratios
   ("5.6x value") or qualitative claims ("extremely high AOV") as findings.
5. PLANNED CAMPAIGNS ARE N/A. Campaigns with status planned/paused and zero
   spend get ROAS N/A (never 0.00) and MUST NOT receive pause/delete
   instructions.
6. OUTPUT MUST BE COMPLETE. Return the full JSON object. If you cannot
   finish, return {"error": "..."} instead of truncating.
7. All analysis output is audited (ai_agent_runs); fabricating data is a
   blocking failure.
"""

PROMPT_TEMPLATE = (
    "You are the Marketing Manager for Nuotao Outdoor, an outdoor gear DTC brand "
    "targeting European and American customers. Analyze the provided marketing context "
    "and respond with ONLY a JSON object matching the output schema.\n\n"
    + TRUTHFULNESS_RULES
    + "\n\nContext: {context_json}\n\n"
    "Output schema: {output_schema}\n\n"
    "Focus on: campaign ROI analysis, customer segmentation, pricing strategy, "
    "competitive positioning, and actionable marketing recommendations. "
    "All recommendations must be data-driven and include confidence scores."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Brief summary of marketing analysis"},
        "data_sources": {
            "type": "object",
            "description": "R1: source of every number in this report "
                    "(ad platform/CRM/GA4/payment)",
            "properties": {
                "campaign_spend": {"type": "string"},
                "campaign_revenue": {"type": "string"},
                "customer_segments": {"type": "string"},
                "orders": {"type": "string"},
            },
            "required": ["campaign_spend", "campaign_revenue", "customer_segments"],
        },
        "reconciliation": {
            "type": "object",
            "description": "R2: campaign revenue vs customer-segment revenue reconciliation",
            "properties": {
                "campaign_total_revenue": {"type": "number"},
                "segment_total_revenue": {"type": "number"},
                "gap": {"type": "number"},
                "gap_percentage": {"type": "number"},
                "reconciled": {"type": "boolean"},
                "note": {"type": "string"},
            },
            "required": ["campaign_total_revenue", "segment_total_revenue", "reconciled"],
        },
        "campaign_analysis": {
            "type": "object",
            "properties": {
                "roi": {"type": "number", "description": "Return on investment ratio"
                    " (or null if N/A)"},
                "roi_status": {"type": "string", "enum": ["computed", "n/a", "unknown"]},
                "cac": {"type": ["number", "null"], "description": "Customer acquisition cost"},
                "conversion_rate": {"type": ["number", "null"],
                    "description": "Conversion rate percentage"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
            },
        },
        "customer_segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "size": {"type": "string", "description": "sample size, e.g. '1 customer'"},
                    "customer_count": {"type": "number"},
                    "value": {"type": "string"},
                    "strategy": {"type": "string"},
                },
                "required": ["name", "customer_count"],
            },
        },
        "pricing_suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product": {"type": "string"},
                    "current_price": {"type": "number"},
                    "suggested_price": {"type": "number"},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "action": {"type": "string"},
                    "expected_impact": {"type": "string", "description": "impact wording"},
                    "basis": {"type": "string",
                    "description": "R3: evidence/assumption behind the impact"},
                    "formula": {"type": "string",
                    "description": "R3: calculation model for the impact"},
                    "timeline": {"type": "string"},
                },
                "required": ["priority", "action"],
            },
        },
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "summary",
        "data_sources",
        "reconciliation",
        "action_items",
        "confidence_score",
    ],
}


@dataclass
class MarketingAnalysisResult:
    """Outcome of one marketing manager run."""

    agent_run: AiAgentRun | None
    output: dict[str, Any] | None
    error: str | None = None
    dry_run: bool = False


async def analyze_marketing(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    context: dict[str, Any],
    trace_id: str | None = None,
    persist: bool = True,
) -> MarketingAnalysisResult:
    """Run marketing manager analysis.

    Args:
        workspace_id: workspace identifier
        context: marketing context data (campaigns, customers, products, metrics)
        trace_id: optional trace identifier
        persist: when False, skip audit persistence (dry-run)

    Returns:
        MarketingAnalysisResult with structured output or error.
    """
    result: GenericAgentResult = await run_generic_agent(
        session,
        workspace_id=workspace_id,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger=TRIGGER,
        context=context,
        prompt_name=PROMPT_NAME,
        output_schema=OUTPUT_SCHEMA,
        system_instruction=(
            "You are a senior marketing manager for an outdoor gear DTC brand. "
            "Analyze the context and provide data-driven recommendations. "
            "Respond ONLY with a valid JSON object matching the schema. "
            "Obey the Truthfulness Rules: no invented numbers, reconcile revenue, "
            "model every prediction, respect small samples, mark planned campaigns N/A."
        ),
        temperature=0.3,
        task_type="marketing_analysis",
        trace_id=trace_id,
        persist=persist,
    )

    return MarketingAnalysisResult(
        agent_run=result.agent_run,
        output=result.output,
        error=result.error,
        dry_run=not persist,
    )


async def analyze_campaign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    campaign_id: str,
    campaign_data: dict[str, Any],
    trace_id: str | None = None,
) -> MarketingAnalysisResult:
    """Analyze a specific marketing campaign.

    Args:
        workspace_id: workspace identifier
        campaign_id: campaign identifier
        campaign_data: campaign metrics and data
        trace_id: optional trace identifier

    Returns:
        MarketingAnalysisResult with campaign analysis.
    """
    context = {
        "analysis_type": "campaign_analysis",
        "campaign_id": campaign_id,
        "campaign_data": campaign_data,
    }
    return await analyze_marketing(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )


async def analyze_customer_segments(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_data: dict[str, Any],
    trace_id: str | None = None,
) -> MarketingAnalysisResult:
    """Analyze customer segments and suggest targeting strategies.

    Args:
        workspace_id: workspace identifier
        customer_data: customer demographics, behavior, and purchase data
        trace_id: optional trace identifier

    Returns:
        MarketingAnalysisResult with customer segment analysis.
    """
    context = {
        "analysis_type": "customer_segmentation",
        "customer_data": customer_data,
    }
    return await analyze_marketing(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )
