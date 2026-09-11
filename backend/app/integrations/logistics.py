"""Logistics tracking connector (M4.3).

Synchronizes shipment tracking state and events into the OS. Idempotency is
keyed on ``tracking_number`` (per workspace): a shipment is created on first
sighting and updated on subsequent syncs; tracking events are append-only and
de-duplicated by (event_type, location, description, occurred_at).
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import Connector, ConnectorError, SyncSummary
from app.models.supply_chain import LogisticsEvent, ShipmentRecord
from app.schemas.supply_chain import LogisticsEventCreate, ShipmentCreate, ShipmentUpdate
from app.services import supply_chain

logger = logging.getLogger(__name__)

_SHIPMENT_STATUSES: set[str] = {"created", "in_transit", "delivered", "failed", "delayed"}


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _canonical_time(value: Any) -> str:
    """Canonical UTC ISO-8601 string for dedupe ('' for missing values).

    SQLite stores naive datetimes while incoming records may carry a ``Z`` /
    offset suffix; normalizing both sides to UTC keeps the comparison stable.
    """
    if value is None:
        return ""
    if not isinstance(value, datetime):
        text = str(value).strip()
        if not text:
            return ""
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            return text
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


class LogisticsConnector(Connector):
    """Tracking sync connector: creates/updates shipments + appends events."""

    name: str = "logistics"

    def validate(self, source: Any) -> list[str]:
        """Require a pushed batch of tracking records for M4.3."""
        if not isinstance(source, dict):
            return ["source must be an object with a 'data' list"]
        if not isinstance(source.get("data"), list) or not source["data"]:
            return ["data must be a non-empty list of tracking records"]
        return []

    def transform(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize raw tracking records (no PII is extracted)."""
        normalized: list[dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                raise ConnectorError("each record must be an object")
            tracking_number = _as_str(record.get("tracking_number"))
            if not tracking_number:
                raise ConnectorError("tracking record requires 'tracking_number'")
            carrier = _as_str(record.get("carrier"))
            if not carrier:
                raise ConnectorError("tracking record requires 'carrier'")
            status = _as_str(record.get("status"), "created").lower()
            if status not in _SHIPMENT_STATUSES:
                raise ConnectorError(f"invalid shipment status '{status}'")
            events = record.get("events") if isinstance(record.get("events"), list) else []
            normalized.append(
                {
                    "tracking_number": tracking_number,
                    "carrier": carrier,
                    "status": status,
                    "origin": _as_str(record.get("origin")) or None,
                    "destination": _as_str(record.get("destination")) or None,
                    "ship_date": record.get("ship_date"),
                    "delivery_time_days": record.get("delivery_time_days"),
                    "delay_reason": _as_str(record.get("delay_reason")) or None,
                    "events": [
                        {
                            "event_type": _as_str(event.get("event_type")),
                            "location": _as_str(event.get("location")) or None,
                            "description": _as_str(event.get("description")) or None,
                            "occurred_at": event.get("occurred_at"),
                        }
                        for event in events
                        if isinstance(event, dict) and _as_str(event.get("event_type"))
                    ],
                }
            )
        return normalized

    async def sync(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        source: Any,
        trace_id: str | None,
    ) -> SyncSummary:
        """Upsert shipments by tracking number and append new tracking events."""
        if not isinstance(source, dict) or not isinstance(source.get("data"), list):
            raise ConnectorError("data must be a list of tracking records")
        records = self.transform(source["data"])

        summary = SyncSummary()
        for record in records:
            created = await self._sync_shipment(
                session, workspace_id=workspace_id, record=record, trace_id=trace_id
            )
            events_added = await self._sync_events(
                session, workspace_id=workspace_id, record=record, trace_id=trace_id
            )
            summary.records_count += 1
            if created is True:
                summary.created_count += 1
            elif created is False:
                summary.updated_count += 1
            else:
                summary.skipped_count += 1
            summary.created_count += events_added
        logger.info("logistics sync records=%s trace=%s", summary.records_count, trace_id)
        return summary

    async def _sync_shipment(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> bool | None:
        """Create or update one shipment by (workspace, tracking_number)."""
        tracking_number = record["tracking_number"]
        existing = (
            await session.execute(
                select(ShipmentRecord).where(
                    ShipmentRecord.workspace_id == workspace_id,
                    ShipmentRecord.tracking_number == tracking_number,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            shipment = await supply_chain.create_shipment(
                session,
                workspace_id=workspace_id,
                data=ShipmentCreate(
                    carrier=record["carrier"],
                    origin=record.get("origin"),
                    destination=record.get("destination"),
                    tracking_number=tracking_number,
                    status=record["status"],
                    ship_date=record.get("ship_date"),
                    delivery_time_days=record.get("delivery_time_days"),
                    delay_reason=record.get("delay_reason"),
                ),
                trace_id=trace_id,
            )
            logger.info("shipment %s created from logistics sync", shipment.id)
            return True
        await supply_chain.update_shipment(
            session,
            workspace_id=workspace_id,
            shipment_id=existing.id,
            data=ShipmentUpdate(
                status=record["status"],
                delivery_time_days=record.get("delivery_time_days"),
                delay_reason=record.get("delay_reason"),
            ),
            trace_id=trace_id,
        )
        return False

    async def _sync_events(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> int:
        """Append tracking events, skipping already-recorded ones (idempotent)."""
        events = record.get("events") or []
        if not events:
            return 0
        shipment = (
            await session.execute(
                select(ShipmentRecord).where(
                    ShipmentRecord.workspace_id == workspace_id,
                    ShipmentRecord.tracking_number == record["tracking_number"],
                )
            )
        ).scalar_one_or_none()
        if shipment is None:
            return 0
        existing_rows = (
            (
                await session.execute(
                    select(LogisticsEvent).where(
                        LogisticsEvent.workspace_id == workspace_id,
                        LogisticsEvent.shipment_id == shipment.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        seen = {
            (
                row.event_type,
                row.location or "",
                row.description or "",
                _canonical_time(row.occurred_at),
            )
            for row in existing_rows
        }
        added = 0
        for event in events:
            key = (
                event["event_type"],
                event.get("location") or "",
                event.get("description") or "",
                _canonical_time(event.get("occurred_at")),
            )
            if key in seen:
                continue
            await supply_chain.add_logistics_event(
                session,
                workspace_id=workspace_id,
                shipment_id=shipment.id,
                data=LogisticsEventCreate(
                    event_type=event["event_type"],
                    location=event.get("location"),
                    description=event.get("description"),
                    occurred_at=event.get("occurred_at"),
                ),
                trace_id=trace_id,
            )
            seen.add(key)
            added += 1
        return added
