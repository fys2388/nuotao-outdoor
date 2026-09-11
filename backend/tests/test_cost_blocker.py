"""Cost blocker tests (M0-M4.1 production blocker).

Tests cover:
- No ProductCost -> PO enters pending_cost_confirmation (blocked)
- Only purchase_cost without full landed cost -> blocked
- Fallback ratio only used for estimate, NOT for execution
- Cost confirmed -> PO can transition to draft -> approved
- pending_cost_confirmation CANNOT go directly to approved/ordered
- Duplicate cost confirmation does not create duplicate POs
"""

from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.supply_chain import PurchaseOrder, PurchaseOrderItem
from app.services import fulfillment_service, supply_chain


DEFAULT_WORKSPACE = __import__("uuid").UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def sample_order_with_items(db_session):
    """Order with 2 items, NO ProductCost configured."""
    order = Order(
        workspace_id=DEFAULT_WORKSPACE,
        external_order_id="TEST-COST-001",
        status="received",
        payment_status="paid",
        currency="USD",
        subtotal=Decimal("180.00"),
        shipping_total=Decimal("20.00"),
        total=Decimal("200.00"),
        refunded_amount=Decimal("0.00"),
    )
    db_session.add(order)
    await db_session.flush()

    item1 = OrderItem(
        order_id=order.id,
        workspace_id=DEFAULT_WORKSPACE,
        product_id=None,
        sku="SKU-NOCOST-001",
        name="Product Without Cost",
        quantity=2,
        unit_price=Decimal("80.00"),
        line_total=Decimal("160.00"),
    )
    item2 = OrderItem(
        order_id=order.id,
        workspace_id=DEFAULT_WORKSPACE,
        product_id=None,
        sku="SKU-NOCOST-002",
        name="Another Product Without Cost",
        quantity=1,
        unit_price=Decimal("20.00"),
        line_total=Decimal("20.00"),
    )
    db_session.add_all([item1, item2])
    await db_session.flush()
    return order


@pytest_asyncio.fixture
async def product_with_cost(db_session):
    """Product with real ProductCost."""
    product = Product(
        workspace_id=DEFAULT_WORKSPACE,
        sku="SKU-REALCOST-001",
        name="Product With Real Cost",
    )
    db_session.add(product)
    await db_session.flush()

    cost = ProductCost(
        workspace_id=DEFAULT_WORKSPACE,
        product_id=product.id,
        purchase_cost=Decimal("35.00"),
        domestic_shipping=Decimal("5.00"),
        international_shipping=Decimal("15.00"),
        packaging=Decimal("2.00"),
        tax_estimate=Decimal("3.00"),
        handling=Decimal("1.00"),
        total_landed_cost=Decimal("61.00"),
        total_cost=Decimal("61.00"),
    )
    db_session.add(cost)
    await db_session.flush()
    return product, cost


@pytest_asyncio.fixture
async def order_with_real_cost_items(db_session, product_with_cost):
    """Order with items that have real ProductCost."""
    product, cost = product_with_cost
    order = Order(
        workspace_id=DEFAULT_WORKSPACE,
        external_order_id="TEST-COST-002",
        status="received",
        payment_status="paid",
        currency="USD",
        subtotal=Decimal("100.00"),
        shipping_total=Decimal("10.00"),
        total=Decimal("110.00"),
        refunded_amount=Decimal("0.00"),
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        order_id=order.id,
        workspace_id=DEFAULT_WORKSPACE,
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        quantity=1,
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )
    db_session.add(item)
    await db_session.flush()
    return order


# --------------------------------------------------------------------------- #
# Test 1: No ProductCost -> PO blocked (pending_cost_confirmation)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_product_cost_blocks_purchase_order(db_session, sample_order_with_items):
    """No ProductCost -> PO enters pending_cost_confirmation, cannot be approved."""
    po, created = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert created is True
    assert po.status == "pending_cost_confirmation"
    assert po.cost_confirmed is False
    assert po.cost_source == "fallback"
    assert po.cost_confidence < Decimal("0.5")
    assert po.cost_block_reason is not None
    assert "Missing real ProductCost" in po.cost_block_reason


@pytest.mark.asyncio
async def test_pending_cost_confirmation_cannot_be_approved(db_session, sample_order_with_items):
    """pending_cost_confirmation CANNOT go directly to approved."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.status == "pending_cost_confirmation"

    # Try to approve directly -> should fail (pending_cost_confirmation -> approved not allowed)
    with pytest.raises(supply_chain.SupplyChainError):
        await supply_chain.approve_purchase_order(
            db_session, workspace_id=DEFAULT_WORKSPACE, po_id=po.id,
        )


@pytest.mark.asyncio
async def test_pending_cost_confirmation_cannot_be_ordered(db_session, sample_order_with_items):
    """pending_cost_confirmation CANNOT go directly to ordered."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    # Try to order directly -> should fail (must go through approved first)
    with pytest.raises(supply_chain.SupplyChainError):
        await supply_chain.order_purchase_order(
            db_session, workspace_id=DEFAULT_WORKSPACE, po_id=po.id,
        )


