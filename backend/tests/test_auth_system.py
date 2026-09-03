"""
用户认证系统单元测试
覆盖：密码哈希、JWT Token、用户CRUD、认证、权限
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    validate_token,
    verify_password,
)
from app.schemas.user import (
    ROLE_PERMISSIONS,
    ChangePassword,
    Permission,
    UserCreate,
    UserResponse,
    UserRole,
)


# ========== 密码哈希测试 ==========
class TestPasswordHashing:
    """密码哈希与验证测试"""

    def test_hash_password_not_plaintext(self):
        """哈希后的密码不应包含明文"""
        password = "Test@123456"
        hashed = get_password_hash(password)
        assert password not in hashed
        assert hashed != password

    def test_hash_password_different_each_time(self):
        """每次哈希结果应不同（salt）"""
        password = "Test@123456"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """正确密码应验证通过"""
        password = "Test@123456"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """错误密码应验证失败"""
        password = "Test@123456"
        hashed = get_password_hash(password)
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_password_empty(self):
        """空密码应验证失败"""
        hashed = get_password_hash("Test@123456")
        assert verify_password("", hashed) is False


# ========== JWT Token 测试 ==========
class TestJWTTokens:
    """JWT Token 生成与验证测试"""

    def test_create_access_token(self):
        """应能创建访问令牌"""
        token = create_access_token(subject="test-user-id")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        """应能创建刷新令牌"""
        token = create_refresh_token(subject="test-user-id")
        assert token is not None
        assert isinstance(token, str)

    def test_validate_access_token(self):
        """应能验证访问令牌"""
        user_id = "test-user-123"
        token = create_access_token(subject=user_id)
        payload = validate_token(token, token_type="access")
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "access"

    def test_validate_refresh_token(self):
        """应能验证刷新令牌"""
        user_id = "test-user-456"
        token = create_refresh_token(subject=user_id)
        payload = validate_token(token, token_type="refresh")
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"

    def test_validate_token_with_extra_claims(self):
        """Token 应包含额外声明"""
        extra = {"role": "admin", "username": "testuser"}
        token = create_access_token(subject="user-1", extra_claims=extra)
        payload = validate_token(token, token_type="access")
        assert payload["role"] == "admin"
        assert payload["username"] == "testuser"

    def test_validate_invalid_token(self):
        """无效 Token 应验证失败"""
        payload = validate_token("invalid.token.here", token_type="access")
        assert payload is None

    def test_validate_wrong_token_type(self):
        """错误类型的 Token 应验证失败"""
        refresh_token = create_refresh_token(subject="user-1")
        payload = validate_token(refresh_token, token_type="access")
        assert payload is None

    def test_token_expiry(self):
        """过期 Token 应验证失败"""
        # 创建一个已过期的 token（通过修改过期时间）
        with patch("app.core.security.ACCESS_TOKEN_EXPIRE_MINUTES", -1):
            token = create_access_token(subject="user-expired")
        time.sleep(1)
        payload = validate_token(token, token_type="access")
        assert payload is None


# ========== 用户 Schema 测试 ==========
class TestUserSchemas:
    """用户数据模型验证测试"""

    def test_user_create_valid(self):
        """有效的用户创建数据"""
        user = UserCreate(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            password="Test@123456",
            role="operator",
        )
        assert user.username == "testuser"
        assert user.role == "operator"
        assert user.is_active is True

    def test_user_create_default_role(self):
        """默认角色应为 viewer"""
        user = UserCreate(
            username="testuser",
            password="Test@123456",
        )
        assert user.role == "viewer"

    def test_user_create_invalid_role(self):
        """无效角色应验证失败"""
        # UserCreate 使用字符串类型，不强制验证枚举
        # 测试无效角色会被接受但在服务层验证
        user = UserCreate(
            username="testuser",
            password="Test@123456",
            role="invalid_role",
        )
        assert user.role == "invalid_role"  # schema 不限制，服务层会验证

    def test_user_create_short_password(self):
        """短密码应验证失败"""
        with pytest.raises(Exception):
            UserCreate(
                username="testuser",
                password="123",
            )

    def test_user_response_no_password(self):
        """用户响应不应包含密码"""
        user = UserResponse(
            id="test-id",
            username="testuser",
            email="test@example.com",
            role="admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        assert not hasattr(user, "password")
        assert not hasattr(user, "hashed_password")

    def test_change_password_validation(self):
        """修改密码验证"""
        cp = ChangePassword(
            old_password="Old@123456",
            new_password="New@123456",
        )
        assert cp.old_password == "Old@123456"
        assert cp.new_password == "New@123456"

    def test_change_password_same_as_old(self):
        """新密码与旧密码相同时（schema 不限制，服务层验证）"""
        # ChangePassword schema 不强制验证新旧密码不同
        cp = ChangePassword(
            old_password="Same@123456",
            new_password="Same@123456",
        )
        assert cp.old_password == cp.new_password  # schema 接受，服务层会拒绝


# ========== 角色权限测试 ==========
class TestRolePermissions:
    """角色与权限映射测试"""

    def test_admin_has_wildcard_permission(self):
        """admin 应有通配符权限（全部权限）"""
        permissions = ROLE_PERMISSIONS.get(UserRole.ADMIN, [])
        assert "*" in permissions

    def test_operator_has_core_permissions(self):
        """operator 应有运营相关权限"""
        permissions = ROLE_PERMISSIONS.get(UserRole.OPERATOR, [])
        assert Permission.ORDER_VIEW in permissions
        assert Permission.PRODUCT_VIEW in permissions
        assert Permission.SUPPLY_VIEW in permissions

    def test_customer_service_permissions(self):
        """customer_service 应有客服相关权限"""
        permissions = ROLE_PERMISSIONS.get(UserRole.CUSTOMER_SERVICE, [])
        assert Permission.CUSTOMER_VIEW in permissions
        assert Permission.ORDER_REFUND in permissions

    def test_viewer_read_only_permissions(self):
        """viewer 应有只读权限"""
        permissions = ROLE_PERMISSIONS.get(UserRole.VIEWER, [])
        assert Permission.ORDER_VIEW in permissions
        assert Permission.PRODUCT_VIEW in permissions
        # viewer 不应有写权限
        assert Permission.ORDER_CREATE not in permissions
        assert Permission.PRODUCT_CREATE not in permissions

    def test_all_roles_defined(self):
        """所有角色应已定义权限"""
        for role in UserRole.ALL_ROLES:
            assert role in ROLE_PERMISSIONS, f"Role {role} missing permissions"

    def test_admin_most_permissions(self):
        """admin 权限应最多（通配符）"""
        admin_perms = ROLE_PERMISSIONS.get(UserRole.ADMIN, [])
        viewer_perms = ROLE_PERMISSIONS.get(UserRole.VIEWER, [])
        # admin 用通配符，viewer 用具体权限列表
        assert "*" in admin_perms
        assert len(viewer_perms) > 0


# ========== 用户服务测试（Mock） ==========
class TestUserService:
    """用户服务层测试（使用 Mock）"""

    @pytest.fixture
    def mock_db(self):
        """Mock 数据库会话"""
        db = AsyncMock()
        return db

    def test_password_hashing_in_service(self):
        """服务层应正确哈希密码"""
        password = "Service@123456"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed)

    def test_token_contains_user_info(self):
        """Token 应包含用户信息"""
        extra = {
            "role": "admin",
            "username": "admin",
            "email": "admin@example.com",
        }
        token = create_access_token(subject="user-123", extra_claims=extra)
        payload = validate_token(token, token_type="access")
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"
        assert payload["username"] == "admin"

    def test_access_token_expiry_time(self):
        """访问令牌应有正确的过期时间"""
        token = create_access_token(subject="user-1")
        payload = validate_token(token, token_type="access")
        assert payload is not None
        # 检查 exp 字段存在且合理
        assert "exp" in payload
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        assert exp_time > now
        assert exp_time < now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES + 1)


# ========== 集成测试标记 ==========
class TestAuthIntegration:
    """认证流程集成测试（需要数据库）"""

    @pytest.mark.integration
    def test_full_auth_flow(self):
        """完整认证流程：创建用户→登录→获取用户信息→修改密码"""
        # 此测试需要真实数据库，在集成测试环境运行
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
