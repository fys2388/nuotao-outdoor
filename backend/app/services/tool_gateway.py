"""Tool gateway + handler registry (M5.1).

M5.0 introduced the whitelist + L0-L3 permission gate with audit-only
outcomes. M5.1 adds the execution half: a tool row may bind an in-process
handler (``handler_name`` + ``args_schema``). Bound handlers are executed
through the gateway; unbound whitelist-only tools keep the M5.0 audit-only
behavior. L3 tools never auto-execute - they stop at ``waiting_approval``
with a policy-driven approval deadline for a human decision.

Handlers are plain async callables registered under a name; they receive a
typed :class:`ToolContext` and MUST return JSON-serializable dicts. No
handler may touch the database directly - it only sees the context (session
included for future read-only services) and returns a result that is
appended to the execution audit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_runtime import AgentExecution, AgentRegistry, AgentTool

ToolHandlerFn = Callable[[dict[str, Any], "ToolContext"], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolContext:
    """Everything a handler may need; immutable and minimal by design."""

    session: AsyncSession
    workspace_id: UUID
    agent: AgentRegistry
    execution: AgentExecution
    tool: AgentTool
    trace_id: str | None = None


class ToolHandler(Protocol):
    """A registered tool handler (async, JSON-safe result)."""

    async def __call__(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]: ...


# In-process handler registry: name -> handler callable.
TOOL_HANDLERS: dict[str, ToolHandlerFn] = {}


def register_handler(name: str, handler: ToolHandlerFn) -> None:
    """Register (or replace) an in-process tool handler by name."""
    TOOL_HANDLERS[name] = handler


def unregister_handler(name: str) -> None:
    """Remove a registered handler (used by tests)."""
    TOOL_HANDLERS.pop(name, None)


def get_handler(name: str | None) -> ToolHandlerFn | None:
    """Return the registered handler for a tool, if any."""
    if not name:
        return None
    return TOOL_HANDLERS.get(name)


class ToolGatewayError(Exception):
    """Raised when a tool call cannot be executed through the gateway."""


async def execute_handler(
    *,
    session: AsyncSession,
    workspace_id: UUID,
    agent: AgentRegistry,
    execution: AgentExecution,
    tool: AgentTool,
    arguments: dict[str, Any],
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Run a bound handler and return its result (raises when unbound)."""
    handler = get_handler(tool.handler_name)
    if handler is None:
        raise ToolGatewayError(
            f"tool '{tool.tool_name}' has no registered handler "
            f"(handler_name={tool.handler_name!r}); refusing to execute"
        )
    context = ToolContext(
        session=session,
        workspace_id=workspace_id,
        agent=agent,
        execution=execution,
        tool=tool,
        trace_id=trace_id,
    )
    return await handler(arguments or {}, context)
