"""Gate: hardcoded_fallback data must NOT auto-run the 1688 pipeline.

A hardcoded fallback snapshot (data_source="hardcoded_fallback") is a degraded
placeholder, not live product data. import_from_1688 must return it without
running the pipeline when auto_run_pipeline=True, and must mark why it skipped,
so stale prices/SKUs never silently auto-list to WooCommerce.
"""
import pytest

from app.services import product_pipeline_service as svc


def _fallback_result() -> dict:
    return {
        "success": True,
        "data": {
            "import_id": "imp-1",
            "product_id": "964465929482",
            "source_url": "964465929482",
            "data_source": "hardcoded_fallback",
            "product_info": {"name": "杜克头灯", "sku": "X"},
        },
        "error": None,
    }


async def test_fallback_blocks_auto_pipeline(monkeypatch):
    async def fake_fetch(url_or_id):
        return _fallback_result()

    called = {"run_pipeline": False}

    async def fake_run_pipeline(**kwargs):  # pragma: no cover - must not be reached
        called["run_pipeline"] = True
        return {"data": {"status": "listed"}}

    monkeypatch.setattr(svc, "_cached_fetch_1688_product", fake_fetch)
    monkeypatch.setattr(svc, "run_pipeline", fake_run_pipeline)

    result = await svc.import_from_1688(
        "964465929482", auto_run_pipeline=True, auto_list=True
    )

    assert result["success"] is True, "fallback 导入本身仍应成功返回"
    assert called["run_pipeline"] is False, "兜底假数据禁止自动跑 pipeline"
    assert "pipeline_skipped_reason" in result["data"], "必须带显式跳过标记"
    assert "hardcoded_fallback" in result["data"]["pipeline_skipped_reason"]


async def test_real_scrape_still_auto_runs(monkeypatch):
    real = _fallback_result()
    real["data"]["data_source"] = "scrapling"  # 真实抓取

    async def fake_fetch(url_or_id):
        return real

    called = {"run_pipeline": False}

    async def fake_run_pipeline(**kwargs):
        called["run_pipeline"] = True
        return {"data": {"status": "listed"}}

    monkeypatch.setattr(svc, "_cached_fetch_1688_product", fake_fetch)
    monkeypatch.setattr(svc, "run_pipeline", fake_run_pipeline)

    result = await svc.import_from_1688(
        "964465929482", auto_run_pipeline=True, auto_list=True
    )

    assert called["run_pipeline"] is True, "真实抓取数据应正常自动流转"
    assert "pipeline_skipped_reason" not in result["data"]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # import_from_1688 本身不 sleep，这里仅防未来引入；保持测试快速
    yield
