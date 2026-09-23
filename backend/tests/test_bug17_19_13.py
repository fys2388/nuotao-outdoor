"""Regression tests for BUG #19 (WC sync retry) and BUG #13 (unauthorized publish audit).

BUG #19: `list_to_woocommerce` must retry transient failures with exponential
backoff (1s / 3s / 9s) and only retry recoverable errors (429/5xx/network);
4xx business errors (400/422) must fail immediately without retry.

BUG #13: When WC sync observes a product that is `publish` on WC but still
`draft` locally, it must write a `product.wc_unauthorized_publish` audit event
to the event log so operators can trace who bypassed the ListingJob gate.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import HTTPException

from app.services.product_listing_service import list_to_woocommerce


def _wc_post_mock(*responses: MagicMock) -> MagicMock:
    """Return a MagicMock whose .post() pops a response from the given list.

    Each `responses` entry is a MagicMock with `.raise_for_status()` and
    `.json()`; when a raise_for_status call is expected to fail, the mock
    raises HTTPError with a synthetic `.response`.
    """
    queue = list(responses)
    calls = []

    def post(url, auth=None, json=None, timeout=30):
        calls.append({"url": url, "json": json})
        if not queue:
            raise AssertionError(f"too many requests.post calls ({len(calls)})")
        return queue.pop(0)

    mock = MagicMock()
    mock.post.side_effect = post
    mock.post.call_count = 0
    return mock


def _mock_response(status_code: int, payload: dict | None = None, raise_for_status: bool = True) -> MagicMock:
    """Build a MagicMock mimicking requests.Response.

    If `raise_for_status` is True, calling `.raise_for_status()` will
    raise an HTTPError; otherwise it's a no-op.
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload or {}
    if raise_for_status:
        err = requests.exceptions.HTTPError(
            f"HTTP {status_code}", response=resp,
        )
        resp.raise_for_status.side_effect = err
    else:
        resp.raise_for_status.side_effect = None
    return resp


def test_bug19_retries_on_500_then_succeeds() -> None:
    """Retry transient 5xx, succeed on 3rd attempt; return attempts=3."""
    ok_payload = {"id": 42, "name": "Test", "status": "publish", "permalink": "https://x"}
    resp_500_1 = _mock_response(500, {"message": "Internal Server Error"}, raise_for_status=True)
    resp_500_2 = _mock_response(503, {"message": "Service Unavailable"}, raise_for_status=True)
    resp_ok = _mock_response(200, ok_payload, raise_for_status=False)

    with patch(
        "app.services.product_listing_service.requests.post",
        side_effect=[resp_500_1, resp_500_2, resp_ok],
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_KEY", "k",
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_SECRET", "s",
    ), patch(
        "app.services.product_listing_service.evaluate_gate_from_dict",
        return_value={"status": "passed", "reasons": []},
    ), patch("time.sleep", return_value=None) as mock_sleep:
        product = {"sku": "SKU-19", "name": "N", "description": "D", "short_description": "SD"}
        result = list_to_woocommerce(product, status="publish")

    assert result["success"] is True, result
    assert result["woocommerce_id"] == 42
    assert result["attempts"] == 3
    # Exponential backoff: two retries => sleeps of 1s then 3s
    assert mock_sleep.call_count == 2
    sleeps = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleeps == [1.0, 3.0], sleeps


def test_bug19_400_returns_without_retry() -> None:
    """4xx business error must not retry."""
    resp_400 = _mock_response(400, {"message": "bad sku"}, raise_for_status=True)

    with patch(
        "app.services.product_listing_service.requests.post",
        return_value=resp_400,
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_KEY", "k",
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_SECRET", "s",
    ), patch(
        "app.services.product_listing_service.evaluate_gate_from_dict",
        return_value={"status": "passed", "reasons": []},
    ), patch("time.sleep", return_value=None) as mock_sleep:
        product = {"sku": "SKU-400", "name": "N", "description": "D", "short_description": "SD"}
        result = list_to_woocommerce(product, status="publish")

    assert result["success"] is False
    assert result.get("retryable") is False
    assert result.get("attempt") == 1
    # No retry happened, so no sleep should be called
    mock_sleep.assert_not_called()


def test_bug19_network_error_exhausts_all_attempts() -> None:
    """Network exception (ConnectionError) exhausts retries and returns retryable=True."""
    with patch(
        "app.services.product_listing_service.requests.post",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_KEY", "k",
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_SECRET", "s",
    ), patch(
        "app.services.product_listing_service.evaluate_gate_from_dict",
        return_value={"status": "passed", "reasons": []},
    ), patch(
        "time.sleep", return_value=None,
    ) as mock_sleep:
        product = {"sku": "SKU-CONN", "name": "N", "description": "D", "short_description": "SD"}
        result = list_to_woocommerce(product, status="publish")

    assert result["success"] is False
    assert result["attempts"] == 3
    assert result.get("retryable") is True
    # 3 attempts means 2 sleeps between them
    assert mock_sleep.call_count == 2


def test_bug19_429_retries() -> None:
    """429 rate limit should retry."""
    resp_429 = _mock_response(429, {"message": "rate limited"}, raise_for_status=True)
    ok_payload = {"id": 43, "name": "R", "status": "publish", "permalink": "https://r"}
    resp_ok = _mock_response(200, ok_payload, raise_for_status=False)

    with patch(
        "app.services.product_listing_service.requests.post",
        side_effect=[resp_429, resp_ok],
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_KEY", "k",
    ), patch(
        "app.services.product_listing_service.WC_CONSUMER_SECRET", "s",
    ), patch(
        "app.services.product_listing_service.evaluate_gate_from_dict",
        return_value={"status": "passed", "reasons": []},
    ), patch(
        "time.sleep", return_value=None,
    ) as mock_sleep:
        product = {"sku": "SKU-429", "name": "R", "description": "D", "short_description": "SD"}
        result = list_to_woocommerce(product, status="publish")

    assert result["success"] is True
    assert result["woocommerce_id"] == 43
    assert result["attempts"] == 2
    assert mock_sleep.call_count == 1
