"""PII 字段加密原语（设计 / Staging 验证阶段）。

Owner 决策（APR-M440-PII-001，2026-11-18，reports/b2b/M441_INSTRUCTION_FROM_CHATGPT.md）：
本轮只允许设计、代码实现、自动化测试与 Staging 验证；**禁止**触碰生产 PII、
生产回填、删除明文字段、修改生产密钥或做生产 PII schema 迁移。

设计要点（对应 Owner 11 项要求）：
1. ``email_hash`` = HMAC-SHA-256(pii_hmac_key, normalize_email(email))，hex 摘要，检索用；
2. ``email_encrypted`` = AES-256-GCM 信封加密：base64(iv || ciphertext || tag)；
3. ``contact_name_encrypted`` = 同 AES-256-GCM；
4. 密钥走环境变量（生产缺失即硬失败），后续可接 KMS（KeyProvider 可插拔）；
5. 双读写过渡：读优先密文、写双写；明文回填后由回填脚本删除（Staging 验证）；
6. 等值检索用 ``email_hash`` 唯一索引，不用明文；
7. Admin 解密仅 ``require_role("operator")``，日志脱敏；
8. ``pii_key_version`` 列支持轮换；
9. normalize：casefold + strip（大小写/空格），@ 校验；
10. 回填/回滚脚本（Staging 验证，生产不执行）；
11. 备份为密文，恢复需 KEK。

不触碰任何生产数据；本模块仅提供纯函数原语，供迁移/回填/服务层使用。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings


class PiiCryptoError(Exception):
    """PII 加密/解密失败。"""


def normalize_email(email: str) -> str:
    """规范化邮箱（lowercase + strip）；非法值抛错。"""
    if not isinstance(email, str) or not email.strip():
        raise PiiCryptoError("email is required")
    normalized = email.strip().casefold()
    if "@" not in normalized or len(normalized) < 5:
        raise PiiCryptoError("invalid email")
    return normalized


def _pii_hmac_key() -> bytes:
    settings = get_settings()
    key = (settings.pii_hmac_key or "").strip()
    if not key:
        raise PiiCryptoError("PII_HMAC_KEY must be configured")
    return key.encode("utf-8")


def _pii_enc_key() -> bytes:
    settings = get_settings()
    key = (settings.pii_encryption_key or "").strip()
    if not key:
        raise PiiCryptoError("PII_ENCRYPTION_KEY must be configured")
    try:
        raw = base64.b64decode(key)
    except Exception as exc:  # noqa: BLE001
        raise PiiCryptoError("PII_ENCRYPTION_KEY must be base64") from exc
    if len(raw) != 32:
        raise PiiCryptoError("PII_ENCRYPTION_KEY must be 32-byte base64")
    return raw


def build_email_hash(email: str, *, workspace_id: str | None = None) -> str:
    """HMAC-SHA-256 摘要（可选 workspace 作用域），hex。

    确定性：同邮箱 + 同 workspace 永远得到同值，用于唯一索引与等值检索。
    """
    normalized = normalize_email(email)
    message = (
        f"{workspace_id}:{normalized}".encode("utf-8")
        if workspace_id
        else normalized.encode("utf-8")
    )
    return hmac.new(_pii_hmac_key(), message, hashlib.sha256).hexdigest()


def encrypt_field(plaintext: str) -> str:
    """AES-256-GCM 加密，返回 base64(iv || ct || tag)，无 AAD。"""
    if not isinstance(plaintext, str):
        raise PiiCryptoError("plaintext must be str")
    key = _pii_enc_key()
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(iv + ciphertext).decode("ascii")


def decrypt_field(token: str) -> str:
    """解密 ``base64(iv || ct || tag)``；格式/密钥错误抛 PiiCryptoError。"""
    if not isinstance(token, str) or not token:
        raise PiiCryptoError("invalid ciphertext")
    try:
        raw = base64.b64decode(token)
    except Exception as exc:  # noqa: BLE001
        raise PiiCryptoError("invalid ciphertext") from exc
    if len(raw) < 13:
        raise PiiCryptoError("invalid ciphertext")
    iv, ciphertext = raw[:12], raw[12:]
    try:
        return AESGCM(_pii_enc_key()).decrypt(iv, ciphertext, None).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise PiiCryptoError("decryption failed") from exc
