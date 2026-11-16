"""M3.38 测试：审批状态、证据等级、费用缺失、重复费用、成本闭环逻辑（M3.38 指令任务 9）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_m338
from _m335_skus_data import PURCHASE_SRC, margin_breakdown


def test_apr_register_seven_pending():
    """APR-001~007 全部登记且无真实审批记录（PENDING 状态由报告逻辑体现）。"""
    assert len(generate_m338.APRS) == 7
    ids = [a[0] for a in generate_m338.APRS]
    assert ids == [f"APR-00{i}" for i in range(1, 8)]
    # 每项含审批人/时间/证据占位（M338-01 输出全部 PENDING）
    rpt = generate_m338.m338_01()
    assert rpt.count("**PENDING**") == 7


def test_status_cost_verified_partial():
    """采购有据但重量/HS未核实 → COST_VERIFIED_PARTIAL。"""
    for wc in (907, 917, 990, 991, 992, 995, 996, 997, 1009):
        assert generate_m338.status_of(wc, PURCHASE_SRC.get(wc, "D")) == "COST_VERIFIED_PARTIAL"


def test_status_stopped_to_pending():
    for wc in (1014, 1013):
        assert generate_m338.status_of(wc, PURCHASE_SRC.get(wc, "D")) == "STOP_PENDING_OWNER_APPROVAL"


def test_status_restructure():
    assert generate_m338.status_of(1722, "D") == "RESTRUCTURE"


def test_status_needs_evidence_count():
    cnt = 0
    for s in generate_m338.recs():
        if s["psrc"] == "D" and s["wc"] not in (1014, 1013, 1722):
            assert s["status"] == "NEEDS_EVIDENCE", s["wc"]
            cnt += 1
    assert cnt == 33


def test_missing_fee_not_default_zero():
    """清关费/代垫费不得默认 $0：模型不隐式含它们。"""
    mb = margin_breakdown(29.99, 12.80)
    assert "broker_fee" not in mb and "disbursement_fee" not in mb
    assert "customs_broker_fee" not in mb and "carrier_disbursement_fee" not in mb


def test_no_double_count():
    """支付/退货/扣CAC 各计一次。"""
    price, landed = 29.99, 12.80
    mb = margin_breakdown(price, landed)
    pay = price * 0.029 + 0.30
    ret = price * 0.12
    assert abs(mb["gross_margin"] - (price - landed - pay - ret)) < 0.01
    assert abs(mb["contrib"] - (price - landed - pay)) < 0.01
    assert abs(mb["net"] - (price - landed - pay - ret - 15)) < 0.01


def test_cost_closure_zero_skus():
    """无 SKU 满足 8 项闭环条件 → 如实报告 0 SKU，不强行闭环。"""
    rpt = generate_m338.m338_07()
    assert "0 SKU" in rpt
    assert "不" in rpt or "不得" in rpt  # 含"不得为了完成阶段目标降低标准"
