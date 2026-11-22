"""M4.2.0-R3-Final financial-amount + audit-idempotency tests.

These tests read the DATABASE (purchase_order_items, purchase_orders) and the
event_log — not just function return values — to prove the cost-confirmation
closure is financially correct and fully auditable:

- Per-SKU amounts: unit_cost == real ProductCost, line_total correct,
  subtotal/shipping/total correct (multi-SKU, distinct costs).
- Currency guard: ProductCost.currency != PO.currency -> fail-closed, no
  cost_confirmed, amounts unchanged (no auto FX).
- product_id/SKU consistency: mismatched identifiers -> fail-closed.
- Idempotency: repeating confirmation emits exactly ONE cost-confirmed event.
- actor_role: order/cancel/receive/partial_receive + cost-confirm + create/update
  events all carry a non-null, DB-matching actor_role.

POs are built with ``supply_chain.create_purchase_order`` (items carry an
explicit product_id) and moved to ``pending_cost_confirmation`` so we exercise
``confirm_purchase_order_cost`` directly without routing through the
fulfilment auto-create path.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.event import EventLog
from app.models.product import Product, ProductCost
from app.models.supply_chain import PurchaseOrderItem
from app.models.user import User
from app.schemas.supply_chain import (
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    PurchaseOrderUpdate,
)
from app.services import supply_chain

WS = __import__("uuid").UUID("00000000-0000-0000-0000-000000000001")


async def _seed_admin(db_session) -> User:
    admin = User(
        id=uuid4(),
        username=f"admin-{uuid4().hex[:8]}",
        email=f"admin-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()
    return admin


async def _seed_operator(db_session) -> User:
    op = User(
        id=uuid4(),
        username=f"op-{uuid4().hex[:8]}",
        email=f"op-{uuid4().hex[:8]}@example.com",
        hashed_password="x",
        role="operator",
        is_active=True,
    )
    db_session.add(op)
    await db_session.flush()
    return op


async def _seed_products(db_session, specs: list[tuple[str, str, str]]):
    """Async-seed Product+ProductCost rows: specs of (sku, purchase_cost, currency)."""
    out = []
    for sku, purchase_cost, currency in specs:
        product = Product(workspace_id=WS, sku=sku, name=f"P {sku}")
        db_session.add(product)
        await db_session.flush()
        cost = ProductCost(
            workspace_id=WS,
            product_id=product.id,
            currency=currency,
            purchase_cost=Decimal(purchase_cost),
            domestic_shipping=Decimal("0"),
            total_landed_cost=Decimal(purchase_cost),
            total_cost=Decimal(purchase_cost),
        )
        db_session.add(cost)
        out.append((product, cost))
    await db_session.flush()
    return out


async def _mk_pending_po(db_session, *, po_number: str, items: list[tuple[str, str, int]]):
    """Build a PO via the canonical create (items carry product_id), then move it
    to pending_cost_confirmation. items = [(sku, product_id_str, qty)]."""
    data = PurchaseOrderCreate(
        po_number=po_number,
        currency="USD",
        shipping_cost=Decimal("0"),
        items=[
            PurchaseOrderItemCreate(
                product_id=pid,
                sku=sku,
                name=f"item {sku}",
                quantity=qty,
                unit_cost=Decimal("1.00"),
            )
            for sku, pid, qty in items
        ],
    )
    admin = await _seed_admin(db_session)
    po = await supply_chain.create_purchase_order(db_session, workspace_id=WS, data=data, actor_user_id=str(admin.id))
    # Cost confirmation is gated on this entry status; set it directly so the
    # test targets confirm_purchase_order_cost in isolation.
    po.status = "pending_cost_confirmation"
    await db_session.flush()
    await db_session.refresh(po)
    return po, admin


async def _po_items(db_session, po_id):
    res = await db_session.execute(select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po_id))
    return res.scalars().all()


async def _events(db_session, event_type: str, entity_id: str | None = None):
    stmt = select(EventLog).where(EventLog.event_type == event_type)
    if entity_id:
        stmt = stmt.where(EventLog.entity_id == entity_id)
    res = await db_session.execute(stmt)
    return res.scalars().all()


# --------------------------------------------------------------------------- #
# R3-F3.1 Multi-SKU precise financial amounts (read DB, not return value)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_multi_sku_amounts_recomputed_from_real_cost(db_session):
    """Two SKUs with distinct real costs -> per-SKU unit_cost/line_total and
    PO subtotal/total all recomputed exactly from ProductCost."""
    seeded = await _seed_products(db_session, [("SKU-A", "10.00", "USD"), ("SKU-B", "7.50", "USD")])
    pid_a = str(seeded[0][0].id)
    pid_b = str(seeded[1][0].id)
    po, admin = await _mk_pending_po(
        db_session,
        po_number=f"R3F3-MULTI-{uuid4().hex[:6]}",
        items=[("SKU-A", pid_a, 3), ("SKU-B", pid_b, 4)],
    )

    po = await supply_chain.confirm_purchase_order_cost(
        db_session,
        po.id,
        confirmed_by="tester",
        workspace_id=WS,
        confirmer_user_id=str(admin.id),
    )
    await db_session.refresh(po)

    items = {i.sku: i for i in await _po_items(db_session, po.id)}
    # unit_cost written back from the real ProductCost, per SKU
    assert items["SKU-A"].unit_cost == Decimal("10.00")
    assert items["SKU-B"].unit_cost == Decimal("7.50")
    # line_total = unit_cost * quantity, per SKU
    assert items["SKU-A"].line_total == Decimal("30.00")  # 10 * 3
    assert items["SKU-B"].line_total == Decimal("30.00")  # 7.5 * 4
    # subtotal = sum(line_total); total = subtotal + shipping(0)
    assert po.subtotal == Decimal("60.00")
    assert po.total == Decimal("60.00")
    assert po.cost_confirmed is True


# --------------------------------------------------------------------------- #
# R3-F3.2 Currency mismatch -> fail-closed, amounts unchanged
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_currency_mismatch_fails_closed(db_session):
    """ProductCost in CNY vs PO in USD -> confirmation rejected, no cost_confirmed,
    amounts and status untouched (no auto FX conversion)."""
    seeded = await _seed_products(db_session, [("SKU-CNY", "70.00", "CNY")])
    pid_cny = str(seeded[0][0].id)
    po, admin = await _mk_pending_po(
        db_session,
        po_number=f"R3F3-CNY-{uuid4().hex[:6]}",
        items=[("SKU-CNY", pid_cny, 2)],
    )
    assert po.currency == "USD"
    before_subtotal = po.subtotal
    before_total = po.total

    with pytest.raises(supply_chain.SupplyChainError, match="currency mismatch"):
        await supply_chain.confirm_purchase_order_cost(
            db_session,
            po.id,
            confirmed_by="tester",
            workspace_id=WS,
            confirmer_user_id=str(admin.id),
        )

    await db_session.refresh(po)
    assert po.status == "pending_cost_confirmation"
    assert po.cost_confirmed is False
    # amounts unchanged
    assert po.subtotal == before_subtotal
    assert po.total == before_total
    # no cost-confirmed event emitted
    events = await _events(db_session, "supply.purchase_order_cost_confirmed", str(po.id))
    assert len(events) == 0


# --------------------------------------------------------------------------- #
# R3-F3.3 product_id / SKU mismatch -> fail-closed
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_product_id_sku_mismatch_fails(db_session):
    """An item whose product_id and sku point at DIFFERENT products must not
    confirm — the SKU fallback must not silently pull another product's cost."""
    seeded = await _seed_products(db_session, [("SKU-A", "10.00", "USD"), ("SKU-B", "99.00", "USD")])
    pid_a = str(seeded[0][0].id)
    # product_id = product A, but sku = "SKU-B" -> identifiers conflict.
    po, admin = await _mk_pending_po(
        db_session,
        po_number=f"R3F3-MISMATCH-{uuid4().hex[:6]}",
        items=[("SKU-B", pid_a, 1)],
    )

    with pytest.raises(supply_chain.SupplyChainError):
        await supply_chain.confirm_purchase_order_cost(
            db_session,
            po.id,
            confirmed_by="tester",
            workspace_id=WS,
            confirmer_user_id=str(admin.id),
        )
    await db_session.refresh(po)
    assert po.cost_confirmed is False
    assert po.status == "pending_cost_confirmation"


