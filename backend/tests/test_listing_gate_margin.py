# -*- coding: utf-8 -*-
"""PRICE-002 毛利门禁测试。

回归对象：商品 2230 曾以 $5.83 售价上架，而采购成本换汇后为 $6.30——
每单亏损却通过了上架门禁，因为 listing_gate 只校验「有没有价格」「有没有成本」，
从不校验「价格是否覆盖成本」。

本测试锁定修复后的行为：
  1. 售价 < 落地成本 → blocked（negative_margin，硬阻断，force 不可放行）
  2. 覆盖成本但净利 < 25% → needs_review（below_margin_target，可 force）
  3. 净利 ≥ 25% → passed
  4. 无成本数据 → 不误判为毛利问题（仍报 missing_cost）
  5. 有实测 total_landed_cost 时优先采用（measured），否则回退估算（estimated）
  6. CNY 计价成本按配置汇率换算，不得当作 USD
  7. evaluate_gate_from_dict（管线的无门禁出口）同样拦截亏损价
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.services.listing_gate import (
    HARD_BLOCK,
    REVIEW_REQUIRED,
    evaluate_gate,
    evaluate_gate_from_dict,
)
from app.services.pricing_policy import (
    evaluate_price,
    minimum_price,
    net_margin,
    suggested_retail_price,
)

APPROVED_COPY = {
    "status": "approved",
    "title": "Retractable LED Camping Lantern",
    "description": "x" * 700,  # 超过 _MIN_DESCRIPTION_CHARS=600，不触发 thin_copy
}


def make_product(sku="NT-TEST-1", candidate_status=None):
    # data_source="manual": 模拟已通过来源真实性校验的商品，使本测试聚焦 PRICE-002
    # 毛利行为而非 D8-F unauthentic_source 门禁（后者由 fallback_gate 测试覆盖）。
    return SimpleNamespace(sku=sku, name="Test Lantern", description="", candidate_status=candidate_status, data_source="manual")


def gate_for(regular_price, purchase_cost, **kwargs):
    """跑一次门禁，只关心毛利相关结论。"""
    return evaluate_gate(
        make_product(),
        {"regular_price": regular_price, "sale_price": None},
        APPROVED_COPY,
        purchase_cost=purchase_cost,
        **kwargs,
    )


def codes(gate):
    return {r["code"] for r in gate["reasons"]}


# ---------------------------------------------------------------- 1. 硬阻断

def test_price_below_landed_cost_is_hard_blocked() -> None:
    """2230 的真实场景：采购 ¥45（=$6.30），售价 $5.83。必须 blocked。"""
    gate = gate_for(5.83, 6.30)
    assert gate["status"] == "blocked"
    assert "negative_margin" in codes(gate)


def test_negative_margin_is_in_hard_block_set() -> None:
    """硬阻断集合必须包含 negative_margin，否则 force 可绕过。"""
    assert "negative_margin" in HARD_BLOCK


def test_price_equal_to_purchase_cost_still_blocked() -> None:
    """售价 == 采购价时落地成本必然更高（物流+费用），仍属亏损。"""
    gate = gate_for(6.30, 6.30)
    assert gate["status"] == "blocked"
    assert "negative_margin" in codes(gate)


# ------------------------------------------------------- 2. 未达标需复核

def test_below_target_margin_needs_review_not_blocked() -> None:
    """覆盖成本但净利 < 25% → needs_review（可人工 force 放行）。"""
    # 落地成本 = 6.30 + 0.50(头程) + 5.00(尾程) + 0.20(包装) = 12.00
    # 达标最低价 = (12.00 + 0.30) / (1 - 0.209 - 0.25) = 22.74
    gate = gate_for(15.00, 6.30)
    assert gate["status"] == "needs_review"
    assert "below_margin_target" in codes(gate)
    assert "negative_margin" not in codes(gate)


def test_below_margin_target_is_overridable() -> None:
    """below_margin_target 必须在 REVIEW_REQUIRED 中（引流/清仓是合法业务决策）。"""
    assert "below_margin_target" in REVIEW_REQUIRED
    assert "below_margin_target" not in HARD_BLOCK


def test_suggested_price_in_review_message() -> None:
    """复核信息必须给出建议售价，否则运营无从下手。"""
    gate = gate_for(15.00, 6.30)
    msg = next(r["message"] for r in gate["reasons"] if r["code"] == "below_margin_target")
    assert "建议售价" in msg
    assert "22.99" in msg


# ------------------------------------------------------------- 3. 达标放行

def test_price_meeting_target_passes() -> None:
    """$22.99（净利 25.6%）应通过，不得误伤修复后的 2230。"""
    gate = gate_for(22.99, 6.30)
    assert "negative_margin" not in codes(gate)
    assert "below_margin_target" not in codes(gate)
    assert gate["status"] == "passed", gate["reasons"]


def test_margin_boundary_exactly_at_target() -> None:
    """恰好达标（净利 == 25%）应视为通过，不得因浮点误差误判。"""
    landed = 6.30 + 0.50 + 5.00 + 0.20
    p_min = minimum_price(landed)
    m = net_margin(p_min, landed)
    assert m >= 0.25 - 1e-9


# --------------------------------------------------- 4. 无成本不误判毛利

def test_missing_cost_does_not_produce_margin_verdict() -> None:
    """无成本数据时只能报 missing_cost，不得凭空判定亏损。"""
    gate = gate_for(5.83, None)
    c = codes(gate)
    assert "missing_cost" in c
    assert "negative_margin" not in c
    assert "below_margin_target" not in c


def test_zero_cost_does_not_produce_margin_verdict() -> None:
    gate = gate_for(5.83, 0)
    c = codes(gate)
    assert "missing_cost" in c
    assert "negative_margin" not in c


def test_omitted_cost_skips_margin_check() -> None:
    """purchase_cost 未传（调用方尚未接入成本）时不做毛利判定，保持向后兼容。"""
    gate = evaluate_gate(
        make_product(),
        {"regular_price": 5.83, "sale_price": None},
        APPROVED_COPY,
    )
    c = codes(gate)
    assert "missing_cost" not in c
    assert "negative_margin" not in c


def test_missing_price_does_not_produce_margin_verdict() -> None:
    """无价格时报 missing_price，毛利判定应跳过而非崩溃。"""
    gate = gate_for(None, 6.30)
    assert "missing_price" in codes(gate)
    assert "negative_margin" not in codes(gate)


# ------------------------------------------- 5. 实测成本优先于估算

def test_measured_landed_cost_preferred() -> None:
    """有实测 total_landed_cost 时必须采用，不用默认物流估算。"""
    # 实测落地成本 $18 → 达标最低价 (18+0.30)/0.541 = $33.83
    # $22.99 在估算口径下达标，在实测口径下不达标
    row = SimpleNamespace(purchase_cost=6.30, total_landed_cost=18.00, currency="USD")
    gate = gate_for(22.99, 6.30, cost_row=row)
    assert "below_margin_target" in codes(gate)
    assert "negative_margin" not in codes(gate)


def test_measured_cost_verdict_marks_basis() -> None:
    v = evaluate_price(22.99, 6.30,
                       cost_row=SimpleNamespace(purchase_cost=6.30,
                                                total_landed_cost=18.00, currency="USD"))
    assert v["landed_basis"] == "measured"


def test_invalid_measured_row_falls_back_to_estimate() -> None:
    """P2-9 有效成本语义：landed=0 的行无效，必须回退估算而非当作零成本。"""
    row = SimpleNamespace(purchase_cost=6.30, total_landed_cost=0, currency="USD")
    v = evaluate_price(22.99, 6.30, cost_row=row)
    assert v["landed_basis"] == "estimated"
    assert v["verdict"] == "ok"


def test_zero_cost_row_is_not_free_margin() -> None:
    """落地成本为 0 的占位行不得产出「毛利 ≈ 售价全额」的假象。"""
    row = SimpleNamespace(purchase_cost=0, total_landed_cost=0, currency="USD")
    v = evaluate_price(22.99, 6.30, cost_row=row)
    assert v["landed_basis"] == "estimated"
    assert v["landed_cost"] > 0


# ------------------------------------------------------ 6. CNY 汇率换算

def test_cny_purchase_cost_is_converted() -> None:
    """CNY 计价成本必须按配置汇率换算：¥45 → $6.30，$22.99 达标。"""
    v = evaluate_price(22.99, 45.00, purchase_currency="CNY")
    assert v["purchase_usd"] == Decimal("6.30")
    assert v["verdict"] == "ok"


def test_cny_cost_treated_as_usd_overblocks_not_hides() -> None:
    """危险方向验证：若漏换算把 ¥45 当 $45，落地成本虚高 → 会【过度拦截】。

    这不会隐藏亏损（安全侧），但会误伤正常商品，所以换算仍必须正确。
    正确口径下 $5.83 对 ¥45(=$6.30) 判 negative；错误口径把它当 $45 成本，
    $5.83 更是远低于成本，同样 negative —— 两口径都拦截低价，差别在高价商品：
    """
    v_cny = evaluate_price(22.99, 45.00, purchase_currency="CNY")   # 正确：成本 $6.30
    v_usd = evaluate_price(22.99, 45.00, purchase_currency="USD")   # 错误：成本 $45
    assert v_cny["purchase_usd"] == Decimal("6.30")
    assert v_usd["purchase_usd"] == Decimal("45.00")
    assert v_cny["verdict"] == "ok"          # 换算后 $22.99 达标
    assert v_usd["verdict"] == "negative"    # 漏换算则 $22.99 < 落地$50.70 被误判亏损


# --------------------------------------------- 7. 管线无门禁出口同样拦截

def test_dict_gate_blocks_negative_margin() -> None:
    """evaluate_gate_from_dict 是管线直推 WC 的出口，必须同样拦截亏损价。"""
    gate = evaluate_gate_from_dict({
        "sku": "NT-TEST-2",
        "name": "Test Lantern",
        "description": "English copy",
        "regular_price": 5.83,
        "purchase_cost": 6.30,
    })
    assert gate["status"] == "blocked"
    assert "negative_margin" in codes(gate)


def test_dict_gate_passes_healthy_price() -> None:
    gate = evaluate_gate_from_dict({
        "sku": "NT-TEST-3",
        "name": "Test Lantern",
        "description": "English copy",
        "regular_price": 22.99,
        "purchase_cost": 6.30,
    })
    assert "negative_margin" not in codes(gate)


def test_dict_gate_silent_without_cost_field() -> None:
    """不携带成本字段的调用方保持既有语义：不因沉默而全部转 needs_review。"""
    gate = evaluate_gate_from_dict({
        "sku": "NT-TEST-4",
        "name": "Test Lantern",
        "description": "English copy",
        "regular_price": 5.83,
    })
    assert "negative_margin" not in codes(gate)
    assert "missing_cost" not in codes(gate)


# --------------------------------------------------- 定价工具函数

def test_suggested_price_ends_in_99_and_meets_floor() -> None:
    """建议售价必须 .99 结尾且不低于达标最低价（PRICE-004）。"""
    landed = Decimal("6.30") + Decimal("0.50") + Decimal("5.00") + Decimal("0.20")
    p = suggested_retail_price(landed)
    assert str(p).endswith(".99")
    assert p >= minimum_price(landed)
    assert p == Decimal("22.99")  # 2230 实际采用的价格


def test_suggested_price_is_none_for_bad_input() -> None:
    assert suggested_retail_price(0) is None
    assert suggested_retail_price(None) is None
    assert suggested_retail_price(-5) is None


def test_net_margin_none_for_zero_price() -> None:
    assert net_margin(0, 10) is None


def test_undeterminable_when_no_price() -> None:
    v = evaluate_price(None, 6.30)
    assert v["verdict"] == "undeterminable"
