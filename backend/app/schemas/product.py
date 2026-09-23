"""Product import request/response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImportRowError(BaseModel):
    """One failed CSV row."""

    row: int
    message: str


class ProductImportResult(BaseModel):
    """Summary of a CSV product import run."""

    imported: int
    updated: int
    failed: int
    errors: list[ImportRowError] = Field(default_factory=list)


class ProductOut(BaseModel):
    """Product as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    sku: str
    name: str
    description: str | None
    category: str | None
    brand: str | None
    status: str
    candidate_status: str | None = None
    # V3.0 独立评分漏斗阶段（rejected/test_candidate/testing/hero 等），
    # 以及一票否决时的失败规则快照，供前端在推送前做本地硬阻断展示。
    funnel_stage: str | None = None
    reject_reasons: list[Any] = Field(default_factory=list)
    source: str
    source_url: str | None
    tags: list[Any]
    attributes: dict[str, Any]
    meta: dict[str, Any]
    weight_kg: Decimal | None
    dimensions: dict[str, Any] | None
    target_market: str
    created_at: datetime
    updated_at: datetime


class ProductBatchDeleteRequest(BaseModel):
    """Request body for batch soft-deleting products."""

    product_ids: list[UUID] = Field(min_length=1, max_length=500)


class ProductDeleteResult(BaseModel):
    """Outcome of a single or batch soft-delete operation."""

    deleted: int
    not_found: list[UUID] = Field(default_factory=list)