# --------------------------------------------------------------------------- #
# R3-F3.4 Idempotency -> exactly ONE cost-confirmed event
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_duplicate_confirmation_emits_single_event(db_session):
    """Repeating cost confirmation emits exactly ONE cost-confirmed event."""
    seeded = await _seed_products(db_session, [("SKU-IDEM", "5.00", "USD")])
    pid = str(seeded[0][0].id)
    po, admin = await _mk_pending_po(
        db_session,
        po_number=f"R3F3-IDEM-{uuid4().hex[:6]}",
        items=[("SKU-IDEM", pid, 2)],
    )
    for _ in range(2):
        po = await supply_chain.confirm_purchase_order_cost(
            db_session,
            po.id,
            confirmed_by="tester",
            workspace_id=WS,
            confirmer_user_id=str(admin.id),
        )
    events = await _events(db_session, "supply.purchase_order_cost_confirmed", str(po.id))
    assert len(events) == 1


# --------------------------------------------------------------------------- #
# R3-F3.5 actor_role present + DB-matching on all procurement events
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_all_procurement_events_carry_actor_role(db_session):
    """order/receive/partial_receive + cost-confirm + create events all record a
    non-null actor_role that matches the seeded DB user's role."""
    operator = await _seed_operator(db_session)
    seeded = await _seed_products(db_session, [("SKU-ROLE", "4.00", "USD")])
    pid = str(seeded[0][0].id)
    po, admin = await _mk_pending_po(
        db_session,
        po_number=f"R3F3-ROLE-{uuid4().hex[:6]}",
        items=[("SKU-ROLE", pid, 1)],
    )
    # confirm cost (admin)
    po = await supply_chain.confirm_purchase_order_cost(
        db_session,
        po.id,
        confirmed_by="tester",
        workspace_id=WS,
        confirmer_user_id=str(admin.id),
    )
    # draft -> approved (admin) -> ordered (operator) -> partial_received -> received
    po = await supply_chain.approve_purchase_order(
        db_session,
        workspace_id=WS,
        po_id=po.id,
        approved_by="a@x.com",
        caller_role="admin",
        caller_user_id=str(admin.id),
    )
    po = await supply_chain.order_purchase_order(
        db_session,
        workspace_id=WS,
        po_id=po.id,
        caller_user_id=str(operator.id),
    )
    po = await supply_chain.partial_receive_purchase_order(
        db_session,
        workspace_id=WS,
        po_id=po.id,
        caller_user_id=str(operator.id),
    )
    po = await supply_chain.receive_purchase_order(
        db_session,
        workspace_id=WS,
        po_id=po.id,
        caller_user_id=str(operator.id),
    )

    # cost-confirmed event carries admin role
    cc = (await _events(db_session, "supply.purchase_order_cost_confirmed", str(po.id)))[0]
    assert cc.payload.get("actor_user_id") == str(admin.id)
    assert cc.payload.get("actor_role") == "admin"

    # ordered / partial_received / received events carry the operator's role
    for etype in (
        "supply.purchase_order_ordered",
        "supply.purchase_order_partial_received",
        "supply.purchase_order_received",
    ):
        ev = (await _events(db_session, etype, str(po.id)))[0]
        assert ev.payload.get("actor_user_id") == str(operator.id), etype
        assert ev.payload.get("actor_role") == "operator", etype

    # created event carries a non-null actor_role (admin created it here)
    created = (await _events(db_session, "supply.purchase_order_created", str(po.id)))[0]
    assert created.payload.get("actor_role") is not None


