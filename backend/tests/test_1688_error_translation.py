"""Tests for _translate_1688_error: 把 1688 原始错误翻译成用户可读中文。"""
import pytest

from app.services.product_pipeline_service import _translate_1688_error


@pytest.mark.parametrize(
    "raw, expected_code",
    [
        ("gw.APIACLDecline: AppKey is not allowed(acl)", "APPKEY_ACL_DECLINE"),
        ("gw.UserNotLogin", "USER_NOT_LOGIN"),
        ("connect timeout after 30s", "UPSTREAM_TIMEOUT"),
        ("Read timeout from 1688 open api", "UPSTREAM_TIMEOUT"),
        ("gw.IllegalParam: offer_id missing", "ILLEGAL_PARAM"),
        ("1688 return forbidden for this offer", "FORBIDDEN"),
        ("HTTP 403 forbidden", "FORBIDDEN"),
    ],
)
def test_known_errors_are_translated(raw: str, expected_code: str) -> None:
    friendly, code = _translate_1688_error(raw)
    assert friendly is not None
    assert code == expected_code
    # 翻译后的文本必须是中文友好语，不能只是把原文回传
    assert friendly != raw


@pytest.mark.parametrize("raw", [None, "", "some unknown upstream message"])
def test_unknown_errors_pass_through(raw: str | None) -> None:
    friendly, code = _translate_1688_error(raw)
    assert friendly is None
    assert code is None


def test_translation_is_case_insensitive() -> None:
    _, code = _translate_1688_error("Gw.ApiAclDecline: appkey is not allowed")
    assert code == "APPKEY_ACL_DECLINE"
