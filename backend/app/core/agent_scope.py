"""Business-scope rules shared by the Agent runtime layers.

The Agent platform is a shared底座, but execution authority is not shared by
implication. Every agent, task, execution, tool, policy and approval decision
carries one of three business scopes:

``B2C``
    Retail-only capability. It may use B2C and SHARED resources.
``B2B``
    Wholesale-only capability. It may use B2B and SHARED resources.
``SHARED``
    Cross-business capability. It may use resources from either side.

Compatibility is directional: ``owner_scope`` is the caller's scope and
``target_scope`` is the resource being accessed.
"""

from __future__ import annotations

B2C = "B2C"
B2B = "B2B"
SHARED = "SHARED"

BUSINESS_SCOPES: tuple[str, ...] = (B2C, B2B, SHARED)
TASK_BUSINESS_SCOPES: tuple[str, ...] = (B2C, B2B, SHARED)


class AgentScopeError(ValueError):
    """Raised when an Agent business scope is missing or incompatible."""


def normalize_scope(value: str | None, *, default: str = SHARED) -> str:
    """Return a canonical scope or raise for an unknown value."""
    scope = (value or default).strip().upper()
    if scope not in BUSINESS_SCOPES:
        raise AgentScopeError(
            f"invalid business_scope '{value}'; expected one of {', '.join(BUSINESS_SCOPES)}"
        )
    return scope


def scope_compatible(owner_scope: str | None, target_scope: str | None) -> bool:
    """Return whether an owner may access a resource in the target scope.

    Unknown values are never compatible. This makes callers fail closed when
    a legacy row or malformed integration omits the scope.
    """
    try:
        owner = normalize_scope(owner_scope, default="")
        target = normalize_scope(target_scope, default="")
    except AgentScopeError:
        return False
    if owner == SHARED:
        return True
    if target == SHARED:
        return True
    return owner == target


def require_scope_compatible(
    owner_scope: str | None,
    target_scope: str | None,
    *,
    resource: str,
) -> None:
    """Raise a domain error when the target is outside the owner's scope."""
    if not scope_compatible(owner_scope, target_scope):
        raise AgentScopeError(
            f"{resource} scope '{target_scope}' is not compatible with "
            f"caller scope '{owner_scope}'"
        )