@pytest.mark.asyncio
async def test_create_update_events_carry_actor_role(db_session):
    """create_purchase_order / update_purchase_order events record actor_role."""
    operator = await _seed_operator(db_session)
    seeded = await _seed_products(db_session, [("SKU-CR", "2.00", "USD")])
    pid = str(seeded[0][0].id)

    data = PurchaseOrderCreate(
        po_number=f"R3F3-CR-{uuid4().hex[:6]}",
        currency="USD",
        shipping_cost=Decimal("0"),
        items=[PurchaseOrderItemCreate(product_id=pid, sku="SKU-CR", name="x", quantity=1, unit_cost=Decimal("1.00"))],
    )
    po = await supply_chain.create_purchase_order(
        db_session, workspace_id=WS, data=data, actor_user_id=str(operator.id)
    )
    created = (await _events(db_session, "supply.purchase_order_created", str(po.id)))[0]
    assert created.payload.get("actor_user_id") == str(operator.id)
    assert created.payload.get("actor_role") == "operator"

    po = await supply_chain.update_purchase_order(
        db_session,
        workspace_id=WS,
        po_id=po.id,
        data=PurchaseOrderUpdate(notes="updated"),
        actor_user_id=str(operator.id),
    )
    updated = (await _events(db_session, "supply.purchase_order_updated", str(po.id)))[0]
    assert updated.payload.get("actor_user_id") == str(operator.id)
    assert updated.payload.get("actor_role") == "operator"


