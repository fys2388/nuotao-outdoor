"""
后端性能优化中间件
- Redis 缓存
- 响应压缩
- 请求限流
- 数据库连接池优化
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from functools import wraps

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.redis import get_redis

settings = get_settings()


# ============================================
# 缓存装饰器
# ============================================
def cache(ttl: int = 60, key_prefix: str = "cache"):
    """
    Redis 缓存装饰器

    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀

    Usage:
        @cache(ttl=300, key_prefix="products")
        async def get_products():
            return await product_service.list_products()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            key_data = f"{func.__module__}:{func.__name__}:{args!s}:{sorted(kwargs.items())!s}"
            cache_key = f"{key_prefix}:{hashlib.md5(key_data.encode()).hexdigest()}"

            # 尝试从缓存获取
            try:
                redis = await get_redis()
                cached = await redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass  # 缓存不可用时降级到直接执行

            # 执行函数
            result = await func(*args, **kwargs)

            # 写入缓存
            try:
                redis = await get_redis()
                await redis.setex(cache_key, ttl, json.dumps(result, default=str))
            except Exception:
                pass

            return result
        return wrapper
    return decorator


# ============================================
# 缓存失效装饰器
# ============================================
def invalidate_cache(key_patterns: list[str]):
    """
    缓存失效装饰器，在函数执行后删除匹配的缓存键

    Args:
        key_patterns: 要删除的缓存键模式列表

    Usage:
        @invalidate_cache(["products:*", "product:*"])
        async def update_product(product_id: str, data: dict):
            return await product_service.update(product_id, data)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # 失效缓存
            try:
                redis = await get_redis()
                for pattern in key_patterns:
                    keys = await redis.keys(pattern)
                    if keys:
                        await redis.delete(*keys)
            except Exception:
                pass

            return result
        return wrapper
    return decorator


# ============================================
# 请求限流中间件
# ============================================
class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 Redis 的请求限流中间件"""

    def __init__(self, app: FastAPI, default_limit: int = 100, window: int = 60):
        super().__init__(app)
        self.default_limit = default_limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        # 跳过限流的路径
        skip_paths = ["/healthz", "/docs", "/openapi.json", "/metrics"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)

        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"

        # 限流键
        rate_key = f"rate_limit:{client_ip}:{request.url.path}"

        try:
            redis = await get_redis()
            current = await redis.incr(rate_key)
            if current == 1:
                await redis.expire(rate_key, self.window)

            if current > self.default_limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests", "retry_after": self.window}
                )
        except Exception:
            pass  # Redis 不可用时跳過限流

        response = await call_next(request)
        return response


# ============================================
# 响应时间中间件
# ============================================
class ResponseTimeMiddleware(BaseHTTPMiddleware):
    """记录响应时间的中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"
        return response


# ============================================
# 性能优化配置函数
# ============================================
def setup_performance_middleware(app: FastAPI):
    """
    配置所有性能优化中间件

    Args:
        app: FastAPI 应用实例
    """
    # Gzip 压缩
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 响应时间
    app.add_middleware(ResponseTimeMiddleware)

    # 请求限流（生产环境启用）
    if settings.ENVIRONMENT == "production":
        app.add_middleware(RateLimitMiddleware, default_limit=100, window=60)


# ============================================
# 数据库连接池优化配置
# ============================================
DATABASE_POOL_CONFIG = {
    "pool_size": 20,              # 连接池大小
    "max_overflow": 10,            # 最大溢出连接
    "pool_recycle": 3600,          # 连接回收时间（秒）
    "pool_pre_ping": True,          # 连接前 ping 检查
    "pool_timeout": 30,             # 获取连接超时（秒）
    "echo": False,                   # 是否打印 SQL
    "future": True,                  # 使用 SQLAlchemy 2.0 风格
}

# ============================================
# Redis 连接池配置
# ============================================
REDIS_POOL_CONFIG = {
    "max_connections": 50,          # 最大连接数
    "socket_timeout": 5,             # 套接字超时（秒）
    "socket_connect_timeout": 5,     # 连接超时（秒）
    "retry_on_timeout": True,        # 超时重试
    "health_check_interval": 30,     # 健康检查间隔（秒）
}
