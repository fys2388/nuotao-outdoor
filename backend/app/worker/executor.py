"""Generic agent execution executor (M5.1).

The runtime's default executor: render the agent's versioned prompt from the
Prompt Registry, bound the task input as the user message, call the LLM
Gateway, and return structured metrics. It is intentionally generic - the
business context builders (product/campaign/customer) belong to the specific
agents built in later milestones. The worker accepts any callable with the
same signature, so agents can plug their own context assembly at M5.2.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentRegistry, AgentTask
from app.models.agent_runtime_hardening import AgentExecutionPolicy
from app.services import agent_runtime, llm_gateway


@dataclass(frozen=True)
class ExecutionResult:
    """Structured outcome of one agent execution attempt."""

    output: dict[str, Any]
    provider: str
    model: str
    tokens: dict[str, int] = field(default_factory=dict)
    cost: Decimal = Decimal("0")
    latency_ms: int = 0


def _parse_json_content(content: str) -> dict[str, Any]:
    """Parse model output; tolerate code fences, fall back to a text payload."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except (json.JSONDecodeError, TypeError):
        return {"text": content[:4000]}


async def llm_executor(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent: AgentRegistry,
    task: AgentTask,
    policy: AgentExecutionPolicy,
    trace_id: str | None = None,
) -> ExecutionResult:
    """Render the versioned prompt and run the model through the gateway."""
    prompt = await agent_runtime.resolve_agent_prompt(
        session, workspace_id=workspace_id, agent_uuid=agent.id
    )
    variables: dict[str, str] = {}
    for key in prompt.variables or []:
        value = task.input.get(key)
        variables[key] = "" if value is None else str(value)
    try:
        rendered = prompt.template.format_map(variables)
    except (KeyError, ValueError):
        rendered = prompt.template

    user_content = json.dumps(task.input, ensure_ascii=False, default=str)
    user_content = user_content[: policy.max_context_size]

    request = llm_gateway.LLMRequest(
        messages=[
            {"role": "system", "content": rendered},
            {"role": "user", "content": user_content},
        ],
        provider=agent.model_provider,
        model=agent.model_name,
        task_type=f"agent.{agent.agent_id}",
        response_format="json_object",
    )
    started = time.perf_counter()
    response = await llm_gateway.complete(request, trace_id=trace_id)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ExecutionResult(
        output=_parse_json_content(response.content),
        provider=response.provider,
        model=response.model,
        tokens=response.tokens,
        cost=response.cost,
        latency_ms=latency_ms,
    )
