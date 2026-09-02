"""
用户存储服务
使用 JSON 文件存储用户数据（P0-2 数据库持久化时迁移到 PostgreSQL）
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.security import get_password_hash, verify_password
from app.schemas.user import UserCreate, UserResponse, UserUpdate

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "users",
)
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_users() -> dict[str, dict[str, Any]]:
    """加载所有用户"""
    _ensure_data_dir()
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load users: %s", str(e))
        return {}


def _save_users(users: dict[str, dict[str, Any]]) -> None:
    """保存所有用户"""
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error("Failed to save users: %s", str(e))


def _user_to_response(user: dict[str, Any]) -> UserResponse:
    """转换用户字典为响应模型"""
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        full_name=user.get("full_name"),
        role=user.get("role", "viewer"),
        is_active=user.get("is_active", True),
        created_at=datetime.fromisoformat(user["created_at"]) if user.get("created_at") else datetime.now(timezone.utc),
        updated_at=datetime.fromisoformat(user["updated_at"]) if user.get("updated_at") else None,
        last_login_at=datetime.fromisoformat(user["last_login_at"]) if user.get("last_login_at") else None,
    )


def create_user(user_create: UserCreate) -> UserResponse:
    """创建用户"""
    users = _load_users()

    # 检查用户名是否已存在
    for existing_user in users.values():
        if existing_user["username"] == user_create.username:
            raise ValueError(f"用户名 '{user_create.username}' 已存在")
        if user_create.email and existing_user.get("email") == user_create.email:
            raise ValueError(f"邮箱 '{user_create.email}' 已被注册")

    user_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    user = {
        "id": user_id,
        "username": user_create.username,
        "email": user_create.email,
        "full_name": user_create.full_name,
        "hashed_password": get_password_hash(user_create.password),
        "role": user_create.role,
        "is_active": user_create.is_active,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }

    users[user_id] = user
    _save_users(users)

    logger.info("User created: id=%s, username=%s, role=%s", user_id, user_create.username, user_create.role)
    return _user_to_response(user)


def get_user_by_id(user_id: str) -> UserResponse | None:
    """根据 ID 获取用户"""
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return None
    return _user_to_response(user)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """根据用户名获取用户（包含密码哈希，用于认证）"""
    users = _load_users()
    for user in users.values():
        if user["username"] == username:
            return user
        if user.get("email") == username:
            return user
    return None


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """验证用户凭据"""
    user = get_user_by_username(username)
    if not user:
        return None
    if not user.get("is_active", True):
        return None
    if not verify_password(password, user.get("hashed_password", "")):
        return None
    return user


def update_user_last_login(user_id: str) -> None:
    """更新用户最后登录时间"""
    users = _load_users()
    if user_id in users:
        users[user_id]["last_login_at"] = datetime.now(timezone.utc).isoformat()
        _save_users(users)


def update_user(user_id: str, user_update: UserUpdate) -> UserResponse | None:
    """更新用户"""
    users = _load_users()
    if user_id not in users:
        return None

    user = users[user_id]
    update_data = user_update.model_dump(exclude_unset=True)

    if update_data.get("password"):
        user["hashed_password"] = get_password_hash(update_data["password"])
        del update_data["password"]

    for key, value in update_data.items():
        if value is not None:
            user[key] = value

    user["updated_at"] = datetime.now(timezone.utc).isoformat()
    users[user_id] = user
    _save_users(users)

    logger.info("User updated: id=%s", user_id)
    return _user_to_response(user)


def delete_user(user_id: str) -> bool:
    """删除用户"""
    users = _load_users()
    if user_id not in users:
        return False
    del users[user_id]
    _save_users(users)
    logger.info("User deleted: id=%s", user_id)
    return True


def list_users(page: int = 1, page_size: int = 20) -> tuple[list[UserResponse], int]:
    """列出用户（分页）"""
    users = _load_users()
    user_list = list(users.values())
    total = len(user_list)

    start = (page - 1) * page_size
    end = start + page_size
    paginated_users = user_list[start:end]

    return [_user_to_response(u) for u in paginated_users], total


def change_password(user_id: str, old_password: str, new_password: str) -> bool:
    """修改密码"""
    users = _load_users()
    if user_id not in users:
        return False

    user = users[user_id]
    if not verify_password(old_password, user.get("hashed_password", "")):
        return False

    user["hashed_password"] = get_password_hash(new_password)
    user["updated_at"] = datetime.now(timezone.utc).isoformat()
    users[user_id] = user
    _save_users(users)

    logger.info("Password changed for user: id=%s", user_id)
    return True


def ensure_default_admin() -> UserResponse:
    """确保默认管理员用户存在"""
    users = _load_users()
    for user in users.values():
        if user.get("role") == "admin":
            return _user_to_response(user)

    # 创建默认管理员
    admin = UserCreate(
        username="admin",
        email="admin@nuotao.com",
        full_name="系统管理员",
        password="Admin@2026",
        role="admin",
        is_active=True,
    )
    return create_user(admin)
