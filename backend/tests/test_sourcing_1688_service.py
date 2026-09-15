"""Unit tests for 1688 open-platform URL and signature construction."""

from app.services.sourcing_1688_service import (
    _build_aop_url_path,
    _sign_aop,
)


def test_build_aop_url_path_contains_namespace_and_name() -> None:
    path = _build_aop_url_path("alibaba.product.get", app_key="123456")

    assert path == "param2/1/com.alibaba.product/alibaba.product.get/123456"


def test_aop_signature_uses_hmac_sha1_and_url_path() -> None:
    path = "param2/1/com.alibaba.product/alibaba.product.get/123456"
    params = {
        "productID": "1075485124628",
        "access_token": "token",
        "_aop_timestamp": "1700000000000",
    }

    assert _sign_aop(path, params, "secret") == (
        "0B279C60A8A47E83DFEAB7298DE595A88DBBC741"
    )
