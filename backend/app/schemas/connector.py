"""Connector run schemas (M4.3)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

CONNECTOR_NAMES: tuple[str, ...] = ("woocommerce", "logistics", "marketing", "supplier")


class ConnectorSyncRequest(BaseModel):
    """Trigger a connector sync.

    ``data`` is a pushed batch of raw external records (manual/testing runs);
    ``config`` carries live-source configuration (e.g. WooCommerce REST
    credentials). When ``data`` is omitted the connector validates and uses
    ``config`` for a live fetch.
    """

    data: list[dict[str, Any]] | None = None
    config: dict[str, Any] | None = None


class ConnectorRunOut(BaseModel):
    """A connector run audit row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    connector_name: str
    status: str
    records_count: int
    error_message: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
