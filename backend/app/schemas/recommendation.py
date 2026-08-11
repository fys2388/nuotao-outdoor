"""Business recommendation schemas (M4.3)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RECOMMENDATION_DOMAINS: tuple[str, ...] = (
    "product",
    "marketing",
    "customer",
    "supply_chain",
    "operations",
)


class RecommendationCreate(BaseModel):
    """Propose a business recommendation (decision intelligence output)."""

    domain: Literal[
        "product",
        "marketing",
        "customer",
        "supply_chain",
        "operations",
    ]
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=64)
    recommendation: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=2000)
    confidence: Decimal = Field(default=Decimal("0"), ge=0, le=1)


class RecommendationApproveRequest(BaseModel):
    """Human approval/rejection of a business recommendation."""

    actor: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class RecommendationOut(BaseModel):
    """A business recommendation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    domain: str
    entity_type: str
    entity_id: str
    recommendation: str
    reason: str | None
    confidence: Decimal
    status: str
    approved_by: str | None
    approved_at: datetime | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
