"""
用户相关 Schemas（Pydantic 模型）
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# 角色定义
class UserRole:
    ADMIN = "admin"           # 管理员（全部权限）
    OPERATOR = "operator"     # 运营（业务操作，无系统设置）
    CUSTOMER_SERVICE = "customer_service"  # 客服（订单/客户管理）
    VIEWER = "viewer"         # 只读（查看报表，无操作权限）

    ALL_ROLES = [ADMIN, OPERATOR, CUSTOMER_SERVICE, VIEWER]


# 权限定义
class Permission:
    # 订单管理
    ORDER_VIEW = "order:view"
    ORDER_CREATE = "order:create"
    ORDER_UPDATE = "order:update"
    ORDER_DELETE = "order:delete"
    ORDER_REFUND = "order:refund"

    # 产品管理
    PRODUCT_VIEW = "product:view"
    PRODUCT_CREATE = "product:create"
    PRODUCT_UPDATE = "product:update"
    PRODUCT_DELETE = "product:delete"

    # 客户管理
    CUSTOMER_VIEW = "customer:view"
    CUSTOMER_UPDATE = "customer:update"

    # 营销
    MARKETING_VIEW = "marketing:view"
    MARKETING_CREATE = "marketing:create"
    MARKETING_UPDATE = "marketing:update"
    MARKETING_SEND = "marketing:send"

    # 供应链
    SUPPLY_VIEW = "supply:view"
    SUPPLY_CREATE = "supply:create"
    SUPPLY_UPDATE = "supply:update"
    SUPPLY_PURCHASE = "supply:purchase"

    # 数据分析
    ANALYTICS_VIEW = "analytics:view"
    ANALYTICS_EXPORT = "analytics:export"

    # 系统管理
    SYSTEM_VIEW = "system:view"
    SYSTEM_CONFIG = "system:config"
    SYSTEM_USER = "system:user"
    SYSTEM_BACKUP = "system:backup"

    # AI Agent
    AGENT_VIEW = "agent:view"
    AGENT_RUN = "agent:run"
    AGENT_APPROVE = "agent:approve"


# 角色权限映射
ROLE_PERMISSIONS = {
    UserRole.ADMIN: ["*"],  # 全部权限
    UserRole.OPERATOR: [
        Permission.ORDER_VIEW, Permission.ORDER_CREATE, Permission.ORDER_UPDATE,
        Permission.PRODUCT_VIEW, Permission.PRODUCT_CREATE, Permission.PRODUCT_UPDATE,
        Permission.CUSTOMER_VIEW, Permission.CUSTOMER_UPDATE,
        Permission.MARKETING_VIEW, Permission.MARKETING_CREATE, Permission.MARKETING_UPDATE, Permission.MARKETING_SEND,
        Permission.SUPPLY_VIEW, Permission.SUPPLY_CREATE, Permission.SUPPLY_UPDATE, Permission.SUPPLY_PURCHASE,
        Permission.ANALYTICS_VIEW, Permission.ANALYTICS_EXPORT,
        Permission.AGENT_VIEW, Permission.AGENT_RUN, Permission.AGENT_APPROVE,
    ],
    UserRole.CUSTOMER_SERVICE: [
        Permission.ORDER_VIEW, Permission.ORDER_UPDATE, Permission.ORDER_REFUND,
        Permission.CUSTOMER_VIEW, Permission.CUSTOMER_UPDATE,
        Permission.PRODUCT_VIEW,
        Permission.AGENT_VIEW, Permission.AGENT_RUN,
    ],
    UserRole.VIEWER: [
        Permission.ORDER_VIEW,
        Permission.PRODUCT_VIEW,
        Permission.CUSTOMER_VIEW,
        Permission.MARKETING_VIEW,
        Permission.SUPPLY_VIEW,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.SYSTEM_VIEW,
    ],
}


class UserBase(BaseModel):
    """用户基础信息"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr | None = Field(None, description="邮箱")
    full_name: str | None = Field(None, max_length=100, description="全名")
    role: str = Field(UserRole.VIEWER, description="角色")
    is_active: bool = Field(True, description="是否启用")


class UserCreate(UserBase):
    """创建用户请求"""
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class UserUpdate(BaseModel):
    """更新用户请求"""
    email: EmailStr | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=6, max_length=128)


class UserLogin(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserResponse(UserBase):
    """用户响应（不包含密码）"""
    id: str
    created_at: datetime
    updated_at: datetime | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="过期时间（秒）")
    user: UserResponse


class TokenRefresh(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


class ChangePassword(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


class UserListResponse(BaseModel):
    """用户列表响应"""
    users: list[UserResponse]
    total: int
    page: int
    page_size: int
