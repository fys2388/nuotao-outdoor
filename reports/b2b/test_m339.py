"""M3.39 测试：审批状态控制、证据等级、费用缺失、重复费用、完整成本验证、未经授权动作阻断。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_m339
from _m335_skus_data import PURCHASE_SRC, margin_breakdown


def test_apr_004_005_approved_only():
    """APR-004/005 APPROVED，其余 PENDING（真实 Owner 审批，非 AI 摘要）。"""
    assert generate_m339.APR_STATUS["APR-004"] == "APPROVED"
    assert generate_m339.APR_STATUS["APR-005"] == "APPROVED"
    for a in ("APR-001", "APR-002", "APR-003", "APR-006", "APR-007"):
        assert generate_m339.APR_STATUS[a] == "PENDING"
    assert sum(1 for v in generate_m339.APR_STATUS.values() if v == "APPROVED") == 2


def test_approval_register_contains_real_approval():
    """M339-02 登记含真实 Owner 授权记录（2026-11-16，非 AI 摘要）。"""
    rpt = generate_m339.m339_02()
    assert "APPROVED" in rpt and "2026-11-16" in rpt
    assert "Owner 明确授权记录" in rpt


def test_status_cost_verified_partial():
    for wc in (907, 917, 990, 991, 992, 995, 996, 997, 1009):
        assert generate_m339.status_of(wc, PURCHASE_SRC.get(wc, "D")) == "COST_VERIFIED_PARTIAL"


def test_status_stopped_pending():
    for wc in (1014, 1013):
        assert generate_m339.status_of(wc, PURCHASE_SRC.get(wc, "D")) == "STOP_PENDING_OWNER_APPROVAL"


def test_missing_fee_not_default_zero():
    mb = margin_breakdown(29.99, 12.80)
    assert "broker_fee" not in mb and "disbursement_fee" not in mb
    assert "customs_broker_fee" not in mb and "carrier_disbursement_fee" not in mb


def test_no_double_count():
    price, landed = 29.99, 12.80
    mb = margin_breakdown(price, landed)
    pay = price * 0.029 + 0.30
    ret = price * 0.12
    assert abs(mb["gross_margin"] - (price - landed - pay - ret)) < 0.01
    assert abs(mb["net"] - (price - landed - pay - ret - 15)) < 0.01


def test_no_unauthorized_actions():
    """边界：未联系供应商/报关行/货代、未停售/迁仓、未改 WC/生产。"""
    rpt = generate_m339.m339_08(generate_m339.recs()) + generate_m339.m339_09(generate_m339.recs())
    assert "保持 STOP_PENDING_OWNER_APPROVAL" in rpt
    assert "暂不迁仓" in rpt or "未迁仓" in rpt
    assert "未改价" in rpt or "未下架" in rpt


def test_unified_evidence_archive():
    """#1719/#1722/#998 同时出现在实测与价格清单 → 统一 SKU 证据档案。"""
    rpt3 = generate_m339.m339_03(generate_m339.recs())
    rpt4 = generate_m339.m339_04(generate_m339.recs())
    assert "#1719" in rpt3 and "#1722" in rpt3 and "#998" in rpt3
    assert "#1719" in rpt4 and "#1722" in rpt4 and "#998" in rpt4
    assert "统一 SKU 证据档案" in rpt3
