"""Rule registry and rule engine API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import resolve_actor
from app.core.database import get_db
from app.core.workspace import get_workspace_id
from app.schemas.rule import (
    CheckResult,
    OverrideResult,
    RuleCheckRequest,
    RuleCreate,
    RuleEvaluateRequest,
    RuleOut,
    RuleOverrideRequest,
    RuleResult,
    RuleSuggestRequest,
    SuggestResult,
)
from app.services import rule_engine

router = APIRouter(prefix="/rules", tags=["rules"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: rule_engine.RuleEngineError) -> HTTPException:
    """Map rule engine errors to HTTP responses."""
    if isinstance(exc, rule_engine.RuleConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("", response_model=RuleOut, status_code=201, summary="Create a rule")
async def create_rule(
    body: RuleCreate,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RuleOut:
    """Register a new versioned rule (rules always come from the database)."""
    try:
        rule = await rule_engine.create_rule(db, workspace_id=workspace_id, data=body)
    except rule_engine.RuleEngineError as exc:
        raise _http_error(exc) from exc
    return RuleOut.model_validate(rule)


@router.get("", response_model=list[RuleOut], summary="List rules")
async def list_rules(
    db: DbSession,
    workspace_id: WorkspaceId,
    category: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[RuleOut]:
    """List rules with optional category/status filters."""
    rules = await rule_engine.list_rules(
        db,
        workspace_id=workspace_id,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [RuleOut.model_validate(rule) for rule in rules]


@router.get("/{rule_id}", response_model=RuleOut, summary="Get a rule")
async def get_rule(
    rule_id: str,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RuleOut:
    """Return the newest active version of a rule."""
    try:
        rule = await rule_engine.get_rule(db, workspace_id=workspace_id, rule_id=rule_id)
    except rule_engine.RuleEngineError as exc:
        raise _http_error(exc) from exc
    return RuleOut.model_validate(rule)


@router.post("/check", response_model=CheckResult, summary="Check rules against context")
async def check(
    body: RuleCheckRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> CheckResult:
    """Evaluate a rule or a whole group; every evaluation is audited."""
    try:
        return await rule_engine.check(
            db,
            workspace_id=workspace_id,
            context=body.context,
            rule_id=body.rule_id,
            group=body.group,
        )
    except rule_engine.RuleEngineError as exc:
        raise _http_error(exc) from exc


@router.post("/evaluate", response_model=RuleResult, summary="Evaluate a single rule")
async def evaluate(
    body: RuleEvaluateRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> RuleResult:
    """Evaluate one rule (hard/flow) against a context."""
    try:
        return await rule_engine.evaluate(
            db,
            workspace_id=workspace_id,
            rule_id=body.rule_id,
            context=body.context,
            version=body.version,
        )
    except rule_engine.RuleEngineError as exc:
        raise _http_error(exc) from exc


@router.post("/suggest", response_model=SuggestResult, summary="Score a soft rule group")
async def suggest(
    body: RuleSuggestRequest,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> SuggestResult:
    """Score the soft rules of a group and aggregate a weighted total."""
    return await rule_engine.suggest(
        db,
        workspace_id=workspace_id,
        group=body.group,
        context=body.context,
    )


@router.post("/override", response_model=OverrideResult, summary="Record a rule override")
async def override(
    body: RuleOverrideRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> OverrideResult:
    """Audit a human override of a rule decision (execution stays manual)."""
    try:
        return await rule_engine.override(
            db,
            workspace_id=workspace_id,
            rule_id=body.rule_id,
            context=body.context,
            reason=body.reason,
            actor=resolve_actor(request, body.actor),
        )
    except rule_engine.RuleEngineError as exc:
        raise _http_error(exc) from exc
