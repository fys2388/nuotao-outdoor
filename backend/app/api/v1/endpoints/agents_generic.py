"""Generic AI Agent endpoints for marketing, supply chain, customer service, and business analyst.

Each agent accepts a domain-specific context (JSON) and returns AI-generated analysis.
Uses the generic_agent framework with domain-specific prompts from the registry.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.generic_agent import run_generic_agent
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id

router = APIRouter(prefix="/agents", tags=["agents-generic"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


class GenericAgentRequest(BaseModel):
    """Request body for generic agent analysis."""

    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Domain-specific context data for the AI agent",
    )
    dry_run: bool = Field(
        default=False,
        description="When true, skip audit persistence (validate pipeline only)",
    )
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)


class GenericAgentResponse(BaseModel):
    """Response from generic agent analysis."""

    agent_run_id: int | None = None
    status: str
    output: dict[str, Any] | None = None
    error: str | None = None
    dry_run: bool = False


# Agent configuration: (agent_id, agent_name, prompt_name, task_type, trigger)
AGENT_CONFIGS = {
    "marketing-manager": {
        "agent_id": "marketing_manager",
        "agent_name": "Marketing Manager",
        "prompt_name": "AGENT_MARKETING_MANAGER",
        "task_type": "marketing_agent",
        "trigger": "api:marketing-manager:analyze",
        "system_instruction": (
            "You are the Nuotao Outdoor Marketing Manager. Analyze the provided marketing "
            "context and respond with ONLY a JSON object containing campaign suggestions, "
            "content ideas, channel recommendations, and expected ROI estimates."
        ),
    },
    "supply-chain-manager": {
        "agent_id": "supply_chain_manager",
        "agent_name": "Supply Chain Manager",
        "prompt_name": "AGENT_SUPPLY_CHAIN_MANAGER",
        "task_type": "supply_chain_agent",
        "trigger": "api:supply-chain-manager:analyze",
        "system_instruction": (
            "You are the Nuotao Outdoor Supply Chain Manager. Analyze the provided supply "
            "chain context and respond with ONLY a JSON object containing supplier recommendations, "
            "cost optimization suggestions, inventory planning, and logistics advice."
        ),
    },
    "customer-service-manager": {
        "agent_id": "customer_service_manager",
        "agent_name": "Customer Service Manager",
        "prompt_name": "AGENT_CUSTOMER_SERVICE_MANAGER",
        "task_type": "customer_service_agent",
        "trigger": "api:customer-service-manager:analyze",
        "system_instruction": (
            "You are the Nuotao Outdoor Customer Service Manager. Analyze the provided customer "
            "service context and respond with ONLY a JSON object containing response suggestions, "
            "satisfaction improvement ideas, escalation recommendations, and trend analysis."
        ),
    },
    "business-analyst": {
        "agent_id": "business_analyst",
        "agent_name": "Business Analyst",
        "prompt_name": "AGENT_BUSINESS_ANALYST",
        "task_type": "business_analyst_agent",
        "trigger": "api:business-analyst:analyze",
        "system_instruction": (
            "You are the Nuotao Outdoor Business Analyst. Analyze the provided business "
            "context and respond with ONLY a JSON object containing financial analysis, KPI "
            "assessments, trend predictions, risk factors, and actionable recommendations."
        ),
    },
}


async def _run_agent(
    agent_key: str,
    body: GenericAgentRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> GenericAgentResponse:
    """Shared handler for all generic agent endpoints."""
    config = AGENT_CONFIGS[agent_key]

    result = await run_generic_agent(
        db,
        workspace_id=workspace_id,
        agent_id=config["agent_id"],
        agent_name=config["agent_name"],
        trigger=config["trigger"],
        context=body.context,
        prompt_name=config["prompt_name"],
        system_instruction=config["system_instruction"],
        temperature=body.temperature,
        task_type=config["task_type"],
        trace_id=get_trace_id(),
        persist=not body.dry_run,
    )

    if result.error and not result.output:
        return GenericAgentResponse(
            agent_run_id=result.agent_run.id if result.agent_run else None,
            status="failed",
            error=result.error,
            dry_run=result.dry_run,
        )

    return GenericAgentResponse(
        agent_run_id=result.agent_run.id if result.agent_run else None,
        status="completed",
        output=result.output,
        error=result.error,
        dry_run=result.dry_run,
    )


@router.post(
    "/marketing-manager/analyze",
    response_model=GenericAgentResponse,
    summary="Run the Marketing Manager Agent (campaign + content suggestions)",
)
async def analyze_marketing(
    body: GenericAgentRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> GenericAgentResponse:
    """Analyze marketing context and generate campaign/content suggestions."""
    return await _run_agent("marketing-manager", body, db, workspace_id)


@router.post(
    "/supply-chain-manager/analyze",
    response_model=GenericAgentResponse,
    summary="Run the Supply Chain Manager Agent (supplier + cost + inventory)",
)
async def analyze_supply_chain(
    body: GenericAgentRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> GenericAgentResponse:
    """Analyze supply chain context and generate supplier/cost/inventory suggestions."""
    return await _run_agent("supply-chain-manager", body, db, workspace_id)


@router.post(
    "/customer-service-manager/analyze",
    response_model=GenericAgentResponse,
    summary="Run the Customer Service Manager Agent (response + satisfaction)",
)
async def analyze_customer_service(
    body: GenericAgentRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> GenericAgentResponse:
    """Analyze customer service context and generate response/satisfaction suggestions."""
    return await _run_agent("customer-service-manager", body, db, workspace_id)


@router.post(
    "/business-analyst/analyze",
    response_model=GenericAgentResponse,
    summary="Run the Business Analyst Agent (financial + KPI + trends)",
)
async def analyze_business(
    body: GenericAgentRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> GenericAgentResponse:
    """Analyze business context and generate financial/KPI/trend analysis."""
    return await _run_agent("business-analyst", body, db, workspace_id)
