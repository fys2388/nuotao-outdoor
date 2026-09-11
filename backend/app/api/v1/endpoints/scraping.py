"""Scraping API endpoints (M5.16, compliance-gated).

``POST /api/v1/scraping/jobs`` submits a scraping job. The route only performs
parameter validation + RBAC and delegates to :func:`app.services.scraping`. No
business logic lives here. Scraping is disabled by default; the service refuses
to run when ``SCRAPING_ENABLED=false`` or no domain is allowlisted.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import resolve_actor
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.core.workspace import get_workspace_id
from app.schemas.scraping import ScrapeJobRequest, ScrapeJobResultOut
from app.services import scraping
from app.services.approval_rbac import ApprovalRBACError, check_actor_permission
from app.services.product_intelligence import ProductDecisionActorError

router = APIRouter(prefix="/scraping", tags=["scraping"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
WorkspaceId = Annotated[UUID, Depends(get_workspace_id)]


def _http_error(exc: Exception) -> HTTPException:
    """Map service errors: RBAC/actor -> 403, config/validation -> 400."""
    if isinstance(exc, (ApprovalRBACError, ProductDecisionActorError)):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/jobs",
    response_model=ScrapeJobResultOut,
    summary="Submit a scraping job (disabled by default, RBAC-guarded)",
)
async def submit_scrape_job(
    body: ScrapeJobRequest,
    request: Request,
    db: DbSession,
    workspace_id: WorkspaceId,
) -> ScrapeJobResultOut:
    """Scrape a bounded set of public URLs and persist results as candidates.

    Requires the actor to hold ``scraping.job.submit`` (403 otherwise). The
    job only runs when scraping is enabled and the domains are allowlisted;
    otherwise a 400 is returned. Results enter the standard Product Candidate
    human-approval chain - nothing is auto-published or auto-purchased.
    """
    actor = resolve_actor(request, body.actor) if getattr(body, "actor", None) else None
    try:
        if actor:
            await check_actor_permission(
                db,
                workspace_id=workspace_id,
                actor=actor,
                permission="scraping.job.submit",
            )
        result = await scraping.run_scrape_job(
            db,
            workspace_id=workspace_id,
            urls=body.urls,
            trace_id=get_trace_id(),
        )
    except (scraping.ScrapingServiceError, scraping.ScrapingError) as exc:
        raise _http_error(exc) from exc
    except ApprovalRBACError as exc:
        raise _http_error(exc) from exc
    return ScrapeJobResultOut(
        requested=result.requested,
        succeeded=result.succeeded,
        failed=result.failed,
        product_ids=result.product_ids,
        errors=result.errors,
    )