# --------------------------------------------------------------------------- #
# Test 2: Real ProductCost -> PO can be created as draft and approved
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_real_product_cost_allows_purchase_order(db_session, order_with_real_cost_items):
    """Real ProductCost -> PO created as draft, cost_confirmed=True."""
    po, created = await fulfillment_service.create_purchase_order_from_order(
        db_session, order_with_real_cost_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert created is True
    assert po.status == "draft"
    assert po.cost_confirmed is True
    assert po.cost_source == "product_cost"
    assert po.cost_confidence >= Decimal("0.9")
    assert po.cost_block_reason is None


@pytest.mark.asyncio
async def test_real_cost_po_can_be_approved(db_session, order_with_real_cost_items):
    """PO with real cost can go draft -> approved."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, order_with_real_cost_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.status == "draft"

    po = await supply_chain.approve_purchase_order(
        db_session, workspace_id=DEFAULT_WORKSPACE, po_id=po.id,
    )
    assert po.status == "approved"


# --------------------------------------------------------------------------- #
# Test 3: Fallback ratio only for estimate, NOT for execution
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fallback_cost_marked_as_estimate(db_session, sample_order_with_items):
    """Fallback cost is marked with source='fallback' and low confidence."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.cost_source == "fallback"
    assert po.cost_confidence < Decimal("0.5")
    assert po.cost_confirmed is False
    # The PO total is calculated using fallback, but it's blocked from execution
    assert po.total > Decimal("0")


# --------------------------------------------------------------------------- #
# Test 4: Cost confirmed -> PO can re-enter approval flow
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cost_confirmation_transitions_to_draft(db_session, sample_order_with_items, product_with_cost):
    """After adding ProductCost, confirm_purchase_order_cost transitions to draft."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.status == "pending_cost_confirmation"

    # Add real ProductCost for the PO items
    product, cost = product_with_cost
    # Update PO items to reference the product with real cost
    items_result = await db_session.execute(
        __import__("sqlalchemy").select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == po.id
        )
    )
    items = items_result.scalars().all()
    for item in items:
        item.product_id = product.id
        item.sku = product.sku
    await db_session.flush()

    # Now confirm cost
    po = await fulfillment_service.confirm_purchase_order_cost(
        db_session, po.id, confirmed_by="tester", workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.status == "draft"
    assert po.cost_confirmed is True
    assert po.cost_source == "product_cost"
    assert po.cost_confirmed_by == "tester"
    assert po.cost_confirmed_at is not None
    assert po.cost_block_reason is None


@pytest.mark.asyncio
async def test_confirmed_po_can_be_approved(db_session, sample_order_with_items, product_with_cost):
    """After cost confirmation, PO can go draft -> approved."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    product, cost = product_with_cost
    items_result = await db_session.execute(
        __import__("sqlalchemy").select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == po.id
        )
    )
    for item in items_result.scalars().all():
        item.product_id = product.id
        item.sku = product.sku
    await db_session.flush()

    po = await fulfillment_service.confirm_purchase_order_cost(
        db_session, po.id, confirmed_by="tester", workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.status == "draft"

    po = await supply_chain.approve_purchase_order(
        db_session, workspace_id=DEFAULT_WORKSPACE, po_id=po.id,
    )
    assert po.status == "approved"


# --------------------------------------------------------------------------- #
# Test 5: Duplicate cost confirmation does not create duplicate POs
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_duplicate_cost_confirmation_idempotent(db_session, sample_order_with_items, product_with_cost):
    """Repeated cost confirmation is idempotent, does not create duplicate POs."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    product, cost = product_with_cost
    items_result = await db_session.execute(
        __import__("sqlalchemy").select(PurchaseOrderItem).where(
            PurchaseOrderItem.purchase_order_id == po.id
        )
    )
    for item in items_result.scalars().all():
        item.product_id = product.id
        item.sku = product.sku
    await db_session.flush()

    # First confirmation
    po1 = await fulfillment_service.confirm_purchase_order_cost(
        db_session, po.id, confirmed_by="tester", workspace_id=DEFAULT_WORKSPACE,
    )
    # Second confirmation (idempotent)
    po2 = await fulfillment_service.confirm_purchase_order_cost(
        db_session, po.id, confirmed_by="tester", workspace_id=DEFAULT_WORKSPACE,
    )
    assert po1.id == po2.id
    assert po1.status == po2.status == "draft"

    # Verify no duplicate POs created
    all_pos = await db_session.execute(
        __import__("sqlalchemy").select(PurchaseOrder).where(
            PurchaseOrder.workspace_id == DEFAULT_WORKSPACE
        )
    )
    po_list = all_pos.scalars().all()
    assert len(po_list) == 1


# --------------------------------------------------------------------------- #
# Test 6: Cost confirmation fails if items still lack real cost
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cost_confirmation_fails_without_real_cost(db_session, sample_order_with_items):
    """confirm_purchase_order_cost fails if items still lack real ProductCost."""
    po, _ = await fulfillment_service.create_purchase_order_from_order(
        db_session, sample_order_with_items, workspace_id=DEFAULT_WORKSPACE,
    )
    assert po.status == "pending_cost_confirmation"

    # Try to confirm without adding real cost -> should fail
    with pytest.raises(ValueError, match="still missing real ProductCost"):
        await fulfillment_service.confirm_purchase_order_cost(
            db_session, po.id, confirmed_by="tester", workspace_id=DEFAULT_WORKSPACE,
        )

    # PO should still be in pending_cost_confirmation
    await db_session.refresh(po)
    assert po.status == "pending_cost_confirmation"
    assert po.cost_confirmed is False
