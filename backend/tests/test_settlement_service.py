"""settlements 回款台账 + 周报真实数据源测试（运营闭环 P0-1/P0-2）。"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import Order
from app.services import settlement_service
from app.services.real_business_data import build_business_data_from_db

WS = settlement_service.DEFAULT_WORKSPACE_ID


# --------------------------------------------------------------------------- #
# 登记
# --------------------------------------------------------------------------- #

async def test_register_settlement_expected(db_session):
    entry = await settlement_service.register_settlement(
        db_session,
        workspace_id=WS,
        carrier="correos",
        expected_amount=Decimal("120.00"),
        external_order_id="WC-1001",
        settlement_kind="cod",
        due_date=date(2026, 9, 15),
    )
    assert entry["status"] == "expected"
    assert entry["expected_amount"] == "120.00"
    assert entry["received_amount"] == "0.00"
    assert entry["carrier"] == "correos"


async def test_register_settlement_invalid_kind(db_session):
    with pytest.raises(settlement_service.SettlementError):
        await settlement_service.register_settlement(
            db_session,
            workspace_id=WS,
            carrier="correos",
            expected_amount=Decimal("10"),
            settlement_kind="bogus",
        )


async def test_register_settlement_negative_amount(db_session):
    with pytest.raises(settlement_service.SettlementError):
        await settlement_service.register_settlement(
            db_session,
            workspace_id=WS,
            carrier="correos",
            expected_amount=Decimal("-5"),
        )


# --------------------------------------------------------------------------- #
# 实收状态机：expected -> partial -> received（含扣费口径）
# --------------------------------------------------------------------------- #

async def test_full_receipt_with_fees_marks_received(db_session):
    entry = await settlement_service.register_settlement(
        db_session,
        workspace_id=WS,
        carrier="correos",
        expected_amount=Decimal("120.00"),
        fees=Decimal("0"),
    )
    # 实收 115.5 + 扣费 4.5 = 120 => 全额结清
    after = await settlement_service.record_receipt(
        db_session,
        settlement_id=entry["id"],
        received_amount=Decimal("115.50"),
        fees=Decimal("4.50"),
    )
    assert after["status"] == "received"
    assert after["received_amount"] == "115.50"
    assert after["fees"] == "4.50"


async def test_partial_receipt_marks_partial(db_session):
    entry = await settlement_service.register_settlement(
        db_session,
        workspace_id=WS,
        carrier="clearance_hungary",
        expected_amount=Decimal("300.00"),
        settlement_kind="clearance",
    )
    after = await settlement_service.record_receipt(
        db_session,
        settlement_id=entry["id"],
        received_amount=Decimal("100.00"),
    )
    assert after["status"] == "partial"
    assert after["received_amount"] == "100.00"


async def test_receipt_not_found(db_session):
    with pytest.raises(settlement_service.SettlementError):
        await settlement_service.record_receipt(
            db_session,
            settlement_id=uuid4(),
            received_amount=Decimal("10"),
        )


async def test_mark_disputed(db_session):
    entry = await settlement_service.register_settlement(
        db_session,
        workspace_id=WS,
        carrier="correos",
        expected_amount=Decimal("50"),
    )
    disputed = await settlement_service.mark_disputed(
        db_session, settlement_id=entry["id"], note="物流商拒付"
    )
    assert disputed["status"] == "disputed"
    assert "拒付" in disputed["note"]


# --------------------------------------------------------------------------- #
# 列表与统计
# --------------------------------------------------------------------------- #

async def test_list_settlements_filter(db_session):
    await settlement_service.register_settlement(
        db_session, workspace_id=WS, carrier="correos", expected_amount=Decimal("10")
    )
    await settlement_service.register_settlement(
        db_session, workspace_id=WS, carrier="stripe", expected_amount=Decimal("20")
    )
    result = await settlement_service.list_settlements(
        db_session, workspace_id=WS, carrier="correos"
    )
    assert result["total"] == 1
    assert result["items"][0]["carrier"] == "correos"


async def test_settlement_stats_rollup(db_session):
    # correos 全额结清（含扣费）
    a = await settlement_service.register_settlement(
        db_session,
        workspace_id=WS,
        carrier="correos",
        expected_amount=Decimal("120"),
        settlement_kind="cod",
    )
    await settlement_service.record_receipt(
        db_session, settlement_id=a["id"], received_amount=Decimal("115.5"), fees=Decimal("4.5")
    )
    # clearance 部分回款（100/300）
    b = await settlement_service.register_settlement(
        db_session,
        workspace_id=WS,
        carrier="clearance_hungary",
        expected_amount=Decimal("300"),
        settlement_kind="clearance",
    )
    await settlement_service.record_receipt(
        db_session, settlement_id=b["id"], received_amount=Decimal("100")
    )
    stats = await settlement_service.settlement_stats(db_session, workspace_id=WS)
    assert stats["by_status"]["received"]["count"] == 1
    assert stats["by_status"]["partial"]["count"] == 1
    # 待收 = 300 - 0 - 0 = 300（不含已结清的 correos）
    assert stats["totals"]["pending_amount"] == "200.00"
    # 按渠道分组
    assert stats["by_carrier"]["correos"]["received_amount"] == "115.50"
    assert stats["by_carrier"]["clearance_hungary"]["pending_amount"] == "200.00"


# --------------------------------------------------------------------------- #
# 周报真实数据源
# --------------------------------------------------------------------------- #

async def test_build_business_data_empty_db(db_session):
    week_end = datetime.utcnow().strftime("%Y-%m-%d")
    week_start = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    data = await build_business_data_from_db(
        db_session, week_start, week_end, workspace_id=WS
    )
    assert data["data_source"] == "database"
    assert data["key_metrics"]["total_orders"]["current"] == 0
    assert data["key_metrics"]["total_revenue"]["current"] == 0.0
    assert data["cash_in"]["pending_amount"] == "0.00"


async def test_build_business_data_with_order_and_settlement(db_session):
    ws = WS
    order = Order(
        workspace_id=ws,
        external_order_id=f"WC-{uuid4().hex[:8]}",
        status="completed",
        currency="USD",
        total=Decimal("100.00"),
        shipping_total=Decimal("10.00"),
        payment_fee=Decimal("3.00"),
        advertising_cost=Decimal("20.00"),
        profit_snapshot={
            "revenue": "100.00",
            "total_cost": "60.00",
            "contribution_margin": "40.00",
            "contribution_margin_rate": "0.4",
        },
    )
    db_session.add(order)
    await db_session.flush()

    await settlement_service.register_settlement(
        db_session,
        workspace_id=ws,
        carrier="correos",
        expected_amount=Decimal("120"),
        order_id=order.id,
        external_order_id=order.external_order_id,
    )

    week_end = datetime.utcnow().strftime("%Y-%m-%d")
    week_start = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    data = await build_business_data_from_db(
        db_session, week_start, week_end, workspace_id=ws
    )
    assert data["key_metrics"]["total_orders"]["current"] == 1
    assert data["key_metrics"]["total_revenue"]["current"] == 100.0
    assert data["key_metrics"]["gross_profit"]["current"] == 40.0
    assert data["key_metrics"]["ad_spend"]["current"] == 20.0
    assert data["key_metrics"]["roas"]["current"] == 5.0
    assert data["cash_in"]["pending_amount"] == "120.00"


# --------------------------------------------------------------------------- #
# API 可达性（TestClient + override get_db）
# --------------------------------------------------------------------------- #

def test_settlements_api_flow(api_client):
    r = api_client.post(
        "/api/v1/settlements",
        json={
            "carrier": "correos",
            "expected_amount": "120.00",
            "settlement_kind": "cod",
            "external_order_id": "WC-2001",
        },
    )
    assert r.status_code == 200, r.text
    sid = r.json()["settlement"]["id"]

    r2 = api_client.get("/api/v1/settlements?carrier=correos")
    assert r2.status_code == 200
    assert r2.json()["total"] == 1

    r3 = api_client.get("/api/v1/settlements/stats")
    assert r3.status_code == 200
    assert r3.json()["totals"]["expected_amount"] == "120.00"

    r4 = api_client.post(
        f"/api/v1/settlements/{sid}/receipt",
        json={"received_amount": "115.50", "fees": "4.50"},
    )
    assert r4.status_code == 200
    assert r4.json()["settlement"]["status"] == "received"
