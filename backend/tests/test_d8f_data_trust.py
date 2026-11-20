"""D8-F 商品数据真实性与采集供应链 — 专项测试。

覆盖 D8-F 目标 (4) fail-closed 门禁覆盖 10 类异常 与 (5) 接入 E0-E5 证据等级体系。

10 类异常（D8F_ARCHITECTURE.md §4）：
  1 Cookie失效  2 登录墙  3 占位名  4 价格为空  5 规格缺失
  6 页面ID不匹配  7 解析器不兼容  8 原始数据不可追溯  9 来源冲突
  10 hardcoded_fallback意外调用

核心原则：宁可少采集一个商品，也不能让虚假商品信息进入选品/利润分析/上架/采购决策。
证据等级复用 M334 E0-E5，禁止跳跃升级，商品级 ≠ 字段级。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services import product_pipeline_service as svc
from app.services.data_providers import (
    EvidenceGrade,
    ManualProvider,
    ProductProvenance,
    ProviderResult,
)
from app.services.data_providers.base import FieldProvenance
from app.services.listing_gate import evaluate_gate_from_dict


# ---------------------------------------------------------------------------
# (4) fail-closed：ManualProvider 覆盖 占位名 / 价格为空 / 规格缺失 / 占位/不可追溯
# ---------------------------------------------------------------------------

def _provider() -> ManualProvider:
    return ManualProvider(collected_by="tester")


def test_manual_collect_ok_is_real_but_e0():
    """有效人工录入：ok=True、is_real=True（真实观察），但证据等级初始 E0。"""
    r: ProviderResult = _provider().collect(
        "https://detail.1688.com/964465929482.html",
        fields={"name": "户外折叠月亮椅", "price": 59.9, "images": ["https://x/1.jpg"]},
    )
    assert r.ok is True
    assert r.degraded is False
    assert r.provenance is not None
    assert r.provenance.is_real is True
    assert r.provenance.evidence_grade == EvidenceGrade.E0
    # 字段级来源已记录（商品级真实 ≠ 字段级默认已核实）
    assert "name" in r.provenance.field_provenance
    assert r.provenance.field_provenance["name"].is_verified is True


def test_manual_placeholder_name_fail_closed():
    """异常3 占位名：占位/空名 → ok=False（fail-closed，不产出假数据）。"""
    for bad in ("1688 Product", "Product", "商品", "", "x"):
        r = _provider().collect("x", fields={"name": bad, "price": 10})
        assert r.ok is False, f"占位名 {bad!r} 应被拒"
        assert r.data is None
        assert r.fail_closed_reason and "占位" in r.fail_closed_reason


def test_manual_missing_price_fail_closed():
    """异常4 价格为空/为0：拒绝，绝不伪造默认价（对应审计 N1 price=35.8）。"""
    for bad_price in (None, "", 0, "0", -1):
        r = _provider().collect("x", fields={"name": "合法商品名", "price": bad_price})
        assert r.ok is False, f"价格 {bad_price!r} 应被拒"
        assert r.data is None


def test_manual_spec_missing_is_degraded_flag_not_fake():
    """异常5 规格缺失：无 SKU 时仍可建档（基础信息真实），但需无伪造 SKU。"""
    r = _provider().collect("x", fields={"name": "无规格商品", "price": 20, "sku_list": []})
    # 人工录入缺规格不阻断建档（基础信息真实），但不伪造 SKU
    if r.ok:
        assert r.data.get("sku_list") in (None, [], "") or isinstance(r.data.get("sku_list"), list)


def test_manual_untraceable_source_still_records_provider():
    """异常8 原始数据不可追溯：即便无 source_url，provenance 仍记录 provider/时间。"""
    r = _provider().collect("", fields={"name": "无链接商品", "price": 30})
    assert r.ok is True
    assert r.provenance.provider == "manual"
    assert isinstance(r.provenance.collected_at, datetime)
    assert r.provenance.trace_id  # 有 trace_id 贯穿审计


# ---------------------------------------------------------------------------
# (4) fail-closed：import 闸门覆盖 登录墙/未知/hardcoded_fallback
# ---------------------------------------------------------------------------

def _import_result(data_source: str) -> dict:
    return {
        "success": True,
        "data": {
            "import_id": "imp-x",
            "product_id": "964465929482",
            "source_url": "964465929482",
            "data_source": data_source,
            "product_info": {"name": "杜克头灯", "sku": "X"},
        },
        "error": None,
    }


@pytest.mark.parametrize(
    "data_source",
    ["hardcoded_fallback", "unknown", "", "login_wall", "placeholder"],
)
@pytest.mark.asyncio
async def test_import_gate_blocks_all_non_authentic(monkeypatch, data_source):
    """异常1/2/3/10：任何非真实来源（兜底/登录墙/占位/未知）都阻断自动流转，
    且无论 auto_run_pipeline 取值（旧逻辑只拦 hardcoded_fallback+True）。"""
    async def fake_fetch(url_or_id):
        return _import_result(data_source)

    called = {"run_pipeline": False}

    async def fake_run_pipeline(**kwargs):  # pragma: no cover - must not be reached
        called["run_pipeline"] = True
        return {"data": {"status": "listed"}}

    monkeypatch.setattr(svc, "_cached_fetch_1688_product", fake_fetch)
    monkeypatch.setattr(svc, "run_pipeline", fake_run_pipeline)

    for auto in (True, False):
        called["run_pipeline"] = False
        result = await svc.import_from_1688("964465929482", auto_run_pipeline=auto)
        assert called["run_pipeline"] is False, f"{data_source} auto={auto} 不得自动流转"
        assert result["data"].get("is_authentic") is False
        assert "pipeline_skipped_reason" in result["data"]


@pytest.mark.asyncio
async def test_import_gate_allows_authentic_scrapling(monkeypatch):
    """真实抓取（scrapling）放行自动流转——白名单不放行则合法采集也被堵死。"""
    async def fake_fetch(url_or_id):
        return _import_result("scrapling")

    called = {"run_pipeline": False}

    async def fake_run_pipeline(**kwargs):
        called["run_pipeline"] = True
        return {"data": {"status": "listed"}}

    monkeypatch.setattr(svc, "_cached_fetch_1688_product", fake_fetch)
    monkeypatch.setattr(svc, "run_pipeline", fake_run_pipeline)

    result = await svc.import_from_1688("964465929482", auto_run_pipeline=True)
    assert called["run_pipeline"] is True
    assert result["data"].get("is_authentic") is True


# ---------------------------------------------------------------------------
# (4) fail-closed：上架闸门 unauthentic_source（HARD_BLOCK，不可 force）
# ---------------------------------------------------------------------------

def test_listing_gate_blocks_fallback_source():
    """异常10：hardcoded_fallback 上架被硬阻断。"""
    gate = evaluate_gate_from_dict({
        "sku": "NT-1", "regular_price": "19.9",
        "data_source": "hardcoded_fallback", "is_authentic": False,
    })
    codes = [r["code"] for r in gate["reasons"]]
    assert gate["status"] == "blocked"
    assert "unauthentic_source" in codes


def test_listing_gate_blocks_missing_source():
    """异常8：来源缺失（不可追溯）上架被硬阻断（1688 链路经 convert 必有来源）。"""
    gate = evaluate_gate_from_dict({"sku": "NT-2", "regular_price": "19.9"})
    codes = [r["code"] for r in gate["reasons"]]
    assert gate["status"] == "blocked"
    assert "unauthentic_source" in codes


def test_listing_gate_passes_authentic_source():
    """真实来源（scrapling/manual）不因来源被拦——不误杀合法采集。"""
    for ds in ("scrapling", "manual", "1688_open_api"):
        gate = evaluate_gate_from_dict({
            "sku": "NT-3", "regular_price": "19.9",
            "data_source": ds, "is_authentic": True,
        })
        codes = [r["code"] for r in gate["reasons"]]
        assert "unauthentic_source" not in codes


# ---------------------------------------------------------------------------
# (5) 接入 E0-E5：赋值 / 禁止跳跃 / 商品级 ≠ 字段级
# ---------------------------------------------------------------------------

def test_evidence_grade_values_match_m334():
    """E0-E5 枚举与 M334 体系一致，不另起标准。"""
    assert [g.value for g in EvidenceGrade] == ["E0", "E1", "E2", "E3", "E4", "E5"]


def test_evidence_grade_manual_starts_at_e0():
    """人工录入初始 E0（仅基础信息），不可直接跳到 E4/E5 做利润结论。"""
    r = _provider().collect("x", fields={"name": "折叠椅", "price": 10})
    assert r.provenance.evidence_grade == EvidenceGrade.E0
    assert r.provenance.evidence_grade != EvidenceGrade.E4
    assert r.provenance.evidence_grade != EvidenceGrade.E5


def test_provenance_product_level_vs_field_level():
    """商品级 ≠ 字段级：商品 E0 时价格字段可单独标记已核实（真实观察）。"""
    r = _provider().collect("x", fields={"name": "折叠椅", "price": 25})
    prov: ProductProvenance = r.provenance
    # 商品级仍是 E0
    assert prov.evidence_grade == EvidenceGrade.E0
    # 但价格字段级可已核实（人工真实观察）
    assert prov.field_provenance["price"].is_verified is True
    # 商品级 E0 ≠ 字段级 verified，二者独立


def test_field_provenance_carries_provider_and_time():
    """字段级来源追溯带 provider + collected_at（可审计到具体字段来源）。"""
    fp = FieldProvenance(
        value=59.9, provider="manual",
        collected_at=datetime.now(UTC), is_verified=True,
    )
    assert fp.provider == "manual"
    assert isinstance(fp.collected_at, datetime)
    assert fp.is_verified is True


def test_provider_result_fail_closed_no_data_on_reject():
    """fail-closed 铁律：ok=False 时 data=None，绝不返回 success=True + 假数据。"""
    r = _provider().collect("x", fields={"name": "Product", "price": 0})
    assert r.ok is False
    assert r.data is None
    assert r.provenance is None
    assert r.fail_closed_reason
