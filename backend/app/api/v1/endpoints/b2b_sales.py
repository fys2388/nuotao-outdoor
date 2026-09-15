"""Internal APIs for the B2B RFQ, quote, contract, and order chain."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import (
    get_current_user,
    get_current_workspace_id,
    require_role,
)
from app.core.database import get_db
from app.core.tracing import get_trace_id
from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_sales import B2BContract, B2BQuote, B2BRFQ
from app.schemas.b2b_sales import (
    B2BContractCreate,
    B2BContractListResponse,
    B2BContractResponse,
    B2BContractSignRequest,
    B2BContractStatusUpdate,
    B2BContractSummary,
    B2BOrderConversionResponse,
    B2BQuoteCreate,
    B2BQuoteItemResponse,
    B2BQuoteListResponse,
    B2BQuoteResponse,
    B2BQuoteStatusUpdate,
    B2BQuoteVersionCreate,
    B2BRFQCreate,
    B2BRFQItemResponse,
    B2BRFQListResponse,
    B2BRFQResponse,
    B2BRFQStatusUpdate,
)
from app.schemas.user import UserResponse
from app.services import b2b_credit_service, b2b_sales_service

router = APIRouter(prefix="/admin/b2b", tags=["admin-b2b-sales"])
WorkspaceId = UUID
SalesOperator = Annotated[UserResponse, Depends(require_role("operator"))]


def _actor(user: UserResponse) -> str:
    return user.email or user.username


def _sales_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, b2b_credit_service.B2BCreditError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, b2b_sales_service.B2BSalesStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        message = str(exc)
        status_code = 404 if message.endswith("not found") else 422
        return HTTPException(status_code=status_code, detail=message)
    return HTTPException(status_code=500, detail="B2B sales operation failed")


async def _agent_map(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    agent_ids: set[UUID],
) -> dict[UUID, B2BAgent]:
    if not agent_ids:
        return {}
    rows = (
        await db.execute(
            select(B2BAgent).where(
                B2BAgent.workspace_id == workspace_id,
                B2BAgent.id.in_(agent_ids),
            )
        )
    ).scalars().all()
    return {agent.id: agent for agent in rows}


def _rfq_response(rfq: B2BRFQ, agent: B2BAgent | None = None) -> B2BRFQResponse:
    return B2BRFQResponse(
        id=str(rfq.id),
        rfq_number=rfq.rfq_number,
        agent_id=str(rfq.agent_id),
        agent_company=agent.company_name if agent else "",
        customer_account_id=(
            str(rfq.customer_account_id) if rfq.customer_account_id else None
        ),
        status=rfq.status,
        source=rfq.source,
        requested_currency=rfq.requested_currency,
        destination_country=rfq.destination_country,
        incoterm=rfq.incoterm,
        requested_delivery_date=rfq.requested_delivery_date,
        notes=rfq.notes,
        created_by=rfq.created_by,
        assigned_to=rfq.assigned_to,
        submitted_at=rfq.submitted_at,
        closed_at=rfq.closed_at,
        items=[
            B2BRFQItemResponse(
                id=str(item.id),
                product_id=str(item.product_id),
                sku_snapshot=item.sku_snapshot,
                product_name_snapshot=item.product_name_snapshot,
                requested_quantity=item.requested_quantity,
                target_unit_price=item.target_unit_price,
                specifications=item.specifications or {},
                notes=item.notes,
            )
            for item in rfq.items
        ],
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
    )


def _quote_item_response(item) -> B2BQuoteItemResponse:
    return B2BQuoteItemResponse(
        id=str(item.id),
        product_id=str(item.product_id),
        sku_snapshot=item.sku_snapshot,
        product_name_snapshot=item.product_name_snapshot,
        quantity=item.quantity,
        unit_price=item.unit_price,
        discount_percent=item.discount_percent,
        line_subtotal=item.line_subtotal,
        line_total=item.line_total,
        price_tier_id=str(item.price_tier_id) if item.price_tier_id else None,
        price_source=item.price_source,
        cost_snapshot=item.cost_snapshot or {},
        specifications=item.specifications or {},
    )


def _quote_response(quote: B2BQuote, agent: B2BAgent | None = None) -> B2BQuoteResponse:
    contract = quote.contract
    return B2BQuoteResponse(
        id=str(quote.id),
        quote_number=quote.quote_number,
        version_number=quote.version_number,
        rfq_id=str(quote.rfq_id) if quote.rfq_id else None,
        rfq_number=quote.rfq.rfq_number if quote.rfq else None,
        agent_id=str(quote.agent_id),
        agent_company=agent.company_name if agent else "",
        customer_account_id=(
            str(quote.customer_account_id) if quote.customer_account_id else None
        ),
        status=quote.status,
        currency=quote.currency,
        base_currency=quote.base_currency,
        exchange_rate_to_base=quote.exchange_rate_to_base,
        price_book_version_id=(
            str(quote.price_book_version_id) if quote.price_book_version_id else None
        ),
        valid_until=quote.valid_until,
        payment_terms_days=quote.payment_terms_days,
        incoterm=quote.incoterm,
        shipping_terms=quote.shipping_terms,
        subtotal=quote.subtotal,
        discount_amount=quote.discount_amount,
        shipping_cost=quote.shipping_cost,
        tax_amount=quote.tax_amount,
        total=quote.total,
        created_by=quote.created_by,
        approved_by=quote.approved_by,
        approved_at=quote.approved_at,
        sent_at=quote.sent_at,
        accepted_at=quote.accepted_at,
        rejected_at=quote.rejected_at,
        rejection_reason=quote.rejection_reason,
        notes=quote.notes,
        items=[_quote_item_response(item) for item in quote.items],
        contract=(
            B2BContractSummary(
                id=str(contract.id),
                contract_number=contract.contract_number,
                status=contract.status,
                customer_signed_at=contract.customer_signed_at,
                company_signed_at=contract.company_signed_at,
                activated_at=contract.activated_at,
            )
            if contract
            else None
        ),
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def _contract_response(
    contract: B2BContract,
    agent: B2BAgent | None = None,
) -> B2BContractResponse:
    quote = contract.quote
    return B2BContractResponse(
        id=str(contract.id),
        contract_number=contract.contract_number,
        quote_id=str(contract.quote_id),
        quote_number=quote.quote_number if quote else None,
        version_number=quote.version_number if quote else None,
        agent_id=str(contract.agent_id),
        agent_company=agent.company_name if agent else "",
        customer_account_id=(
            str(contract.customer_account_id) if contract.customer_account_id else None
        ),
        status=contract.status,
        effective_from=contract.effective_from,
        effective_to=contract.effective_to,
        currency=contract.currency,
        total=contract.total,
        document_url=contract.document_url,
        terms=contract.terms or {},
        created_by=contract.created_by,
        customer_signed_by=contract.customer_signed_by,
        customer_signed_at=contract.customer_signed_at,
        company_signed_by=contract.company_signed_by,
        company_signed_at=contract.company_signed_at,
        activated_at=contract.activated_at,
        terminated_at=contract.terminated_at,
        items=[_quote_item_response(item) for item in quote.items] if quote else [],
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


@router.get("/rfqs", response_model=B2BRFQListResponse)
async def list_rfqs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRFQListResponse:
    rfqs, total = await b2b_sales_service.list_rfqs(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
        agent_id=agent_id,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={rfq.agent_id for rfq in rfqs},
    )
    return B2BRFQListResponse(
        items=[_rfq_response(rfq, agents.get(rfq.agent_id)) for rfq in rfqs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/rfqs", response_model=B2BRFQResponse, status_code=201)
async def create_rfq(
    req: B2BRFQCreate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRFQResponse:
    try:
        rfq = await b2b_sales_service.create_rfq(
            db,
            workspace_id=workspace_id,
            agent_id=req.agent_id,
            items=[item.model_dump() for item in req.items],
            created_by=_actor(user),
            source=req.source,
            requested_currency=req.requested_currency,
            destination_country=req.destination_country,
            incoterm=req.incoterm,
            requested_delivery_date=req.requested_delivery_date,
            notes=req.notes,
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _rfq_response(rfq)


@router.get("/rfqs/{rfq_id}", response_model=B2BRFQResponse)
async def get_rfq(
    rfq_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRFQResponse:
    rfq = await b2b_sales_service.get_rfq(
        db,
        workspace_id=workspace_id,
        rfq_id=rfq_id,
    )
    if rfq is None:
        raise HTTPException(status_code=404, detail="RFQ not found")
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={rfq.agent_id},
    )
    return _rfq_response(rfq, agents.get(rfq.agent_id))


@router.patch("/rfqs/{rfq_id}/status", response_model=B2BRFQResponse)
async def update_rfq_status(
    rfq_id: str,
    req: B2BRFQStatusUpdate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BRFQResponse:
    try:
        rfq = await b2b_sales_service.update_rfq_status(
            db,
            workspace_id=workspace_id,
            rfq_id=rfq_id,
            new_status=req.status,
            actor=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={rfq.agent_id},
    )
    return _rfq_response(rfq, agents.get(rfq.agent_id))


@router.post(
    "/rfqs/{rfq_id}/quotes",
    response_model=B2BQuoteResponse,
    status_code=201,
)
async def create_quote_from_rfq(
    rfq_id: str,
    req: B2BQuoteCreate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BQuoteResponse:
    try:
        quote = await b2b_sales_service.create_quote_from_rfq(
            db,
            workspace_id=workspace_id,
            rfq_id=rfq_id,
            created_by=_actor(user),
            valid_until=req.valid_until,
            payment_terms_days=req.payment_terms_days,
            exchange_rate_to_base=req.exchange_rate_to_base,
            base_currency=req.base_currency,
            shipping_cost=req.shipping_cost,
            tax_amount=req.tax_amount,
            shipping_terms=req.shipping_terms,
            notes=req.notes,
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _quote_response(quote)


@router.get("/quotes", response_model=B2BQuoteListResponse)
async def list_quotes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    agent_id: str | None = None,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BQuoteListResponse:
    quotes, total = await b2b_sales_service.list_quotes(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
        agent_id=agent_id,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={quote.agent_id for quote in quotes},
    )
    return B2BQuoteListResponse(
        items=[_quote_response(quote, agents.get(quote.agent_id)) for quote in quotes],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/quotes/{quote_id}", response_model=B2BQuoteResponse)
async def get_quote(
    quote_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BQuoteResponse:
    quote = await b2b_sales_service.get_quote(
        db,
        workspace_id=workspace_id,
        quote_id=quote_id,
    )
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={quote.agent_id},
    )
    return _quote_response(quote, agents.get(quote.agent_id))


@router.post(
    "/quotes/{quote_id}/versions",
    response_model=B2BQuoteResponse,
    status_code=201,
)
async def create_quote_version(
    quote_id: str,
    req: B2BQuoteVersionCreate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BQuoteResponse:
    try:
        quote = await b2b_sales_service.create_quote_version(
            db,
            workspace_id=workspace_id,
            quote_id=quote_id,
            created_by=_actor(user),
            valid_until=req.valid_until,
            notes=req.notes,
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _quote_response(quote)


@router.patch("/quotes/{quote_id}/status", response_model=B2BQuoteResponse)
async def update_quote_status(
    quote_id: str,
    req: B2BQuoteStatusUpdate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BQuoteResponse:
    try:
        quote = await b2b_sales_service.transition_quote(
            db,
            workspace_id=workspace_id,
            quote_id=quote_id,
            new_status=req.status,
            actor=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _quote_response(quote)


@router.post(
    "/quotes/{quote_id}/contracts",
    response_model=B2BContractResponse,
    status_code=201,
)
async def create_contract_from_quote(
    quote_id: str,
    req: B2BContractCreate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BContractResponse:
    try:
        contract = await b2b_sales_service.create_contract_from_quote(
            db,
            workspace_id=workspace_id,
            quote_id=quote_id,
            created_by=_actor(user),
            effective_from=req.effective_from,
            effective_to=req.effective_to,
            document_url=req.document_url,
            terms=req.terms,
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _contract_response(contract)


@router.post(
    "/quotes/{quote_id}/convert-to-order",
    response_model=B2BOrderConversionResponse,
    status_code=201,
)
async def convert_quote_to_order(
    quote_id: str,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BOrderConversionResponse:
    try:
        order: B2BOrder = await b2b_sales_service.convert_quote_to_order(
            db,
            workspace_id=workspace_id,
            quote_id=quote_id,
            actor=_actor(user),
            trace_id=get_trace_id(),
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return B2BOrderConversionResponse(
        id=str(order.id),
        order_number=order.order_number,
        quote_id=str(order.quote_id),
        contract_id=str(order.contract_id),
        status=order.status,
        payment_status=order.payment_status,
        total=order.total,
        currency=order.currency,
    )


@router.get("/contracts", response_model=B2BContractListResponse)
async def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(default=None, max_length=24),
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BContractListResponse:
    contracts, total = await b2b_sales_service.list_contracts(
        db,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        status=status,
    )
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={contract.agent_id for contract in contracts},
    )
    return B2BContractListResponse(
        items=[
            _contract_response(contract, agents.get(contract.agent_id))
            for contract in contracts
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/contracts/{contract_id}", response_model=B2BContractResponse)
async def get_contract(
    contract_id: str,
    _user: UserResponse = Depends(get_current_user),
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BContractResponse:
    contract = await b2b_sales_service.get_contract(
        db,
        workspace_id=workspace_id,
        contract_id=contract_id,
    )
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    agents = await _agent_map(
        db,
        workspace_id=workspace_id,
        agent_ids={contract.agent_id},
    )
    return _contract_response(contract, agents.get(contract.agent_id))


@router.patch("/contracts/{contract_id}/status", response_model=B2BContractResponse)
async def update_contract_status(
    contract_id: str,
    req: B2BContractStatusUpdate,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BContractResponse:
    try:
        contract = await b2b_sales_service.transition_contract(
            db,
            workspace_id=workspace_id,
            contract_id=contract_id,
            new_status=req.status,
            actor=_actor(user),
            reason=req.reason,
            trace_id=get_trace_id(),
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _contract_response(contract)


@router.post("/contracts/{contract_id}/sign", response_model=B2BContractResponse)
async def sign_contract(
    contract_id: str,
    req: B2BContractSignRequest,
    user: SalesOperator,
    workspace_id: WorkspaceId = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
) -> B2BContractResponse:
    try:
        contract = await b2b_sales_service.sign_contract(
            db,
            workspace_id=workspace_id,
            contract_id=contract_id,
            party=req.party,
            signed_by=req.signed_by,
            trace_id=get_trace_id(),
        )
    except ValueError as exc:
        raise _sales_http_error(exc) from exc
    return _contract_response(contract)
