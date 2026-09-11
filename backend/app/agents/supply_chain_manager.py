"""Supply Chain Manager Agent v1.

AI supply chain analysis capability for Nuotao AI OS. Strictly
**analyse + suggest + audit** - never executes supply chain actions.

Permissions
-----------
- READ:  supplier data, inventory levels, cost data, logistics metrics (via services)
- WRITE: supply_chain_analysis_runs (audit) and supply_chain_suggestions
  (proposals with approval_status=pending only)
- FORBIDDEN: place orders, change suppliers, adjust inventory, mutate any
  supplier/product/inventory/logistics row.

Flow
----
Supply Chain Context -> Prompt (registry) -> LLM Gateway -> Structured Output
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

AGENT_ID = "supply_chain_manager"
AGENT_NAME = "Supply Chain Manager"
PROMPT_NAME = "AGENT_SUPPLY_CHAIN_MANAGER"
PROMPT_VERSION = "v1"
TRIGGER = "api:supply_chain:analyze"

PROMPT_TEMPLATE = (
    "You are the Supply Chain Manager for Nuotao Outdoor, an outdoor gear DTC brand "
    "sourcing from China and shipping to Europe and America. Analyze the provided "
    "supply chain context and respond with ONLY a JSON object matching the output schema.\n\n"
    "Context: {context_json}\n\n"
    "Output schema: {output_schema}\n\n"
    "Focus on: supplier performance, inventory optimization, cost reduction, "
    "logistics efficiency, risk assessment, and actionable supply chain recommendations. "
    "All recommendations must be data-driven and include confidence scores."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Brief summary of supply chain analysis"},
        "supplier_analysis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "supplier": {"type": "string"},
                    "performance_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "lead_time_days": {"type": "number"},
                    "quality_rating": {"type": "string"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "recommendation": {"type": "string"},
                },
            },
        },
        "inventory_analysis": {
            "type": "object",
            "properties": {
                "stockout_risk_items": {"type": "array", "items": {"type": "string"}},
                "overstock_items": {"type": "array", "items": {"type": "string"}},
                "reorder_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "current_stock": {"type": "number"},
                            "suggested_reorder_point": {"type": "number"},
                            "rationale": {"type": "string"},
                        },
                    },
                },
            },
        },
        "cost_optimization": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area": {"type": "string"},
                    "current_cost": {"type": "number"},
                    "potential_savings": {"type": "number"},
                    "suggestion": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "risk_assessment": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string"},
                    "likelihood": {"type": "string", "enum": ["low", "medium", "high"]},
                    "impact": {"type": "string", "enum": ["low", "medium", "high"]},
                    "mitigation": {"type": "string"},
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
class SupplyChainAnalysisResult:
    """Outcome of one supply chain manager run."""

    agent_run: AiAgentRun | None
    output: dict[str, Any] | None
    error: str | None = None
    dry_run: bool = False


async def analyze_supply_chain(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    context: dict[str, Any],
    trace_id: str | None = None,
    persist: bool = True,
) -> SupplyChainAnalysisResult:
    """Run supply chain manager analysis.

    Args:
        workspace_id: workspace identifier
        context: supply chain context data (suppliers, inventory, costs, logistics)
        trace_id: optional trace identifier
        persist: when False, skip audit persistence (dry-run)

    Returns:
        SupplyChainAnalysisResult with structured output or error.
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
            "You are a senior supply chain manager for an outdoor gear DTC brand. "
            "Analyze the context and provide data-driven recommendations. "
            "Respond ONLY with a valid JSON object matching the schema."
        ),
        temperature=0.3,
        task_type="supply_chain_analysis",
        trace_id=trace_id,
        persist=persist,
    )

    return SupplyChainAnalysisResult(
        agent_run=result.agent_run,
        output=result.output,
        error=result.error,
        dry_run=not persist,
    )


async def analyze_supplier_performance(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    supplier_id: str,
    supplier_data: dict[str, Any],
    trace_id: str | None = None,
) -> SupplyChainAnalysisResult:
    """Analyze a specific supplier's performance.

    Args:
        workspace_id: workspace identifier
        supplier_id: supplier identifier
        supplier_data: supplier metrics, quality, delivery data
        trace_id: optional trace identifier

    Returns:
        SupplyChainAnalysisResult with supplier analysis.
    """
    context = {
        "analysis_type": "supplier_performance",
        "supplier_id": supplier_id,
        "supplier_data": supplier_data,
    }
    return await analyze_supply_chain(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )


async def analyze_inventory_optimization(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    inventory_data: dict[str, Any],
    trace_id: str | None = None,
) -> SupplyChainAnalysisResult:
    """Analyze inventory levels and suggest optimization.

    Args:
        workspace_id: workspace identifier
        inventory_data: current inventory, sales velocity, lead times
        trace_id: optional trace identifier

    Returns:
        SupplyChainAnalysisResult with inventory optimization analysis.
    """
    context = {
        "analysis_type": "inventory_optimization",
        "inventory_data": inventory_data,
    }
    return await analyze_supply_chain(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )
