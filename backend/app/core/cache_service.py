"""
Redis 缓存服务模块
功能：
  1. 缓存客户端（连接池、序列化）
  2. 缓存装饰器（函数结果缓存）
  3. 缓存失效（按 key、按前缀、全部清除）
  4. 缓存统计（命中率、内存使用）
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from datetime import timedelta
from typing import Any, Callable, Optional

import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger("cache_service")

# 全局缓存统计
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "errors": 0,
    "total_requests": 0,
}


class CacheService:
    """Redis 缓存服务"""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.redis_url
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = None
        self._enabled = settings.cache_enabled

    @property
    def client(self) -> aioredis.Redis:
        """获取 Redis 客户端（懒加载）"""
        if self._client is None:
            self._pool = aioredis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=settings.cache_max_connections,
                decode_responses=False,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
        return self._client

    async def initialize(self):
        """初始化连接池"""
        if not self._enabled:
            logger.info("Cache disabled, skipping initialization")
            return
        try:
            await self.client.ping()
            logger.info("Cache service initialized: %s", self.redis_url)
        except Exception as e:
            logger.warning("Cache initialization failed: %s", e)
            self._enabled = False

    async def close(self):
        """关闭连接"""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    def _serialize(self, value: Any) -> bytes:
        """序列化值"""
        if isinstance(value, bytes):
            return value
        return json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")

    def _deserialize(self, value: bytes | None) -> Any:
        """反序列化值"""
        if value is None:
            return None
        try:
            return json.loads(value.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return value

    async def get(self, key: str) -> Any:
        """获取缓存值"""
        _cache_stats["total_requests"] += 1
        if not self._enabled:
            _cache_stats["misses"] += 1
            return None

        try:
            value = await self.client.get(key)
            if value is not None:
                _cache_stats["hits"] += 1
                return self._deserialize(value)
            _cache_stats["misses"] += 1
            return None
        except Exception as e:
            _cache_stats["errors"] += 1
            logger.warning("Cache get error for key %s: %s", key, e)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | timedelta | None = None,
    ) -> bool:
        """设置缓存值"""
        if not self._enabled:
            return False

        try:
            serialized = self._serialize(value)
            if ttl is not None:
                if isinstance(ttl, timedelta):
                    ttl = int(ttl.total_seconds())
                await self.client.setex(key, ttl, serialized)
            else:
                await self.client.set(key, serialized)
            return True
        except Exception as e:
            logger.warning("Cache set error for key %s: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存值"""
        if not self._enabled:
            return False

        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.warning("Cache delete error for key %s: %s", key, e)
            return False

    async def delete_prefix(self, prefix: str) -> int:
        """按前缀删除缓存"""
        if not self._enabled:
            return 0

        try:
            count = 0
            async for key in self.client.scan_iter(match=f"{prefix}*"):
                await self.client.delete(key)
                count += 1
            logger.info("Deleted %d keys with prefix %s", count, prefix)
            return count
        except Exception as e:
            logger.warning("Cache delete_prefix error: %s", e)
            return 0

    async def clear_all(self) -> bool:
        """清除所有缓存"""
        if not self._enabled:
            return False

        try:
            await self.client.flushdb()
            logger.info("All cache cleared")
            return True
        except Exception as e:
            logger.warning("Cache clear_all error: %s", e)
            return False

    async def exists(self, key: str) -> bool:
        """检查 key 是否存在"""
        if not self._enabled:
            return False
        try:
            return await self.client.exists(key) > 0
        except Exception:
            return False

    async def expire(self, key: str, ttl: int | timedelta) -> bool:
        """设置过期时间"""
        if not self._enabled:
            return False
        try:
            if isinstance(ttl, timedelta):
                ttl = int(ttl.total_seconds())
            await self.client.expire(key, ttl)
            return True
        except Exception:
            return False

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | timedelta | None = None,
    ) -> Any:
        """获取或设置缓存（常用模式）"""
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = factory()
        if asyncio.iscoroutine(value):
            value = await value

        await self.set(key, value, ttl)
        return value

    async def get_stats(self) -> dict:
        """获取缓存统计"""
        stats = dict(_cache_stats)
        if stats["total_requests"] > 0:
            stats["hit_rate"] = round(stats["hits"] / stats["total_requests"] * 100, 2)
        else:
            stats["hit_rate"] = 0.0

        # Redis 内存使用
        try:
            if self._enabled and self._client:
                info = await self.client.info("memory")
                stats["redis_memory_used_bytes"] = info.get("used_memory", 0)
                stats["redis_memory_used_human"] = info.get("used_memory_human", "0B")
        except Exception:
            pass

        return stats

    async def reset_stats(self):
        """重置统计"""
        for key in _cache_stats:
            _cache_stats[key] = 0


# 全局缓存服务实例
cache_service = CacheService()


def cached(
    ttl: int = 300,
    key_prefix: str = "cache",
    include_args: bool = True,
):
    """
    缓存装饰器
    用法：
        @cached(ttl=300, key_prefix="products")
        async def get_product(product_id: str):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache_service._enabled:
                return await func(*args, **kwargs)

            # 生成缓存 key
            key_parts = [key_prefix, func.__name__]
            if include_args:
                key_parts.extend(str(a) for a in args[1:])  # 跳过 self
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            # 尝试从缓存获取
            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                return cached_value

            # 执行函数
            result = await func(*args, **kwargs)

            # 写入缓存
            await cache_service.set(cache_key, result, ttl=ttl)

            return result
        return wrapper
    return decorator


def invalidate_cache(
    key_prefix: str | None = None,
    exact_key: str | None = None,
):
    """
    缓存失效装饰器（在函数执行后清除缓存）
    用法：
        @invalidate_cache(key_prefix="products")
        async def update_product(product_id: str, data: dict):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # 清除缓存
            if exact_key:
                await cache_service.delete(exact_key)
            if key_prefix:
                await cache_service.delete_prefix(key_prefix)

            return result
        return wrapper
    return decorator


# 常用缓存 key 前缀定义
class CacheKeys:
    """缓存 key 前缀常量"""
    PRODUCT = "product"
    PRODUCT_LIST = "product:list"
    ORDER = "order"
    ORDER_LIST = "order:list"
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    AGENT_RESULT = "agent:result"
    WOOCOMMERCE = "woocommerce"
    CONFIG = "config"
    USER = "user"


# 常用 TTL 定义（秒）
class CacheTTL:
    """缓存 TTL 常量（秒）"""
    SHORT = 60          # 1 分钟（频繁变化数据）
    MEDIUM = 300        # 5 分钟（默认）
    LONG = 1800         # 30 分钟（相对稳定数据）
    VERY_LONG = 86400   # 24 小时（配置、静态数据）
    SESSION = 7200      # 2 小时（用户会话）
