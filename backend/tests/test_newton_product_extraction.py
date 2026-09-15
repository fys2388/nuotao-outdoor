"""Tests for Newton Agent based 1688 product extraction."""

import json

from app.services import newton_agent_service


def test_extract_1688_product_parses_fenced_json(monkeypatch) -> None:
    final_payload = {
        "title": "户外防水露营灯",
        "product_id": "1075485124628",
        "price_min": 15.5,
        "price_max": 22.8,
        "price_range": "15.50-22.80",
        "moq": 1,
        "supplier_name": "中山市成铂照明科技有限公司",
        "image_urls": ["https://cbu01.alicdn.com/product.jpg"],
        "description": "太阳能充电长续航露营灯",
        "category": "户外照明",
    }

    monkeypatch.setattr(newton_agent_service, "is_configured", lambda: True)
    monkeypatch.setattr(
        newton_agent_service,
        "create_agent_task",
        lambda *_args, **_kwargs: {
            "success": True,
            "task_id": "task-1",
            "source": "newton_api",
        },
    )
    monkeypatch.setattr(
        newton_agent_service,
        "get_task_status",
        lambda _task_id: {
            "success": True,
            "status": "END",
            "raw": {"content": f"```json\n{json.dumps(final_payload, ensure_ascii=False)}\n```"},
        },
    )

    result = newton_agent_service.extract_1688_product(
        "https://detail.1688.com/offer/1075485124628.html",
        "1075485124628",
        poll_interval=1,
    )

    assert result["success"] is True
    assert result["source"] == "newton_agent"
    assert result["product"]["subject"] == "户外防水露营灯"
    assert result["product"]["price"] == "15.5-22.8"
    assert result["product"]["supplier"]["company_name"] == "中山市成铂照明科技有限公司"
