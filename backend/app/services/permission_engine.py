"""Permission Engine (M5.0): L0-L3 gates for every agent tool call.

Levels are monotonic - a higher level includes all lower levels:

- L0: public read (product public info, marketing content)
- L1: internal read (cost, suppliers, order stats, knowledge)
- L2: proposal (create analysis, recommendations, drafts)
- L3: high-risk execution (approve, purchase, refund, publish)

Rules enforced here are pure functions so they are unit-testable without a
database; the runtime service applies them to every tool call and records
the outcome (allowed / requires_approval / denied) in the execution audit.
"""

from typing import Any

PERMISSION_LEVELS: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


class PermissionError(Exception):
    """Raised when an agent lacks permission for a tool."""


def level_rank(level: str) -> int:
    """Return the numeric rank of a permission level (unknown -> 0)."""
    return PERMISSION_LEVELS.get(level, 0)


def can_access(agent_level: str, tool_level: str) -> bool:
    """True when an agent level covers a tool level (agent >= tool)."""
    return level_rank(agent_level) >= level_rank(tool_level)


def requires_approval(tool_level: str) -> bool:
    """True when a tool is high-risk and needs human approval (L3)."""
    return tool_level == "L3"


def check_tool(
    *,
    agent_level: str,
    tool_level: str,
    tool_name: str,
    enabled: bool = True,
) -> dict[str, Any]:
    """Evaluate one tool call against the whitelist + permission rules.

    Returns a decision dict: ``allowed`` (executable now), ``requires_approval``
    (high-risk, must stop for a human), or ``denied`` (not permitted).

    Raises:
        PermissionError: when the tool is disabled or the agent level is too low.
    """
    if not enabled:
        raise PermissionError(f"tool '{tool_name}' is disabled")
    if not can_access(agent_level, tool_level):
        raise PermissionError(
            f"agent level {agent_level} cannot call tool '{tool_name}' (requires {tool_level})"
        )
    if requires_approval(tool_level):
        return {"status": "requires_approval", "requires_approval": True}
    return {"status": "allowed", "requires_approval": False}
