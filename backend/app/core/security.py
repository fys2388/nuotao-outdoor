"""
安全工具模块
密码哈希、JWT Token 生成和验证
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置。
# 2026-10-11 事故：此处曾硬编码一个开发用密钥并提交到公开仓库，任何人都能用它
# 伪造管理员 access/refresh token。密钥一律来自 .env 的 JWT_SECRET_KEY，
# 任何环境未配置都直接报错（fail closed）——不再保留仓库内默认值，
# 避免同一个字符串继续出现在公开代码里。
# 生成密钥：python -c "import secrets; print(secrets.token_urlsafe(64))"
_settings = get_settings()


def _resolve_secret_key() -> str:
    key = (_settings.jwt_secret_key or "").strip()
    if not key:
        raise RuntimeError(
            "JWT_SECRET_KEY 未配置：请在 .env 中设置（参见 .env.example）。\n"
            "生成方式：python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    return key


SECRET_KEY = _resolve_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时
REFRESH_TOKEN_EXPIRE_DAYS = 7


class JWTError(Exception):
    """JWT 错误包装"""
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error("Password verification failed: %s", str(e))
        return False


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def create_access_token(
    subject: str | Any,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    创建访问令牌（Access Token）

    Args:
        subject: 主题（通常是用户 ID）
        extra_claims: 额外声明（角色、权限等）
        expires_delta: 过期时间增量

    Returns:
        JWT Token 字符串
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "access",
        "iat": datetime.now(timezone.utc),
    }

    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    subject: str | Any,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """创建刷新令牌（Refresh Token）"""
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """
    解码 JWT Token

    Args:
        token: JWT Token 字符串

    Returns:
        解码后的 payload，失败返回 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError as e:
        logger.warning("JWT decode failed: %s", str(e))
        return None


def validate_token(token: str, token_type: str = "access") -> dict[str, Any] | None:
    """
    验证 Token 有效性（包括类型检查和过期检查）

    Args:
        token: JWT Token
        token_type: 期望的 token 类型（access/refresh）

    Returns:
        有效的 payload，无效返回 None
    """
    payload = decode_token(token)
    if not payload:
        return None

    # 检查 token 类型
    if payload.get("type") != token_type:
        logger.warning("Token type mismatch: expected %s, got %s", token_type, payload.get("type"))
        return None

    # 检查过期时间（jose 会自动检查，但这里显式检查）
    exp = payload.get("exp")
    if exp:
        if datetime.now(timezone.utc).timestamp() > exp:
            logger.warning("Token expired")
            return None

    return payload
