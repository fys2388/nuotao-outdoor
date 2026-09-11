"""
部署服务 API 端点
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.deployment_service import (
    check_all_services,
    check_service_health,
    generate_deployment_guide,
    generate_linux_systemd_config,
    generate_nginx_config,
    generate_windows_startup_script,
    get_deployment_status,
    get_system_info,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deployment", tags=["deployment"])


@router.get("/status")
async def status() -> dict[str, Any]:
    """获取部署状态"""
    try:
        return get_deployment_status()
    except Exception as e:
        logger.exception("Get deployment status failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Get deployment status failed: {e!s}")


@router.get("/system-info")
async def system_info() -> dict[str, Any]:
    """获取系统信息"""
    return get_system_info()


@router.get("/services/health")
async def services_health() -> dict[str, Any]:
    """检查所有服务健康状态"""
    return check_all_services()


@router.get("/services/{service_name}/health")
async def service_health(service_name: str) -> dict[str, Any]:
    """检查指定服务健康状态"""
    result = check_service_health(service_name)
    if not result.get("success", True) and "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/config/nginx")
async def nginx_config() -> dict[str, Any]:
    """获取 Nginx 配置"""
    return {
        "success": True,
        "config": generate_nginx_config(),
        "description": "Nginx 反向代理配置，适用于本地生产环境和云服务器部署",
    }


@router.get("/config/windows-startup")
async def windows_startup_script() -> dict[str, Any]:
    """获取 Windows 自启动脚本"""
    return {
        "success": True,
        "script": generate_windows_startup_script(),
        "description": "Windows 自启动脚本，放入 shell:startup 文件夹即可开机自启",
    }


@router.get("/config/linux-systemd")
async def linux_systemd_config() -> dict[str, Any]:
    """获取 Linux systemd 服务配置"""
    return {
        "success": True,
        "config": generate_linux_systemd_config(),
        "description": "Linux systemd 服务配置，适用于云服务器部署",
    }


@router.get("/guide/cloud-deployment")
async def cloud_deployment_guide() -> dict[str, Any]:
    """获取云服务器部署指南"""
    return {
        "success": True,
        "guide": generate_deployment_guide(),
        "description": "云服务器部署完整指南，包含服务器要求、部署步骤、SSL配置、监控维护等",
    }
