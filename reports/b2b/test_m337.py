"""M3.37 测试：状态变更、费用缺失、重复计费、利润计算（M3.37 指令任务 9 要求）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_m336
from _m335_skus_data import PURCHASE_SRC, SKUS, margin_breakdown


def _st(wc):
    # D 档 34 款不在 PURCHASE_SRC，用默认 "D"（与 generate_m336 一致）
    return generate_m336.m336_status(wc, PURCHASE_SRC.get(wc, "D"), None)


def test_status_change_cost_verified_partial():
    """M335 COST_VERIFIED 24 → COST_VERIFIED_PARTIAL（采购有据、重量/HS未核实）。"""
    for wc in [907, 917, 990, 991, 992, 995, 996, 997, 1009]:
        assert _st(wc) == "COST_VERIFIED_PARTIAL", f"#{wc}"


def test_status_change_stopped_to_pending():
    """#1014/#1013 STOPPED → STOP_PENDING_OWNER_APPROVAL（无 Owner 审批记录）。"""
    for wc in (1014, 1013):
        assert _st(wc) == "STOP_PENDING_OWNER_APPROVAL", f"#{wc}"


def test_status_restructure():
    assert _st(1722) == "RESTRUCTURE"


def test_status_needs_evidence_count():
    """D 档（品类估算）33 款标 NEEDS_EVIDENCE（#1722 为 RESTRUCTURE 除外）。"""
    cnt = 0
    for wc in {s[0] for s in SKUS}:
        if PURCHASE_SRC.get(wc, "D") == "D" and wc not in (1014, 1013, 1722):
            assert _st(wc) == "NEEDS_EVIDENCE", f"#{wc}"
            cnt += 1
    assert cnt == 33


def test_missing_fee_not_default_zero():
    """清关费/代垫费不得默认为 $0：模型只含明确费用，缺失项显式不存在。"""
    mb = margin_breakdown(29.99, 12.80)
    assert "broker_fee" not in mb and "disbursement_fee" not in mb
    assert "customs_broker_fee" not in mb and "carrier_disbursement_fee" not in mb


def test_no_double_count():
    """支付费/退货/扣CAC 各计一次，无重复。"""
    price, landed = 29.99, 12.80
    mb = margin_breakdown(price, landed)
    pay = price * 0.029 + 0.30
    ret = price * 0.12
    assert abs(mb["gross_margin"] - (price - landed - pay - ret)) < 0.01
    assert abs(mb["contrib"] - (price - landed - pay)) < 0.01
    assert abs(mb["net"] - (price - landed - pay - ret - 15)) < 0.01


def test_margin_sample_968():
    """样本 #968（售价 29.99，到岸 12.80）核对三口径。"""
    mb = margin_breakdown(29.99, 12.80)
    assert mb["gross_margin_pct"] == 41.4
    assert mb["net_pct"] == -8.6
