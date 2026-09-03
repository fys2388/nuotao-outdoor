"""Marketing Manager Agent v1.

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
-> Validation (schema + business gates) -> audit rows.
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
PROMPT_VERSION = "v1"
TRIGGER = "api:marketing:analyze"

PROMPT_TEMPLATE = (
    "You are the Marketing Manager for Nuotao Outdoor, an outdoor gear DTC brand "
    "targeting European and American customers. Analyze the provided marketing context "
    "and respond with ONLY a JSON object matching the output schema.\n\n"
    "Context: {context_json}\n\n"
    "Output schema: {output_schema}\n\n"
    "Focus on: campaign ROI analysis, customer segmentation, pricing strategy, "
    "competitive positioning, and actionable marketing recommendations. "
    "All recommendations must be data-driven and include confidence scores."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Brief summary of marketing analysis"},
        "campaign_analysis": {
            "type": "object",
            "properties": {
                "roi": {"type": "number", "description": "Return on investment percentage"},
                "cac": {"type": "number", "description": "Customer acquisition cost"},
                "conversion_rate": {"type": "number", "description": "Conversion rate percentage"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
            },
        },
        "customer_segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "size": {"type": "string"},
                    "value": {"type": "string"},
                    "strategy": {"type": "string"},
                },
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
                    "expected_impact": {"type": "string"},
                    "timeline": {"type": "string"},
                },
            },
        },
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["summary", "action_items", "confidence_score"],
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
            "Respond ONLY with a valid JSON object matching the schema."
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
