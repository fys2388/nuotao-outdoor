"""PII 加密原语测试（APR-M440-PII-001，设计/Staging 阶段，不触碰生产）。"""

import base64
import os

import pytest

from app.core import pii_crypto
from app.core.config import get_settings
from app.core.pii_crypto import PiiCryptoError


@pytest.fixture(autouse=True)
def _pii_keys(monkeypatch):
    """配置测试密钥并清除 settings 缓存（get_settings 为 lru_cache）。"""
    monkeypatch.setenv("PII_HMAC_KEY", "test-hmac-key")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_normalize_email():
    assert pii_crypto.normalize_email("  User@Example.COM ") == "user@example.com"


def test_normalize_email_invalid():
    with pytest.raises(PiiCryptoError):
        pii_crypto.normalize_email("not-an-email")
    with pytest.raises(PiiCryptoError):
        pii_crypto.normalize_email("")
    with pytest.raises(PiiCryptoError):
        pii_crypto.normalize_email(None)


def test_build_email_hash_deterministic():
    a = pii_crypto.build_email_hash("User@Example.com", workspace_id="w1")
    b = pii_crypto.build_email_hash("user@example.com", workspace_id="w1")
    assert a == b
    assert len(a) == 64


def test_build_email_hash_workspace_scoped():
    a = pii_crypto.build_email_hash("user@example.com", workspace_id="w1")
    b = pii_crypto.build_email_hash("user@example.com", workspace_id="w2")
    assert a != b


def test_encrypt_decrypt_roundtrip():
    token = pii_crypto.encrypt_field("Buyer@Example.com")
    assert pii_crypto.decrypt_field(token) == "Buyer@Example.com"
    # 随机 IV → 同明文两次密文不同
    assert token != pii_crypto.encrypt_field("Buyer@Example.com")


def test_encrypt_rejects_non_str():
    with pytest.raises(PiiCryptoError):
        pii_crypto.encrypt_field(None)  # type: ignore[arg-type]


def test_decrypt_wrong_key(monkeypatch):
    token = pii_crypto.encrypt_field("secret@example.com")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    get_settings.cache_clear()
    with pytest.raises(PiiCryptoError):
        pii_crypto.decrypt_field(token)


def test_decrypt_malformed():
    with pytest.raises(PiiCryptoError):
        pii_crypto.decrypt_field("not-base64!!")
    with pytest.raises(PiiCryptoError):
        pii_crypto.decrypt_field("")


def test_missing_key_hard_fails(monkeypatch):
    monkeypatch.delenv("PII_HMAC_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(PiiCryptoError):
        pii_crypto.build_email_hash("user@example.com")
