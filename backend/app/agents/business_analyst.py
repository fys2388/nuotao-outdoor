"""Business Analyst Agent v1.

AI business intelligence and analytics capability for Nuotao AI OS.
Strictly **analyse + report + suggest** - never makes business decisions.

Permissions
-----------
- READ:  all business data (sales, costs, marketing, operations, finance) via services
- WRITE: business_analysis_runs (audit) and business_insights
  (reports with approval_status=pending only)
- FORBIDDEN: approve budgets, change targets, modify financial data, mutate any
  business/financial/operational row.

Flow
----
Business Context -> Prompt (registry) -> LLM Gateway -> Structured Output
-> Validation (schema + business gates + data accuracy) -> audit rows.
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

AGENT_ID = "business_analyst"
AGENT_NAME = "Business Analyst"
PROMPT_NAME = "AGENT_BUSINESS_ANALYST"
PROMPT_VERSION = "v1"
TRIGGER = "api:business:analyze"

PROMPT_TEMPLATE = (
    "You are the Business Analyst for Nuotao Outdoor, an outdoor gear DTC brand "
    "operating in European and American markets. Analyze the provided business context "
    "and respond with ONLY a JSON object matching the output schema.\n\n"
    "Context: {context_json}\n\n"
    "Output schema: {output_schema}\n\n"
    "Focus on: financial performance analysis, sales trends, profitability analysis, "
    "KPI tracking, market opportunity identification, competitive benchmarking, "
    "risk assessment, and data-driven business recommendations. "
    "All analysis must be based on the provided data, clearly state assumptions, "
    "and include confidence scores. Never fabricate data or make definitive predictions."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string", "description": "Executive summary of business analysis"},
        "financial_performance": {
            "type": "object",
            "properties": {
                "revenue": {"type": "number", "description": "Total revenue in USD"},
                "revenue_growth_pct": {"type": "number", "description": "Revenue growth percentage"},
                "gross_margin_pct": {"type": "number", "description": "Gross margin percentage"},
                "net_profit": {"type": "number", "description": "Net profit in USD"},
                "net_margin_pct": {"type": "number", "description": "Net margin percentage"},
                "cash_flow_status": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "key_drivers": {"type": "array", "items": {"type": "string"}},
            },
        },
        "sales_analysis": {
            "type": "object",
            "properties": {
                "total_orders": {"type": "number"},
                "average_order_value": {"type": "number"},
                "conversion_rate_pct": {"type": "number"},
                "top_products": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "units_sold": {"type": "number"},
                            "revenue": {"type": "number"},
                            "growth_pct": {"type": "number"},
                        },
                    },
                },
                "sales_by_region": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "region": {"type": "string"},
                            "revenue": {"type": "number"},
                            "share_pct": {"type": "number"},
                            "growth_pct": {"type": "number"},
                        },
                    },
                },
                "trends": {"type": "array", "items": {"type": "string"}},
            },
        },
        "kpi_dashboard": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kpi": {"type": "string"},
                    "current_value": {"type": "string"},
                    "target": {"type": "string"},
                    "status": {"type": "string", "enum": ["on_track", "at_risk", "off_track"]},
                    "variance": {"type": "string"},
                },
            },
        },
        "market_opportunities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "opportunity": {"type": "string"},
                    "estimated_value": {"type": "string"},
                    "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                    "timeframe": {"type": "string"},
                    "required_investment": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "risk_assessment": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "category": {"type": "string", "enum": ["financial", "operational", "market", "compliance", "supply_chain"]},
                    "likelihood": {"type": "string", "enum": ["low", "medium", "high"]},
                    "impact": {"type": "string", "enum": ["low", "medium", "high"]},
                    "mitigation": {"type": "string"},
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "recommendation": {"type": "string"},
                    "expected_outcome": {"type": "string"},
                    "implementation_complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "estimated_timeline": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "data_quality_notes": {"type": "array", "items": {"type": "string"}},
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["executive_summary", "recommendations", "confidence_score"],
}


@dataclass
class BusinessAnalysisResult:
    """Outcome of one business analyst run."""

    agent_run: AiAgentRun | None
    output: dict[str, Any] | None
    error: str | None = None
    dry_run: bool = False


async def analyze_business(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    context: dict[str, Any],
    trace_id: str | None = None,
    persist: bool = True,
) -> BusinessAnalysisResult:
    """Run business analyst analysis.

    Args:
        workspace_id: workspace identifier
        context: business context data (sales, costs, marketing, operations)
        trace_id: optional trace identifier
        persist: when False, skip audit persistence (dry-run)

    Returns:
        BusinessAnalysisResult with structured output or error.
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
            "You are a senior business analyst for an outdoor gear DTC brand. "
            "Analyze the data objectively, state assumptions clearly, "
            "and provide data-driven recommendations. Never fabricate data. "
            "Respond ONLY with a valid JSON object matching the schema."
        ),
        temperature=0.2,
        task_type="business_analysis",
        trace_id=trace_id,
        persist=persist,
    )

    return BusinessAnalysisResult(
        agent_run=result.agent_run,
        output=result.output,
        error=result.error,
        dry_run=not persist,
    )


async def generate_business_report(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    report_type: str,
    period: str,
    business_data: dict[str, Any],
    trace_id: str | None = None,
) -> BusinessAnalysisResult:
    """Generate a structured business report.

    Args:
        workspace_id: workspace identifier
        report_type: type of report (weekly, monthly, quarterly, annual)
        period: reporting period (e.g., '2026-W35', '2026-08')
        business_data: comprehensive business data for the period
        trace_id: optional trace identifier

    Returns:
        BusinessAnalysisResult with generated report.
    """
    context = {
        "analysis_type": "business_report",
        "report_type": report_type,
        "period": period,
        "business_data": business_data,
    }
    return await analyze_business(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )


async def analyze_profitability(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    product_data: dict[str, Any],
    cost_data: dict[str, Any],
    trace_id: str | None = None,
) -> BusinessAnalysisResult:
    """Analyze product and overall profitability.

    Args:
        workspace_id: workspace identifier
        product_data: product sales and pricing data
        cost_data: cost structure (COGS, marketing, operations, overhead)
        trace_id: optional trace identifier

    Returns:
        BusinessAnalysisResult with profitability analysis.
    """
    context = {
        "analysis_type": "profitability_analysis",
        "product_data": product_data,
        "cost_data": cost_data,
    }
    return await analyze_business(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )
