"""Prompt registry schemas (M2.2)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromptCreate(BaseModel):
    """Register a versioned prompt template."""

    prompt_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    version: str = Field(default="v1", pattern=r"^v\d+$")
    template: str = Field(min_length=1, max_length=12000)
    variables: list[str] = Field(default_factory=list)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    description: str | None = Field(default=None, max_length=500)


class PromptOut(BaseModel):
    """A prompt row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    prompt_id: str
    name: str
    version: str
    template: str
    variables: list[Any]
    status: str
    description: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
