"""Generic AI Agent framework for marketing, supply chain, customer service, and business analyst.

Provides a reusable LLM analysis pipeline:
- Context (JSON) -> Prompt (registry) -> LLM Gateway -> Structured JSON Output
- Audit logging via AiAgentRun
- Human-in-the-loop approval bridge

Each domain agent can use this framework with domain-specific prompts and output schemas.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AiAgentRun
from app.services import event_service, llm_gateway, prompt_registry
from app.services.llm_gateway import LLMError, LLMRequest, parse_json_content

logger = logging.getLogger(__name__)


@dataclass
class GenericAgentResult:
    """Result of a generic agent run."""

    agent_run: AiAgentRun | None
    output: dict[str, Any] | None
    error: str | None = None
    dry_run: bool = False


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


async def run_generic_agent(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str,
    agent_name: str,
    trigger: str,
    context: dict[str, Any],
    prompt_name: str,
    output_schema: dict[str, Any] | None = None,
    system_instruction: str = "Analyze the provided context and respond ONLY with a JSON object.",
    temperature: float = 0.3,
    task_type: str = "generic_agent",
    trace_id: str | None = None,
    persist: bool = True,
) -> GenericAgentResult:
    """Run a generic AI agent analysis pipeline.

    Args:
        agent_id: unique agent identifier (e.g. 'marketing_manager')
        agent_name: human-readable agent name
        trigger: trigger source for audit (e.g. 'api:marketing:analyze')
        context: domain-specific context data (JSON-serializable)
        prompt_name: prompt registry name to use
        output_schema: optional JSON schema for structured output validation
        system_instruction: instruction appended to the rendered prompt
        temperature: LLM temperature
        task_type: task type for LLM gateway routing
        persist: when False, skip audit persistence (dry-run)

    Returns:
        GenericAgentResult with output dict or error.
    """
    context = _json_safe(context)

    # 1. Load and render prompt from registry
    try:
        prompt = await prompt_registry.get_active_prompt(
            session, workspace_id=workspace_id, name=prompt_name
        )
        rendered = await prompt_registry.render_prompt(
            session,
            workspace_id=workspace_id,
            name=prompt_name,
            variables={
                "context_json": json.dumps(context, ensure_ascii=False),
                "output_schema": json.dumps(output_schema or {}, ensure_ascii=False),
            },
            trace_id=trace_id,
        )
    except Exception as exc:
        error_msg = f"prompt loading failed: {exc}"
        logger.error("[%s] %s", agent_id, error_msg)
        return GenericAgentResult(agent_run=None, output=None, error=error_msg)

    # 2. LLM Gateway call
    request = LLMRequest(
        messages=[
            {"role": "system", "content": rendered.text},
            {"role": "user", "content": system_instruction},
        ],
        task_type=task_type,
        response_format="json_object",
        temperature=temperature,
    )

    try:
        response = await llm_gateway.complete(request, trace_id=trace_id)
    except LLMError as exc:
        error_msg = f"LLM call failed: {exc}"
        logger.error("[%s] %s", agent_id, error_msg)
        if persist:
            await _persist_failure(
                session,
                workspace_id=workspace_id,
                agent_id=agent_id,
                agent_name=agent_name,
                trigger=trigger,
                context=context,
                error=error_msg,
                trace_id=trace_id,
            )
        return GenericAgentResult(agent_run=None, output=None, error=error_msg)

    # 3. Parse structured output
    try:
        parsed = parse_json_content(response.content)
        output = parsed if isinstance(parsed, dict) else {"result": parsed}
    except (LLMError, ValueError) as exc:
        error_msg = f"invalid structured output: {exc}"
        logger.error("[%s] %s", agent_id, error_msg)
        if persist:
            await _persist_failure(
                session,
                workspace_id=workspace_id,
                agent_id=agent_id,
                agent_name=agent_name,
                trigger=trigger,
                context=context,
                error=error_msg,
                provider=response.provider,
                model=response.model,
                tokens=response.tokens,
                cost=response.cost,
                latency_ms=response.latency_ms,
                prompt_version=prompt.version,
                trace_id=trace_id,
            )
        return GenericAgentResult(agent_run=None, output=None, error=error_msg)

    if not persist:
        return GenericAgentResult(agent_run=None, output=output, dry_run=True)

    # 4. Persist audit record
    agent_run = AiAgentRun(
        workspace_id=workspace_id,
        agent=agent_id,
        trigger=trigger,
        input={"context": context, "prompt_version": prompt.version},
        plan={"steps": ["load_prompt", "llm_gateway", "parse_output"]},
        tool_calls=[
            {
                "tool": "llm_gateway.complete",
                "provider": response.provider,
                "model": response.model,
                "tokens": response.tokens,
                "latency_ms": response.latency_ms,
            }
        ],
        output=_json_safe(output),
        approval={"required": False, "status": "not_required"},
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
        event_type=f"agent.{agent_id}.completed",
        entity_type="agent_run",
        entity_id=str(agent_run.id),
        payload={
            "agent": agent_id,
            "model": response.model,
            "cost": str(response.cost),
            "latency_ms": response.latency_ms,
        },
        trace_id=trace_id,
    )

    logger.info(
        "[%s] completed model=%s tokens=%s cost=%s trace=%s",
        agent_id,
        response.model,
        response.tokens,
        response.cost,
        trace_id,
    )

    return GenericAgentResult(agent_run=agent_run, output=output)


async def _persist_failure(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_id: str,
    agent_name: str,
    trigger: str,
    context: dict[str, Any],
    error: str,
    provider: str | None = None,
    model: str | None = None,
    tokens: dict[str, int] | None = None,
    cost: Decimal | None = None,
    latency_ms: int | None = None,
    prompt_version: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Record a failed agent run for audit."""
    agent_run = AiAgentRun(
        workspace_id=workspace_id,
        agent=agent_id,
        trigger=trigger,
        input={"context": context, "prompt_version": prompt_version},
        plan={"steps": ["load_prompt", "llm_gateway", "parse_output"]},
        tool_calls=[],
        output={"error": error},
        approval={"required": False, "status": "not_required"},
        cost=cost or Decimal("0"),
        status="failed",
        trace_id=trace_id,
        completed_at=datetime.now(UTC),
    )
    session.add(agent_run)
    await session.flush()

    await event_service.create_event(
        session,
        workspace_id=workspace_id,
        event_type=f"agent.{agent_id}.failed",
        entity_type="agent_run",
        entity_id=str(agent_run.id),
        payload={"error": error[:500]},
        trace_id=trace_id,
    )
