"""
认证 API 端点（数据库版本）
登录、注册、Token 刷新、当前用户、修改密码、用户管理
"""
from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    validate_token,
)
from app.schemas.user import (
    ChangePassword,
    Token,
    TokenRefresh,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.services.user_db_service import (
    authenticate_user_db,
    change_password_db,
    create_user_db,
    delete_user_db,
    ensure_default_admin_db,
    get_user_by_id_db,
    list_users_db,
    update_user_db,
    update_user_last_login_db,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """获取当前登录用户（依赖注入）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = validate_token(token, token_type="access")
    if not payload:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = await get_user_by_id_db(db, user_id)
    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    return user


def require_role(*roles: str):
    """角色权限装饰器工厂"""
    async def role_checker(
        current_user: UserResponse = Depends(get_current_user),
    ) -> UserResponse:
        if current_user.role == "admin":
            return current_user
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色: {', '.join(roles)}，当前角色: {current_user.role}",
            )
        return current_user
    return role_checker


@router.on_event("startup")
async def startup_event():
    """启动时确保默认管理员存在"""
    try:
        async for db in get_db():
            await ensure_default_admin_db(db)
            break
        logger.info("Default admin user ensured (DB)")
    except Exception as e:
        logger.warning("Failed to ensure default admin: %s", str(e))


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """用户登录（OAuth2 表单）"""
    user = await authenticate_user_db(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user.id)
    await update_user_last_login_db(db, user_id)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    extra_claims = {
        "role": user.role,
        "username": user.username,
        "email": user.email,
    }

    access_token = create_access_token(
        subject=user_id,
        extra_claims=extra_claims,
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(subject=user_id, extra_claims=extra_claims)

    user_response = await get_user_by_id_db(db, user_id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_response,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: TokenRefresh,
    db: AsyncSession = Depends(get_db),
):
    """刷新访问令牌"""
    payload = validate_token(request.refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌无效或已过期",
        )

    user_id = payload.get("sub")
    user = await get_user_by_id_db(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    extra_claims = {
        "role": user.role,
        "username": user.username,
        "email": user.email,
    }

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user_id,
        extra_claims=extra_claims,
        expires_delta=access_token_expires,
    )
    new_refresh_token = create_refresh_token(subject=user_id, extra_claims=extra_claims)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return current_user


@router.put("/me/password")
async def change_my_password(
    request: ChangePassword,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户密码"""
    success = await change_password_db(db, current_user.id, request.old_password, request.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="原密码错误")
    return {"success": True, "message": "密码修改成功"}


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """注册新用户（默认 viewer 角色）"""
    try:
        user_create.role = "viewer"
        user = await create_user_db(db, user_create)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== 管理员用户管理接口 =====

@router.get("/users", response_model=UserListResponse)
async def get_users(
    page: int = 1,
    page_size: int = 20,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """获取用户列表（仅管理员）"""
    users, total = await list_users_db(db, page=page, page_size=page_size)
    return UserListResponse(users=users, total=total, page=page, page_size=page_size)


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user_admin(
    user_create: UserCreate,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """创建用户（仅管理员）"""
    try:
        return await create_user_db(db, user_create)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user_admin(
    user_id: str,
    user_update: UserUpdate,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """更新用户（仅管理员）"""
    user = await update_user_db(db, user_id, user_update)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.delete("/users/{user_id}")
async def delete_user_admin(
    user_id: str,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """删除用户（仅管理员）"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")
    success = await delete_user_db(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "message": "用户已删除"}
