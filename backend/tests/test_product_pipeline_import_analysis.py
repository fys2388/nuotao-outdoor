"""Tests for the combined 1688 import and AI analysis workflow."""

import pytest

from app.api.v1.endpoints import product_pipeline as product_pipeline_endpoint
from app.services import (
    newton_agent_service,
    product_pipeline_service,
    sourcing_1688_service,
)


@pytest.mark.asyncio
async def test_import_and_analyze_from_1688_combines_import_and_report(monkeypatch) -> None:
    def fake_import(
        url_or_id: str,
        *,
        auto_run_pipeline: bool = False,
        auto_list: bool = False,
    ) -> dict:
        assert url_or_id == "https://detail.1688.com/offer/123456789.html"
        assert auto_run_pipeline is False
        assert auto_list is False
        return {
            "success": True,
            "data": {
                "import_id": "import-1",
                "product_id": "123456789",
                "source_url": url_or_id,
                "product_info": {
                    "name": "Camping Lantern",
                    "supplier": {"company_name": "Nuotao Factory"},
                },
            },
            "error": None,
        }

    async def fake_analyze(product_info: dict, **_: object) -> dict:
        assert product_info["supplier_name"] == "Nuotao Factory"
        return {
            "success": True,
            "data": {
                "ai_recognition": {"product_category": "Camping Lantern"},
                "product_report": {"product_name": "Portable Camping Lantern"},
                "metadata": {"analysis": {"provider": "test"}},
            },
            "error": None,
        }

    monkeypatch.setattr(product_pipeline_service, "import_from_1688", fake_import)
    monkeypatch.setattr(
        product_pipeline_service,
        "analyze_and_generate_report",
        fake_analyze,
    )

    result = await product_pipeline_service.import_and_analyze_from_1688(
        "https://detail.1688.com/offer/123456789.html"
    )

    assert result["success"] is True
    assert result["data"]["product_id"] == "123456789"
    assert result["data"]["product_info"]["supplier_name"] == "Nuotao Factory"
    assert result["data"]["ai_recognition"]["product_category"] == "Camping Lantern"
    assert result["data"]["product_report"]["product_name"] == "Portable Camping Lantern"


@pytest.mark.asyncio
async def test_import_and_analyze_from_1688_preserves_import_error(monkeypatch) -> None:
    def fake_import(*_: object, **__: object) -> dict:
        return {
            "success": False,
            "error": "1688商品不存在",
            "data": {"source_url": "https://detail.1688.com/offer/404.html"},
        }

    monkeypatch.setattr(product_pipeline_service, "import_from_1688", fake_import)

    result = await product_pipeline_service.import_and_analyze_from_1688(
        "https://detail.1688.com/offer/404.html"
    )

    assert result["success"] is False
    assert result["error"] == "1688商品不存在"


def test_import_and_analyze_endpoint(api_client, monkeypatch) -> None:
    async def fake_import_and_analyze(**_: object) -> dict:
        return {
            "success": True,
            "data": {
                "product_id": "123456789",
                "product_info": {"name": "Camping Lantern"},
                "ai_recognition": {"product_category": "Camping Lantern"},
                "product_report": {"product_name": "Portable Camping Lantern"},
            },
            "error": None,
        }

    monkeypatch.setattr(
        product_pipeline_endpoint,
        "import_and_analyze_from_1688",
        fake_import_and_analyze,
    )

    response = api_client.post(
        "/api/v1/product-pipeline/import-and-analyze-1688",
        json={"url_or_id": "https://detail.1688.com/offer/123456789.html"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["product_id"] == "123456789"


def test_import_from_1688_falls_back_to_newton_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        sourcing_1688_service,
        "get_product_detail",
        lambda _: {
            "success": False,
            "source": "1688_open_api",
            "error": "gw.APIACLDecline: AppKey is not allowed(acl)",
        },
    )
    monkeypatch.setattr(newton_agent_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        newton_agent_service,
        "extract_1688_product",
        lambda url_or_id, product_id: {
            "success": True,
            "source": "newton_agent",
            "task_id": "task-1",
            "product": {
                "product_id": product_id,
                "subject": "户外防水露营灯",
                "description": "太阳能充电长续航露营灯",
                "price": "15.50-22.80",
                "price_range": [{"startQuantity": 1, "price": "15.50"}],
                "images": ["https://cbu01.alicdn.com/product.jpg"],
                "supplier": {"company_name": "中山市成铂照明科技有限公司"},
            },
        },
    )

    result = product_pipeline_service.import_from_1688(
        "https://detail.1688.com/offer/1075485124628.html"
    )

    assert result["success"] is True
    assert result["data"]["data_source"] == "newton_agent"
    assert result["data"]["product_info"]["name"] == "户外防水露营灯"
    assert result["data"]["product_info"]["price"] == "15.50-22.80"
    assert result["data"]["product_info"]["supplier"]["company_name"] == "中山市成铂照明科技有限公司"


def test_import_from_1688_rejects_mock_as_real(monkeypatch) -> None:
    monkeypatch.setattr(
        sourcing_1688_service,
        "get_product_detail",
        lambda _: {
            "success": True,
            "source": "mock",
            "product": {"product_id": "1", "subject": "示例产品", "price": "25.80"},
        },
    )
    monkeypatch.setattr(newton_agent_service, "is_configured", lambda: False)

    result = product_pipeline_service.import_from_1688("1")

    assert result["success"] is False
    assert "示例数据" in result["error"]
