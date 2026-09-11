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
