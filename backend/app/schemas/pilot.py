"""M5.6 Product Analyst pilot API schemas.

The pilot endpoint only *creates and waits on* an agent task; it never
approves, starts experiments or executes business actions.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PilotRequest(BaseModel):
    """Run one product-analysis pilot (task creation + optional wait)."""

    product_id: UUID
    wait_seconds: int | None = Field(default=None, ge=1, le=600)
    actor: str | None = Field(default=None, max_length=64)


class PilotOut(BaseModel):
    """Outcome of a pilot task (terminal status when waited)."""

    task_id: UUID
    workspace_id: UUID
    product_id: UUID
    trace_id: str | None = None
    status: str
    analysis_run_id: UUID | None = None
    decision_proposal_id: UUID | None = None
    decision: str | None = None
    approval_status: str | None = None
    provider: str | None = None
    model: str | None = None
    cost: Decimal | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    waiting: bool = False
