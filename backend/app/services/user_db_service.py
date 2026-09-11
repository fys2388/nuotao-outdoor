"""
基于数据库的用户服务
使用 PostgreSQL 存储用户数据（替换 JSON 文件存储）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate

logger = logging.getLogger(__name__)


def _user_to_response(user: User) -> UserResponse:
    """转换 ORM 用户对象为响应模型"""
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at if user.created_at else datetime.now(timezone.utc),
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


async def create_user_db(db: AsyncSession, user_create: UserCreate) -> UserResponse:
    """创建用户（数据库）"""
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == user_create.username))
    if result.scalar_one_or_none():
        raise ValueError(f"用户名 '{user_create.username}' 已存在")

    # 检查邮箱是否已存在
    if user_create.email:
        result = await db.execute(select(User).where(User.email == user_create.email))
        if result.scalar_one_or_none():
            raise ValueError(f"邮箱 '{user_create.email}' 已被注册")

    user = User(
        id=str(uuid4()),
        username=user_create.username,
        email=user_create.email,
        full_name=user_create.full_name,
        hashed_password=get_password_hash(user_create.password),
        role=user_create.role,
        is_active=user_create.is_active,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("User created (DB): id=%s, username=%s, role=%s", user.id, user.username, user.role)
    return _user_to_response(user)


async def get_user_by_id_db(db: AsyncSession, user_id: str) -> UserResponse | None:
    """根据 ID 获取用户（数据库）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    return _user_to_response(user)


async def get_user_by_username_db(db: AsyncSession, username: str) -> User | None:
    """根据用户名获取用户（包含密码哈希，用于认证）"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user:
        return user

    # 尝试按邮箱查找
    result = await db.execute(select(User).where(User.email == username))
    return result.scalar_one_or_none()


async def authenticate_user_db(db: AsyncSession, username: str, password: str) -> User | None:
    """验证用户凭据（数据库）"""
    user = await get_user_by_username_db(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def update_user_last_login_db(db: AsyncSession, user_id: str) -> None:
    """更新用户最后登录时间（数据库）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()


async def update_user_db(db: AsyncSession, user_id: str, user_update: UserUpdate) -> UserResponse | None:
    """更新用户（数据库）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    update_data = user_update.model_dump(exclude_unset=True)

    if update_data.get("password"):
        user.hashed_password = get_password_hash(update_data["password"])
        del update_data["password"]

    for key, value in update_data.items():
        if value is not None:
            setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    logger.info("User updated (DB): id=%s", user_id)
    return _user_to_response(user)


async def delete_user_db(db: AsyncSession, user_id: str) -> bool:
    """删除用户（数据库）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False

    await db.delete(user)
    await db.commit()

    logger.info("User deleted (DB): id=%s", user_id)
    return True


async def list_users_db(db: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[UserResponse], int]:
    """列出用户（分页，数据库）"""
    # 获取总数
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()

    # 获取分页数据
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    users = result.scalars().all()

    return [_user_to_response(u) for u in users], total


async def change_password_db(db: AsyncSession, user_id: str, old_password: str, new_password: str) -> bool:
    """修改密码（数据库）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return False

    if not verify_password(old_password, user.hashed_password):
        return False

    user.hashed_password = get_password_hash(new_password)
    await db.commit()

    logger.info("Password changed (DB) for user: id=%s", user_id)
    return True


async def ensure_default_admin_db(db: AsyncSession) -> UserResponse:
    """确保默认管理员用户存在（数据库）"""
    result = await db.execute(select(User).where(User.role == "admin"))
    admin = result.scalar_one_or_none()
    if admin:
        return _user_to_response(admin)

    # 创建默认管理员
    admin_create = UserCreate(
        username="admin",
        email="admin@nuotao.com",
        full_name="系统管理员",
        password="Admin@2026",
        role="admin",
        is_active=True,
    )
    return await create_user_db(db, admin_create)