@pytest.mark.asyncio
async def test_nonzero_shipping_and_full_audit_snapshot(db_session):
    """Non-zero shipping -> subtotal/shipping/total all correct AND the
    cost-confirmed event payload carries the full PO-level audit fields plus a
    per-SKU cost_snapshot with provenance (R3-F1)."""
    seeded = await _seed_products(db_session, [("SKU-SHIP", "6.00", "USD")])
    pid = str(seeded[0][0].id)
    data = PurchaseOrderCreate(
        po_number=f"R3F3-SHIP-{uuid4().hex[:6]}",
        currency="USD",
        shipping_cost=Decimal("12.34"),
        items=[
            PurchaseOrderItemCreate(product_id=pid, sku="SKU-SHIP", name="x", quantity=3, unit_cost=Decimal("1.00"))
        ],
    )
    admin = await _seed_admin(db_session)
    po = await supply_chain.create_purchase_order(db_session, workspace_id=WS, data=data, actor_user_id=str(admin.id))
    po.status = "pending_cost_confirmation"
    await db_session.flush()

    po = await supply_chain.confirm_purchase_order_cost(
        db_session,
        po.id,
        confirmed_by="tester",
        workspace_id=WS,
        confirmer_user_id=str(admin.id),
        trace_id="tr-ship-1",
    )
    await db_session.refresh(po)
    # subtotal = 6.00 * 3 = 18.00; total = 18.00 + shipping 12.34 = 30.34
    assert po.subtotal == Decimal("18.00")
    assert po.shipping_cost == Decimal("12.34")
    assert po.total == Decimal("30.34")

    ev = (await _events(db_session, "supply.purchase_order_cost_confirmed", str(po.id)))[0]
    p = ev.payload
    # PO-level fields present
    assert p.get("subtotal") == "18.00"
    assert p.get("shipping_cost") == "12.34"
    assert p.get("total") == "30.34"
    assert p.get("cost_source") == "product_cost"
    assert p.get("from_status") == "pending_cost_confirmation"
    assert p.get("to_status") == "draft"
    assert p.get("actor_user_id") == str(admin.id)
    assert p.get("actor_role") == "admin"
    assert ev.trace_id == "tr-ship-1"
    # per-SKU snapshot carries full provenance
    snap = p.get("cost_snapshot")
    assert snap and len(snap) == 1
    s = snap[0]
    for key in (
        "product_id",
        "sku",
        "product_cost_id",
        "product_cost_version",
        "product_cost_valid_from",
        "currency",
        "quantity",
        "unit_cost",
        "line_total",
    ):
        assert key in s, f"cost_snapshot missing {key}"
    assert s["sku"] == "SKU-SHIP"
    assert s["quantity"] == 3
    assert s["unit_cost"] == "6.00"
    assert s["line_total"] == "18.00"
    assert s["currency"] == "USD"


@pytest.mark.asyncio
async def test_cancel_after_confirmation_carries_actor_role(db_session):
    """Confirm cost then cancel (draft -> cancelled): the cancelled event records
    the cancelling operator's DB-verified actor_role."""
    operator = await _seed_operator(db_session)
    seeded = await _seed_products(db_session, [("SKU-CXL", "3.00", "USD")])
    pid = str(seeded[0][0].id)
    data = PurchaseOrderCreate(
        po_number=f"R3F3-CXL-{uuid4().hex[:6]}",
        currency="USD",
        shipping_cost=Decimal("0"),
        items=[PurchaseOrderItemCreate(product_id=pid, sku="SKU-CXL", name="x", quantity=1, unit_cost=Decimal("1.00"))],
    )
    admin = await _seed_admin(db_session)
    po = await supply_chain.create_purchase_order(
        db_session, workspace_id=WS, data=data, actor_user_id=str(operator.id)
    )
    po.status = "pending_cost_confirmation"
    await db_session.flush()
    po = await supply_chain.confirm_purchase_order_cost(
        db_session,
        po.id,
        confirmed_by="tester",
        workspace_id=WS,
        confirmer_user_id=str(admin.id),
    )
    assert po.status == "draft"
    po = await supply_chain.cancel_purchase_order(
        db_session,
        workspace_id=WS,
        po_id=po.id,
        caller_user_id=str(operator.id),
    )
    assert po.status == "cancelled"
    ev = (await _events(db_session, "supply.purchase_order_cancelled", str(po.id)))[0]
    assert ev.payload.get("actor_user_id") == str(operator.id)
    assert ev.payload.get("actor_role") == "operator"


@pytest.mark.asyncio
async def test_product_id_without_product_rejects_no_sku_fallback(db_session):
    """A product_id resolving to NO Product must fail closed - the resolver must
    NOT fall back to the SKU and silently pull another product's cost (R3-F1
    SKU-fallback hole fixed in ee38dad).

    create_purchase_order validates product existence up front (_ensure_product),
    so we build a valid PO then point the item's product_id at a ghost id to
    exercise the resolver's fail-closed path directly."""
    seeded = await _seed_products(db_session, [("SKU-REAL", "8.00", "USD")])
    real_pid = str(seeded[0][0].id)
    po, admin = await _mk_pending_po(
        db_session,
        po_number=f"R3F3-GHOST-{uuid4().hex[:6]}",
        items=[("SKU-REAL", real_pid, 1)],
    )
    # Force the item's product_id to a ghost id (no Product row), keeping sku.
    items = await _po_items(db_session, po.id)
    items[0].product_id = uuid4()
    await db_session.flush()

    with pytest.raises(supply_chain.SupplyChainError):
        await supply_chain.confirm_purchase_order_cost(
            db_session,
            po.id,
            confirmed_by="tester",
            workspace_id=WS,
            confirmer_user_id=str(admin.id),
        )
    await db_session.refresh(po)
    assert po.cost_confirmed is False
    assert po.status == "pending_cost_confirmation"
