"""
缓存管理 API 端点
功能：
  1. 查看缓存统计（命中率、内存使用）
  2. 清除缓存（按 key、按前缀、全部）
  3. 查看缓存 key 列表
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import get_current_user
from app.core.cache_service import cache_service, CacheKeys
from app.schemas.user import UserResponse

router = APIRouter(prefix="/cache", tags=["缓存管理"])


@router.get("/stats", summary="获取缓存统计")
async def get_cache_stats(
    current_user: UserResponse = Depends(get_current_user),
):
    """获取缓存统计信息（命中率、内存使用等）"""
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="权限不足")

    stats = await cache_service.get_stats()
    return {
        "code": 0,
        "message": "success",
        "data": stats,
    }


@router.post("/clear", summary="清除缓存")
async def clear_cache(
    prefix: str | None = Query(None, description="按前缀清除，为空则清除全部"),
    current_user: UserResponse = Depends(get_current_user),
):
    """清除缓存（按前缀或全部）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可清除缓存")

    if prefix:
        count = await cache_service.delete_prefix(prefix)
        message = f"已清除 {count} 个以 '{prefix}' 开头的缓存键"
    else:
        await cache_service.clear_all()
        message = "已清除全部缓存"

    return {
        "code": 0,
        "message": message,
        "data": {"cleared": True, "prefix": prefix},
    }


@router.post("/reset-stats", summary="重置缓存统计")
async def reset_cache_stats(
    current_user: UserResponse = Depends(get_current_user),
):
    """重置缓存统计计数器"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可重置统计")

    await cache_service.reset_stats()
    return {
        "code": 0,
        "message": "缓存统计已重置",
        "data": {"reset": True},
    }


@router.get("/keys", summary="查看缓存键列表")
async def list_cache_keys(
    prefix: str = Query("*", description="键前缀匹配"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    current_user: UserResponse = Depends(get_current_user),
):
    """查看缓存键列表"""
    if current_user.role not in ["admin", "operator"]:
        raise HTTPException(status_code=403, detail="权限不足")

    try:
        keys = []
        async for key in cache_service.client.scan_iter(match=prefix, count=limit):
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            keys.append(key)
            if len(keys) >= limit:
                break

        return {
            "code": 0,
            "message": "success",
            "data": {
                "keys": keys,
                "count": len(keys),
                "prefix": prefix,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取缓存键失败: {str(e)}")


@router.delete("/{cache_key}", summary="删除指定缓存键")
async def delete_cache_key(
    cache_key: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """删除指定的缓存键"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除缓存")

    exists = await cache_service.exists(cache_key)
    if not exists:
        raise HTTPException(status_code=404, detail=f"缓存键 '{cache_key}' 不存在")

    await cache_service.delete(cache_key)
    return {
        "code": 0,
        "message": f"缓存键 '{cache_key}' 已删除",
        "data": {"deleted": True, "key": cache_key},
    }
