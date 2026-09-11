"""Marketing metrics connector (M4.3).

Synchronizes campaign metrics into the OS through the existing marketing
service. Idempotency is keyed on ``(workspace, platform, campaign_id)``: the
campaign is created on first sighting and updated on subsequent syncs. No
advertising action is ever executed - metrics sync is read-only.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import Connector, ConnectorError, SyncSummary
from app.models.marketing import Campaign
from app.schemas.marketing import CampaignCreate, CampaignUpdate
from app.services import marketing

logger = logging.getLogger(__name__)

_PLATFORMS: set[str] = {"meta", "google", "tiktok", "pinterest", "other"}
_CAMPAIGN_STATUSES: set[str] = {"active", "paused", "completed", "archived"}


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


class MarketingConnector(Connector):
    """Campaign metrics sync connector (read-only)."""

    name: str = "marketing"

    def validate(self, source: Any) -> list[str]:
        """Require a pushed batch of campaign metric records for M4.3."""
        if not isinstance(source, dict):
            return ["source must be an object with a 'data' list"]
        if not isinstance(source.get("data"), list) or not source["data"]:
            return ["data must be a non-empty list of campaign records"]
        return []

    def transform(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize raw campaign metric records."""
        normalized: list[dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                raise ConnectorError("each record must be an object")
            platform = _as_str(record.get("platform"), "meta").lower()
            if platform not in _PLATFORMS:
                raise ConnectorError(f"invalid platform '{platform}'")
            campaign_id = _as_str(record.get("campaign_id"))
            if not campaign_id:
                raise ConnectorError("campaign record requires 'campaign_id'")
            status = _as_str(record.get("status"), "active").lower()
            if status not in _CAMPAIGN_STATUSES:
                raise ConnectorError(f"invalid campaign status '{status}'")
            normalized.append(
                {
                    "platform": platform,
                    "campaign_id": campaign_id,
                    "name": _as_str(record.get("name")) or None,
                    "status": status,
                    "currency": _as_str(record.get("currency"), "USD"),
                    "budget": str(record.get("budget") or 0),
                    "spend": str(record.get("spend") or 0),
                    "impressions": int(record.get("impressions") or 0),
                    "clicks": int(record.get("clicks") or 0),
                    "conversion": int(record.get("conversion") or record.get("conversions") or 0),
                    "revenue": str(record.get("revenue") or 0),
                    "started_at": record.get("started_at"),
                    "ended_at": record.get("ended_at"),
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
        """Upsert campaign metrics by (workspace, platform, campaign_id)."""
        if not isinstance(source, dict) or not isinstance(source.get("data"), list):
            raise ConnectorError("data must be a list of campaign records")
        records = self.transform(source["data"])

        summary = SyncSummary()
        for record in records:
            created = await self._sync_campaign(
                session, workspace_id=workspace_id, record=record, trace_id=trace_id
            )
            summary.records_count += 1
            if created is True:
                summary.created_count += 1
            elif created is False:
                summary.updated_count += 1
            else:
                summary.skipped_count += 1
        logger.info("marketing sync records=%s trace=%s", summary.records_count, trace_id)
        return summary

    async def _sync_campaign(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> bool | None:
        """Create or update one campaign (409 on create -> update instead)."""
        platform = record["platform"]
        campaign_id = record["campaign_id"]
        # Pre-check first so the create path never triggers an IntegrityError
        # rollback that would detach the outer ConnectorRun from the session.
        existing = (
            await session.execute(
                select(Campaign).where(
                    Campaign.workspace_id == workspace_id,
                    Campaign.platform == platform,
                    Campaign.campaign_id == campaign_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            await marketing.update_campaign(
                session,
                workspace_id=workspace_id,
                campaign_id=existing.id,
                data=CampaignUpdate(
                    name=record.get("name"),
                    status=record["status"],
                    budget=record.get("budget"),
                    spend=record.get("spend"),
                    impressions=record.get("impressions"),
                    clicks=record.get("clicks"),
                    conversion=record.get("conversion"),
                    revenue=record.get("revenue"),
                    started_at=record.get("started_at"),
                    ended_at=record.get("ended_at"),
                ),
                trace_id=trace_id,
            )
            return False
        try:
            await marketing.create_campaign(
                session,
                workspace_id=workspace_id,
                data=CampaignCreate(
                    platform=platform,
                    campaign_id=campaign_id,
                    name=record.get("name"),
                    status=record["status"],
                    currency=record.get("currency") or "USD",
                    budget=record.get("budget") or "0",
                    spend=record.get("spend") or "0",
                    impressions=record.get("impressions") or 0,
                    clicks=record.get("clicks") or 0,
                    conversion=record.get("conversion") or 0,
                    revenue=record.get("revenue") or "0",
                    started_at=record.get("started_at"),
                    ended_at=record.get("ended_at"),
                ),
                trace_id=trace_id,
            )
            return True
        except marketing.MarketingError as exc:
            if "already exists" not in str(exc):
                raise ConnectorError(str(exc)) from exc
        # A concurrent delivery raced the pre-check; treat as updated.
        existing = (
            await session.execute(
                select(Campaign).where(
                    Campaign.workspace_id == workspace_id,
                    Campaign.platform == platform,
                    Campaign.campaign_id == campaign_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise ConnectorError(f"campaign '{platform}/{campaign_id}' not found for update")
        await marketing.update_campaign(
            session,
            workspace_id=workspace_id,
            campaign_id=existing.id,
            data=CampaignUpdate(
                name=record.get("name"),
                status=record["status"],
                budget=record.get("budget"),
                spend=record.get("spend"),
                impressions=record.get("impressions"),
                clicks=record.get("clicks"),
                conversion=record.get("conversion"),
                revenue=record.get("revenue"),
                started_at=record.get("started_at"),
                ended_at=record.get("ended_at"),
            ),
            trace_id=trace_id,
        )
        return False
