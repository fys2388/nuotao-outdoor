"""Supplier master data connector (M4.3).

Synchronizes supplier master records (e.g. 1688 shop metadata) into the OS.
Idempotency is keyed on ``(workspace, code)`` - the same unique constraint
used by product CSV import. No purchasing is ever triggered automatically.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import Connector, ConnectorError, SyncSummary
from app.models.supplier import Supplier
from app.services import event_service

logger = logging.getLogger(__name__)

_SUPPLIER_PLATFORMS: set[str] = {"1688", "alibaba", "manual", "other"}
_SUPPLIER_RATINGS: set[str] = {"A", "B", "C", "D"}


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


class SupplierConnector(Connector):
    """Supplier master upsert connector (read-only sync)."""

    name: str = "supplier"

    def validate(self, source: Any) -> list[str]:
        """Require a pushed batch of supplier records for M4.3."""
        if not isinstance(source, dict):
            return ["source must be an object with a 'data' list"]
        if not isinstance(source.get("data"), list) or not source["data"]:
            return ["data must be a non-empty list of supplier records"]
        return []

    def transform(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize raw supplier records."""
        normalized: list[dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                raise ConnectorError("each record must be an object")
            code = _as_str(record.get("code"))
            name = _as_str(record.get("name"))
            if not code or not name:
                raise ConnectorError("supplier record requires 'code' and 'name'")
            platform = _as_str(record.get("platform"), "1688").lower()
            if platform not in _SUPPLIER_PLATFORMS:
                raise ConnectorError(f"invalid platform '{platform}'")
            rating = _as_str(record.get("rating"), "C").upper()
            if rating not in _SUPPLIER_RATINGS:
                raise ConnectorError(f"invalid rating '{rating}'")
            contact = record.get("contact") if isinstance(record.get("contact"), dict) else {}
            normalized.append(
                {
                    "code": code,
                    "name": name,
                    "platform": platform,
                    "shop_url": _as_str(record.get("shop_url")) or None,
                    "rating": rating,
                    "status": _as_str(record.get("status"), "active") or "active",
                    "contact": contact,
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
        """Upsert supplier master records by (workspace, code)."""
        if not isinstance(source, dict) or not isinstance(source.get("data"), list):
            raise ConnectorError("data must be a list of supplier records")
        records = self.transform(source["data"])

        summary = SyncSummary()
        for record in records:
            created = await self._sync_supplier(
                session, workspace_id=workspace_id, record=record, trace_id=trace_id
            )
            summary.records_count += 1
            if created is True:
                summary.created_count += 1
            elif created is False:
                summary.updated_count += 1
            else:
                summary.skipped_count += 1
        logger.info("supplier sync records=%s trace=%s", summary.records_count, trace_id)
        return summary

    async def _sync_supplier(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> bool | None:
        """Create or update one supplier by (workspace, code)."""
        code = record["code"]
        existing = (
            await session.execute(
                select(Supplier).where(
                    Supplier.workspace_id == workspace_id,
                    Supplier.code == code,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            supplier = Supplier(
                workspace_id=workspace_id,
                code=code,
                name=record["name"],
                platform=record["platform"],
                shop_url=record.get("shop_url"),
                rating=record["rating"],
                status=record["status"],
                contact=record.get("contact") or {},
            )
            session.add(supplier)
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="supply.supplier_created",
                entity_type="supplier",
                entity_id=str(supplier.id),
                payload={"code": code, "platform": record["platform"]},
                trace_id=trace_id,
            )
            return True
        existing.name = record["name"]
        existing.platform = record["platform"]
        existing.shop_url = record.get("shop_url")
        existing.rating = record["rating"]
        existing.status = record["status"]
        existing.contact = record.get("contact") or {}
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="supply.supplier_updated",
            entity_type="supplier",
            entity_id=str(existing.id),
            payload={"code": code, "platform": record["platform"]},
            trace_id=trace_id,
        )
        return False
