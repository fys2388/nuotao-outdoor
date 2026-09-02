"""M5.14 identity mapping - real PostgreSQL integration.

Proves migration 0023 (``workspace_identity_links``) applies on real
PostgreSQL, the mapping service resolves org -> workspace, disabled links are
ignored and the (workspace_id, organization_id) uniqueness holds.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.workspace_identity import (
    link_workspace_identity,
    resolve_workspace_from_identity,
)

WS_A = UUID("00000000-0000-0000-0000-00000000aa01")
WS_B = UUID("00000000-0000-0000-0000-00000000aa02")


@pytest.mark.asyncio
async def test_workspace_identity_links_migration_and_service(pg_migrated: str) -> None:
    """The 0023 table exists and the mapping service works on real PG."""
    engine = create_async_engine(pg_migrated)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            exists = await conn.scalar(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='workspace_identity_links'"
                )
            )
            assert exists == 1

        async with factory() as session:
            link = await link_workspace_identity(
                session,
                workspace_id=WS_A,
                organization_id="org_a",
                role="operator",
                mapping_metadata={"source": "staging"},
                trace_id="test-identity-pg",
            )
            await session.commit()
            assert link.workspace_id == WS_A
            assert link.organization_id == "org_a"

        async with factory() as session:
            assert await resolve_workspace_from_identity(session, organization_id="org_a") == WS_A
            assert (
                await resolve_workspace_from_identity(session, organization_id="org_missing")
                is None
            )
            # Disabled links are never resolved.
            await link_workspace_identity(
                session, workspace_id=WS_A, organization_id="org_a", enabled=False
            )
            await session.commit()
            assert await resolve_workspace_from_identity(session, organization_id="org_a") is None
            # Re-enable for the uniqueness drill below.
            await link_workspace_identity(
                session, workspace_id=WS_A, organization_id="org_a", enabled=True
            )
            await session.commit()

        # (workspace_id, organization_id) must stay unique.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO workspace_identity_links "
                    "(id, workspace_id, organization_id, enabled) "
                    "VALUES (:id, :ws, 'org_a', true)"
                ),
                {
                    "id": UUID("00000000-0000-0000-0000-00000000aa03"),
                    "ws": WS_A,
                },
            )
            raise AssertionError("duplicate (workspace, org) should violate the unique index")
    except IntegrityError:
        pass
    finally:
        await engine.dispose()
