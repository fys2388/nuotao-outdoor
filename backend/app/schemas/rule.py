"""Rule registry and rule engine request/response schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RuleCreate(BaseModel):
    """Payload for creating a new (versioned) rule in the registry."""

    rule_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    rule_type: Literal["hard", "soft", "flow"] = "hard"
    version: str = Field(default="v1", max_length=16)
    status: Literal["draft", "active", "deprecated"] = "draft"
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    when_conditions: dict[str, Any]
    then_result: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    approval_level: str = Field(default="L0", max_length=8)
    owner: str | None = Field(default=None, max_length=128)


class RuleOut(BaseModel):
    """Rule as stored in the registry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    rule_id: str
    name: str
    category: str
    rule_type: str
    version: str
    status: str
    effective_from: datetime | None
    effective_to: datetime | None
    scope: dict[str, Any]
    when_conditions: dict[str, Any]
    then_result: dict[str, Any]
    params: dict[str, Any]
    approval_level: str
    owner: str | None
    created_at: datetime
    updated_at: datetime


class RuleCheckRequest(BaseModel):
    """Check one rule or a whole group against a context."""

    rule_id: str | None = Field(default=None, max_length=64)
    group: str | None = Field(default=None, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)


class RuleEvaluateRequest(BaseModel):
    """Evaluate a single rule against a context."""

    rule_id: str = Field(min_length=1, max_length=64)
    version: str | None = Field(default=None, max_length=16)
    context: dict[str, Any] = Field(default_factory=dict)


class RuleSuggestRequest(BaseModel):
    """Score the soft rules of a group against a context."""

    group: str = Field(min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)


class RuleOverrideRequest(BaseModel):
    """Request a human override for a rule decision (audited)."""

    rule_id: str = Field(min_length=1, max_length=64)
    context: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=500)
    actor: str = Field(min_length=1, max_length=128)


class RuleResult(BaseModel):
    """Outcome of evaluating one rule."""

    rule_id: str
    name: str
    rule_version: str
    rule_type: str
    passed: bool
    score: float | None = None
    reasons: list[str] = Field(default_factory=list)
    trace_id: str


class CheckResult(BaseModel):
    """Outcome of checking a rule or a group of rules."""

    all_passed: bool
    results: list[RuleResult] = Field(default_factory=list)


class SuggestResult(BaseModel):
    """Weighted score aggregation of a soft rule group."""

    group: str
    aggregate_score: float | None = None
    results: list[RuleResult] = Field(default_factory=list)


class OverrideResult(BaseModel):
    """Recorded rule override."""

    rule_id: str
    rule_version: str
    overridden: bool
    reason: str
    actor: str
    trace_id: str
