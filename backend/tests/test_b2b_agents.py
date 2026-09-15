"""P2 regression tests for B2B advisory agents."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.agents import b2b_agent_seed, b2b_agents
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.agent_runtime import AgentRegistry, AgentTask
from app.models.agent_suggestion import AgentSuggestion
from app.models.b2b import B2BAgent, B2BOrder
from app.models.b2b_sales import B2BQuote
from app.models.event import EventLog
from app.models.product import Product, ProductCost
from app.services import (
    agent_suggestion_service,
    b2b_finance_service,
    b2b_pricing_service,
    b2b_sales_service,
    execution_router,
)

WORKSPACE = DEFAULT_WORKSPACE_ID


async def _create_product(
    db_session,
    *,
    sku: str = "TENT-B2B-001",
    landed_cost: Decimal = Decimal("10.00"),
) -> Product:
    product = Product(
        workspace_id=WORKSPACE,
        sku=sku,
        name=f"Product {sku}",
        status="active",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductCost(
            workspace_id=WORKSPACE,
            product_id=product.id,
            currency="USD",
            purchase_cost=landed_cost,
            total_landed_cost=landed_cost,
            total_cost=landed_cost,
            version="v1",
        )
    )
    await db_session.commit()
    return product


async def _create_b2b_customer(
    db_session,
    *,
    number: str = "AG-P2-001",
    tier: str = "bronze",
    credit_limit: Decimal = Decimal("10000.00"),
) -> B2BAgent:
    customer = B2BAgent(
        workspace_id=WORKSPACE,
        agent_number=number,
        company_name=f"Company {number}",
        contact_name="B2B Buyer",
        email=f"{number.lower()}@example.com",
        hashed_password="not-used",
        tier=tier,
        status="active",
        currency="USD",
        credit_limit=credit_limit,
        current_balance=Decimal("0"),
    )
    db_session.add(customer)
    await db_session.commit()
    return customer


async def _create_rfq(
    db_session,
    *,
    customer: B2BAgent,
    product: Product,
    quantity: int = 100,
    target_price: Decimal = Decimal("22.00"),
):
    rfq = await b2b_sales_service.create_rfq(
        db_session,
        workspace_id=WORKSPACE,
        agent_id=customer.id,
        items=[
            {
                "product_id": str(product.id),
                "quantity": quantity,
                "target_unit_price": target_price,
            }
        ],
        created_by="sales@example.com",
    )
    await b2b_sales_service.update_rfq_status(
        db_session,
        workspace_id=WORKSPACE,
        rfq_id=rfq.id,
        new_status="submitted",
        actor="sales@example.com",
    )
    await db_session.commit()
    return await b2b_sales_service.get_rfq(
        db_session,
        workspace_id=WORKSPACE,
        rfq_id=rfq.id,
    )


async def _publish_bronze_price(
    db_session,
    *,
    product: Product,
    unit_price: Decimal = Decimal("25.00"),
) -> None:
    book = await b2b_pricing_service.create_price_book(
        db_session,
        workspace_id=WORKSPACE,
        code="P2-DEFAULT",
        name="P2 Default",
        currency="USD",
        created_by="pricing@example.com",
        is_default=True,
    )
    version = await b2b_pricing_service.create_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_book_id=book.id,
        created_by="pricing@example.com",
        effective_from=date.today(),
    )
    await b2b_pricing_service.create_price_tier(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        product_id=product.id,
        tier="bronze",
        agent_id=None,
        min_quantity=1,
        max_quantity=None,
        unit_price=unit_price,
        currency="USD",
    )
    await b2b_pricing_service.submit_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        actor="pricing@example.com",
    )
    await b2b_pricing_service.approve_price_version(
        db_session,
        workspace_id=WORKSPACE,
        price_version_id=version.id,
        actor="controller@example.com",
    )


@pytest.mark.asyncio
async def test_b2b_agent_seed_is_idempotent_and_scoped(db_session) -> None:
    first = await b2b_agent_seed.ensure_b2b_agents(
        db_session,
        workspace_id=WORKSPACE,
    )
    await db_session.commit()
    first_ids = {agent.agent_id: agent.id for agent in first}
    first_scopes = {agent.agent_id: agent.business_scope for agent in first}
    first_levels = {agent.agent_id: agent.permission_level for agent in first}
    second = await b2b_agent_seed.ensure_b2b_agents(
        db_session,
        workspace_id=WORKSPACE,
    )
    second_ids = {agent.agent_id: agent.id for agent in second}
    await db_session.commit()

    assert set(first_ids) == {
        "b2b_sales_agent",
        "b2b_quotation_agent",
        "b2b_collection_agent",
    }
    assert first_ids == second_ids
    assert set(first_scopes.values()) == {"B2B"}
    assert set(first_levels.values()) == {"L2"}


@pytest.mark.asyncio
async def test_b2b_bootstrap_api_is_idempotent_and_audited(api_client, db_session) -> None:
    first = api_client.post(
        "/api/v1/agent-registry/b2b/bootstrap",
        json={"actor": "admin"},
    )
    assert first.status_code == 200
    first_rows = first.json()
    assert len(first_rows) == 3
    assert {row["business_scope"] for row in first_rows} == {"B2B"}
    assert {row["permission_level"] for row in first_rows} == {"L2"}

    second = api_client.post(
        "/api/v1/agent-registry/b2b/bootstrap",
        json={"actor": "admin"},
    )
    assert second.status_code == 200
    assert {row["id"] for row in second.json()} == {row["id"] for row in first_rows}

    events = (
        (
            await db_session.execute(
                select(EventLog).where(
                    EventLog.workspace_id == WORKSPACE,
                    EventLog.event_type == "agent.b2b_bootstrap.completed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 2
    assert all(event.payload["actor"] == "admin" for event in events)


@pytest.mark.asyncio
async def test_sales_agent_prioritizes_stale_rfq(db_session) -> None:
    customer = await _create_b2b_customer(db_session)
    product = await _create_product(db_session)
    rfq = await _create_rfq(db_session, customer=customer, product=product)
    rfq.submitted_at = datetime.now(timezone.utc) - timedelta(days=8)
    await db_session.commit()

    result = await b2b_agents.analyze_sales_pipeline(
        db_session,
        workspace_id=WORKSPACE,
        task_input={"as_of": date.today().isoformat(), "stale_days": 3},
    )

    assert result["summary"]["active_rfq_count"] == 1
    assert result["summary"]["action_required_count"] == 1
    assert result["opportunities"][0]["rfq_id"] == str(rfq.id)
    assert result["opportunities"][0]["recommended_action"] == "assign_and_qualify"
    assert result["opportunities"][0]["age_days"] == 8
    assert result["write_actions_performed"] == []


@pytest.mark.asyncio
async def test_quotation_agent_uses_published_price_and_cost(db_session) -> None:
    customer = await _create_b2b_customer(db_session)
    product = await _create_product(db_session)
    await _publish_bronze_price(db_session, product=product)
    rfq = await _create_rfq(
        db_session,
        customer=customer,
        product=product,
        quantity=100,
        target_price=Decimal("22.00"),
    )

    result = await b2b_agents.recommend_quote(
        db_session,
        workspace_id=WORKSPACE,
        task_input={
            "rfq_id": str(rfq.id),
            "target_margin_percent": "20",
            "valid_days": 14,
        },
    )

    assert result["recommended_action"] == "proceed_to_quote"
    assert result["summary"]["published_revenue"] == "2500.00"
    assert result["summary"]["landed_cost"] == "1000.00"
    assert result["summary"]["overall_margin_percent"] == "60.00"
    assert result["summary"]["target_gap"] == "-300.00"
    assert result["lines"][0]["price_source"] == "TIER"
    assert result["write_actions_performed"] == []
    assert await db_session.scalar(select(func.count(B2BQuote.id))) == 0


@pytest.mark.asyncio
async def test_collection_agent_prioritizes_overdue_receivable(db_session) -> None:
    customer = await _create_b2b_customer(
        db_session,
        credit_limit=Decimal("50.00"),
    )
    order = B2BOrder(
        workspace_id=WORKSPACE,
        order_number="B2B-P2-ORDER",
        agent_id=customer.id,
        business_model="B2B",
        status="delivered",
        payment_status="unpaid",
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        total=Decimal("100.00"),
        currency="USD",
        shipping_address={},
        payment_due_date=date.today() - timedelta(days=40),
    )
    db_session.add(order)
    await db_session.commit()
    invoice = await b2b_finance_service.create_invoice_from_order(
        db_session,
        workspace_id=WORKSPACE,
        order_id=order.id,
        created_by="finance@example.com",
        issue_date=date.today() - timedelta(days=60),
        due_date=date.today() - timedelta(days=40),
    )
    await b2b_finance_service.issue_invoice(
        db_session,
        workspace_id=WORKSPACE,
        invoice_id=invoice.id,
        actor="finance@example.com",
    )

    result = await b2b_agents.analyze_collections(
        db_session,
        workspace_id=WORKSPACE,
        task_input={"as_of": date.today().isoformat(), "overdue_only": True},
    )

    assert result["summary"]["overdue_invoice_count"] == 1
    assert result["summary"]["overdue_amount"] == "100.00"
    assert result["priorities"][0]["aging_bucket"] == "31-60"
    assert result["priorities"][0]["recommended_action"] == "sales_escalation"
    assert "CREDIT_LIMIT_EXCEEDED" in result["priorities"][0]["risk_flags"]
    assert result["write_actions_performed"] == []


@pytest.mark.asyncio
async def test_b2b_executor_rejects_non_b2b_agent_and_returns_advisory(db_session) -> None:
    from app.worker.b2b_agent_executor import (
        B2BAgentExecutionError,
        b2b_agent_executor,
    )

    customer = await _create_b2b_customer(db_session)
    product = await _create_product(db_session)
    await _publish_bronze_price(db_session, product=product)
    rfq = await _create_rfq(db_session, customer=customer, product=product)
    agent = (
        await db_session.execute(
            select(AgentRegistry).where(
                AgentRegistry.workspace_id == WORKSPACE,
                AgentRegistry.agent_id == "b2b_quotation_agent",
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        seeded = await b2b_agent_seed.ensure_b2b_agents(
            db_session,
            workspace_id=WORKSPACE,
        )
        await db_session.commit()
        agent = next(item for item in seeded if item.agent_id == "b2b_quotation_agent")

    task = AgentTask(
        workspace_id=WORKSPACE,
        agent_id=agent.id,
        input={"rfq_id": str(rfq.id), "target_margin_percent": "20"},
        status="running",
        business_scope="B2B",
    )
    db_session.add(task)
    await db_session.commit()

    result = await b2b_agent_executor(
        db_session,
        workspace_id=WORKSPACE,
        agent=agent,
        task=task,
        policy=SimpleNamespace(),
    )
    assert result.provider == "internal-rules"
    assert result.cost == Decimal("0")
    assert result.output["analysis_type"] == "b2b_quote_recommendation"
    assert len(result.output["advisory_suggestion_ids"]) == 1

    suggestion = (
        await db_session.execute(
            select(AgentSuggestion).where(
                AgentSuggestion.workspace_id == WORKSPACE,
                AgentSuggestion.id == result.output["advisory_suggestion_ids"][0],
            )
        )
    ).scalar_one()
    assert suggestion.source == "b2b_agent"
    assert suggestion.status == "pending_approval"
    assert suggestion.execution_action == "manual_review"
    assert suggestion.execution_params["advisory_only"] is True
    assert suggestion.execution_params["evidence"]["rfq_id"] == str(rfq.id)

    second = await b2b_agent_executor(
        db_session,
        workspace_id=WORKSPACE,
        agent=agent,
        task=task,
        policy=SimpleNamespace(),
    )
    assert second.output["advisory_suggestion_ids"] == []
    assert (
        await db_session.scalar(
            select(func.count(AgentSuggestion.id)).where(
                AgentSuggestion.workspace_id == WORKSPACE,
                AgentSuggestion.agent_id == "b2b_quotation_agent",
            )
        )
    ) == 1

    await agent_suggestion_service.approve_suggestion(
        db_session,
        suggestion.id,
        approved_by="sales-manager",
        auto_execute=False,
    )
    execution = await execution_router.execute_suggestion(db_session, suggestion)
    assert execution["success"] is True
    assert execution["result"]["business_write_performed"] is False
    assert await db_session.scalar(select(func.count(B2BQuote.id))) == 0

    blocked_agent = AgentRegistry(
        workspace_id=uuid4(),
        agent_id="shared_agent",
        name="Shared Agent",
        domain="operations",
        version="v1",
        status="active",
        model_provider="openai",
        model_name="gpt-4o-mini",
        prompt_version="v1",
        permission_level="L2",
        business_scope="SHARED",
    )
    with pytest.raises(B2BAgentExecutionError, match="not allowed"):
        await b2b_agent_executor(
            db_session,
            workspace_id=WORKSPACE,
            agent=blocked_agent,
            task=task,
            policy=SimpleNamespace(),
        )
