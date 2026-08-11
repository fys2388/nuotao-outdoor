"""Connector orchestration service (M4.3).

Runs one connector sync end-to-end inside a single audit envelope:

1. Resolve the connector by name (whitelist, no dynamic imports).
2. ``validate()`` the source before touching any data.
3. Create a ``ConnectorRun`` (status=running) with the request trace_id.
4. ``sync()`` the records through the existing services (idempotent).
5. Persist the run outcome (success/failed + records_count/error_message).
6. ``audit()`` appends a ``connector.run_completed`` event.

No connector ever executes a business action; failures are recorded in the
run log so the operations team can retry safely.
"""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import Connector
from app.integrations.logistics import LogisticsConnector
from app.integrations.marketing import MarketingConnector
from app.integrations.supplier import SupplierConnector
from app.integrations.woocommerce import WooCommerceConnector
from app.models.connector import ConnectorRun

logger = logging.getLogger(__name__)

# Registered connectors (whitelist; M4.3 scope).
CONNECTORS: dict[str, Connector] = {
    "woocommerce": WooCommerceConnector(),
    "logistics": LogisticsConnector(),
    "marketing": MarketingConnector(),
    "supplier": SupplierConnector(),
}


class ConnectorServiceError(Exception):
    """Raised when a connector sync cannot start or completes with errors."""


async def run_connector_sync(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connector_name: str,
    source: dict,
    trace_id: str | None = None,
) -> ConnectorRun:
    """Run one connector sync and return its audit record."""
    connector = CONNECTORS.get(connector_name)
    if connector is None:
        raise ConnectorServiceError(f"unknown connector '{connector_name}'")

    issues = connector.validate(source)
    if issues:
        raise ConnectorServiceError("; ".join(issues))

    run = ConnectorRun(
        workspace_id=workspace_id,
        connector_name=connector_name,
        status="running",
        trace_id=trace_id,
    )
    session.add(run)
    await session.flush()

    try:
        summary = await connector.sync(
            session, workspace_id=workspace_id, source=source, trace_id=trace_id
        )
    except Exception as exc:  # noqa: BLE001 - the run log must capture every failure
        # A nested service may have rolled the session back (e.g. duplicate
        # create), detaching the run instance; re-load it from the database.
        failed = await session.get(ConnectorRun, run.id)
        if failed is None:
            failed = ConnectorRun(
                workspace_id=workspace_id,
                connector_name=connector_name,
                status="failed",
                trace_id=trace_id,
            )
            session.add(failed)
        failed.status = "failed"
        failed.records_count = 0
        failed.error_message = str(exc)[:1000]
        await session.commit()
        await connector.audit(session, workspace_id=workspace_id, run=failed, trace_id=trace_id)
        logger.warning("connector %s sync failed: %s trace=%s", connector_name, exc, trace_id)
        raise ConnectorServiceError(f"connector '{connector_name}' sync failed: {exc}") from exc

    run = await session.get(ConnectorRun, run.id)
    if run is None:
        run = ConnectorRun(
            workspace_id=workspace_id,
            connector_name=connector_name,
            status="success",
            trace_id=trace_id,
        )
        session.add(run)
    run.status = "success"
    run.records_count = summary.records_count
    await session.commit()
    await connector.audit(session, workspace_id=workspace_id, run=run, trace_id=trace_id)
    await session.refresh(run)
    logger.info(
        "connector %s sync succeeded records=%s trace=%s",
        connector_name,
        run.records_count,
        trace_id,
    )
    return run


async def list_connector_runs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    connector_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ConnectorRun], int]:
    """Query connector run audit records (workspace-scoped)."""
    filters = [ConnectorRun.workspace_id == workspace_id]
    if connector_name:
        filters.append(ConnectorRun.connector_name == connector_name)
    if status:
        filters.append(ConnectorRun.status == status)

    total = (
        await session.execute(select(func.count()).select_from(ConnectorRun).where(*filters))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(ConnectorRun)
                .where(*filters)
                .order_by(ConnectorRun.created_at.desc(), ConnectorRun.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total
