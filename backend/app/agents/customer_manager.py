"""Customer Manager Agent v1.

AI customer service and experience analysis capability for Nuotao AI OS.
Strictly **analyse + suggest + draft responses** - never sends customer
communications without human approval.

Permissions
-----------
- READ:  customer data, order history, support tickets, feedback (via services)
- WRITE: customer_analysis_runs (audit) and response_drafts
  (proposals with approval_status=pending only)
- FORBIDDEN: send emails, issue refunds, change customer data, mutate any
  customer/order/support row.

Flow
----
Customer Context -> Prompt (registry) -> LLM Gateway -> Structured Output
-> Validation (schema + business gates + compliance) -> audit rows.
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

AGENT_ID = "customer_manager"
AGENT_NAME = "Customer Manager"
PROMPT_NAME = "AGENT_CUSTOMER_MANAGER"
PROMPT_VERSION = "v1"
TRIGGER = "api:customer:analyze"

PROMPT_TEMPLATE = (
    "You are the Customer Manager for Nuotao Outdoor, an outdoor gear DTC brand "
    "serving European and American customers. Analyze the provided customer context "
    "and respond with ONLY a JSON object matching the output schema.\n\n"
    "Context: {context_json}\n\n"
    "Output schema: {output_schema}\n\n"
    "Focus on: customer satisfaction analysis, support ticket resolution, "
    "response drafting, churn risk identification, customer feedback analysis, "
    "and actionable customer experience recommendations. "
    "All responses must be professional, empathetic, and brand-appropriate. "
    "Never promise refunds, discounts, or policy exceptions without approval."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "Brief summary of customer analysis"},
        "customer_sentiment": {
            "type": "object",
            "properties": {
                "overall_sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "satisfaction_score": {"type": "number", "minimum": 0, "maximum": 10},
                "churn_risk": {"type": "string", "enum": ["low", "medium", "high"]},
                "key_concerns": {"type": "array", "items": {"type": "string"}},
            },
        },
        "support_analysis": {
            "type": "object",
            "properties": {
                "open_tickets": {"type": "number"},
                "average_resolution_time_hours": {"type": "number"},
                "first_response_time_minutes": {"type": "number"},
                "common_issues": {"type": "array", "items": {"type": "string"}},
                "improvement_suggestions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "response_drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "issue_summary": {"type": "string"},
                    "draft_response": {"type": "string"},
                    "tone": {"type": "string", "enum": ["apologetic", "informative", "empathetic", "firm"]},
                    "requires_approval": {"type": "boolean"},
                    "approval_reason": {"type": "string"},
                },
            },
        },
        "feedback_analysis": {
            "type": "object",
            "properties": {
                "recent_reviews": {"type": "number"},
                "average_rating": {"type": "number", "minimum": 0, "maximum": 5},
                "positive_themes": {"type": "array", "items": {"type": "string"}},
                "negative_themes": {"type": "array", "items": {"type": "string"}},
                "actionable_insights": {"type": "array", "items": {"type": "string"}},
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
                    "owner": {"type": "string"},
                },
            },
        },
        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["summary", "action_items", "confidence_score"],
}


@dataclass
class CustomerAnalysisResult:
    """Outcome of one customer manager run."""

    agent_run: AiAgentRun | None
    output: dict[str, Any] | None
    error: str | None = None
    dry_run: bool = False


async def analyze_customer(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    context: dict[str, Any],
    trace_id: str | None = None,
    persist: bool = True,
) -> CustomerAnalysisResult:
    """Run customer manager analysis.

    Args:
        workspace_id: workspace identifier
        context: customer context data (customer info, orders, tickets, feedback)
        trace_id: optional trace identifier
        persist: when False, skip audit persistence (dry-run)

    Returns:
        CustomerAnalysisResult with structured output or error.
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
            "You are a senior customer experience manager for an outdoor gear DTC brand. "
            "Analyze the context and provide professional, empathetic recommendations. "
            "Draft responses that are brand-appropriate and never promise exceptions. "
            "Respond ONLY with a valid JSON object matching the schema."
        ),
        temperature=0.4,
        task_type="customer_analysis",
        trace_id=trace_id,
        persist=persist,
    )

    return CustomerAnalysisResult(
        agent_run=result.agent_run,
        output=result.output,
        error=result.error,
        dry_run=not persist,
    )


async def draft_customer_response(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    ticket_id: str,
    customer_data: dict[str, Any],
    ticket_data: dict[str, Any],
    trace_id: str | None = None,
) -> CustomerAnalysisResult:
    """Draft a customer service response for a specific ticket.

    Args:
        workspace_id: workspace identifier
        ticket_id: support ticket identifier
        customer_data: customer profile and history
        ticket_data: ticket details and conversation history
        trace_id: optional trace identifier

    Returns:
        CustomerAnalysisResult with drafted response.
    """
    context = {
        "analysis_type": "response_drafting",
        "ticket_id": ticket_id,
        "customer_data": customer_data,
        "ticket_data": ticket_data,
    }
    return await analyze_customer(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )


async def analyze_customer_feedback(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    feedback_data: dict[str, Any],
    trace_id: str | None = None,
) -> CustomerAnalysisResult:
    """Analyze customer feedback and reviews.

    Args:
        workspace_id: workspace identifier
        feedback_data: reviews, ratings, survey responses
        trace_id: optional trace identifier

    Returns:
        CustomerAnalysisResult with feedback analysis.
    """
    context = {
        "analysis_type": "feedback_analysis",
        "feedback_data": feedback_data,
    }
    return await analyze_customer(
        session,
        workspace_id=workspace_id,
        context=context,
        trace_id=trace_id,
    )
