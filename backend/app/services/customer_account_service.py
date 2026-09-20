"""Unified customer master service.

Channel-specific records keep their own operational data while referencing one
workspace-scoped ``customer_accounts`` row. Customer numbers are deterministic
for legacy imports so repeated backfills remain idempotent.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import CustomerAccount
from app.services.customer_identity_service import resolve_canonical_account


def _profile_customer_number(customer_reference_id: str) -> str:
    digest = hashlib.sha256(customer_reference_id.encode("utf-8")).hexdigest()[:24]
    return f"B2C-{digest}"


def _agent_customer_number(agent_number: str) -> str:
    return f"B2B-{agent_number}"


async def _get_by_number(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_number: str,
) -> CustomerAccount | None:
    return (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.customer_number == customer_number,
            )
        )
    ).scalar_one_or_none()


async def _create_if_missing(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_number: str,
    customer_type: str,
    business_model: str,
    display_name: str | None,
    country: str | None,
    default_currency: str,
    trace_id: str | None,
) -> CustomerAccount:
    existing = await _get_by_number(
        session, workspace_id=workspace_id, customer_number=customer_number
    )
    if existing is not None:
        return await resolve_canonical_account(
            session,
            workspace_id=workspace_id,
            account=existing,
        )

    account = CustomerAccount(
        workspace_id=workspace_id,
        customer_number=customer_number,
        customer_type=customer_type,
        business_model=business_model,
        display_name=display_name,
        status="active",
        country=country,
        default_currency=default_currency,
        trace_id=trace_id,
    )
    try:
        async with session.begin_nested():
            session.add(account)
            await session.flush()
    except IntegrityError:
        existing = await _get_by_number(
            session, workspace_id=workspace_id, customer_number=customer_number
        )
        if existing is None:
            raise
        return existing
    return account


async def get_or_create_b2c_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    customer_reference_id: str,
    country: str | None = None,
    default_currency: str = "USD",
    trace_id: str | None = None,
) -> CustomerAccount:
    """Return the unified account for a non-PII B2C profile reference."""
    return await _create_if_missing(
        session,
        workspace_id=workspace_id,
        customer_number=_profile_customer_number(customer_reference_id),
        customer_type="CONSUMER",
        business_model="B2C",
        display_name=None,
        country=country,
        default_currency=default_currency,
        trace_id=trace_id,
    )


async def get_or_create_b2b_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    agent_number: str,
    company_name: str,
    country: str | None = None,
    default_currency: str = "USD",
    trace_id: str | None = None,
) -> CustomerAccount:
    """Return the unified account for a B2B agent."""
    return await _create_if_missing(
        session,
        workspace_id=workspace_id,
        customer_number=_agent_customer_number(agent_number),
        customer_type="WHOLESALER",
        business_model="B2B",
        display_name=company_name,
        country=country,
        default_currency=default_currency,
        trace_id=trace_id,
    )


async def get_account(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    account_id: UUID,
) -> CustomerAccount | None:
    account = (
        await session.execute(
            select(CustomerAccount).where(
                CustomerAccount.workspace_id == workspace_id,
                CustomerAccount.id == account_id,
            )
        )
    ).scalar_one_or_none()
    if account is None:
        return None
    return await resolve_canonical_account(
        session,
        workspace_id=workspace_id,
        account=account,
    )
