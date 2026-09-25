"""
工作流引擎 API 端点

Routes:
- GET  /api/v1/workflow/status           — 获取工作流引擎状态
- GET  /api/v1/workflow/nodes            — 获取节点定义
- POST /api/v1/workflow/instances        — 创建工作流实例
- GET  /api/v1/workflow/instances        — 列出工作流实例
- GET  /api/v1/workflow/instances/{id}   — 获取实例详情
- POST /api/v1/workflow/instances/{id}/start    — 启动实例
- POST /api/v1/workflow/instances/{id}/pause    — 暂停实例
- POST /api/v1/workflow/instances/{id}/resume   — 恢复实例
- POST /api/v1/workflow/instances/{id}/cancel   — 取消实例
- POST /api/v1/workflow/instances/{id}/nodes/{node_id}/complete — 完成节点
- POST /api/v1/workflow/instances/{id}/nodes/{node_id}/fail     — 失败节点
- POST /api/v1/workflow/instances/{id}/nodes/{node_id}/retry    — 重试节点
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.services.workflow_engine import (
    NODE_DEFINITIONS,
    WorkflowEngine,
    engine,
    get_workflow_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])


# ============================================
# 请求模型
# ============================================

class CreateInstanceRequest:
    """创建工作流实例请求"""
    pass


class NodeResultRequest:
    """节点结果请求"""
    pass


# ============================================
# API 端点
# ============================================

@router.get("/status", summary="获取工作流引擎状态")
async def get_status() -> dict[str, Any]:
    """获取工作流引擎状态、节点定义、状态枚举"""
    return get_workflow_status()


@router.get("/nodes", summary="获取节点定义")
async def get_nodes() -> dict[str, Any]:
    """获取所有节点定义"""
    return {
        "nodes": NODE_DEFINITIONS,
        "node_count": len(NODE_DEFINITIONS),
    }


@router.post("/instances", summary="创建工作流实例")
async def create_instance(
    product_info: dict[str, Any],
    workflow_type: str = "selection_to_wc",
    trigger_source: str = "manual",
) -> dict[str, Any]:
    """
    创建工作流实例
    
    Args:
        product_info: 商品信息
        workflow_type: 工作流类型
        trigger_source: 触发来源
    """
    try:
        instance = engine.create_instance(
            product_info=product_info,
            workflow_type=workflow_type,
            trigger_source=trigger_source,
        )
        return {
            "success": True,
            "instance": instance,
            "message": f"Instance created: {instance['id']}",
        }
    except Exception as e:
        logger.error("Create instance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create instance failed: {str(e)}",
        )


@router.get("/instances", summary="列出工作流实例")
async def list_instances(
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """
    列出工作流实例
    
    Args:
        status_filter: 状态过滤
        limit: 返回数量限制
        offset: 偏移量
    """
    try:
        result = engine.list_instances(
            status=status_filter,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            **result,
        }
    except Exception as e:
        logger.error("List instances failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List instances failed: {str(e)}",
        )


@router.get("/instances/{instance_id}", summary="获取实例详情")
async def get_instance(instance_id: str) -> dict[str, Any]:
    """
    获取工作流实例详情
    
    Args:
        instance_id: 实例ID
    """
    try:
        instance = engine.get_instance(instance_id)
        if not instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Instance not found: {instance_id}",
            )
        return {
            "success": True,
            "instance": instance,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get instance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get instance failed: {str(e)}",
        )


@router.post("/instances/{instance_id}/start", summary="启动实例")
async def start_instance(instance_id: str) -> dict[str, Any]:
    """启动工作流实例"""
    try:
        instance = engine.start_instance(instance_id)
        return {
            "success": True,
            "instance": instance,
            "message": "Instance started",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Start instance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Start instance failed: {str(e)}",
        )


@router.post("/instances/{instance_id}/pause", summary="暂停实例")
async def pause_instance(instance_id: str) -> dict[str, Any]:
    """暂停工作流实例"""
    try:
        instance = engine.pause_instance(instance_id)
        return {
            "success": True,
            "instance": instance,
            "message": "Instance paused",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Pause instance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pause instance failed: {str(e)}",
        )


@router.post("/instances/{instance_id}/resume", summary="恢复实例")
async def resume_instance(instance_id: str) -> dict[str, Any]:
    """恢复工作流实例"""
    try:
        instance = engine.resume_instance(instance_id)
        return {
            "success": True,
            "instance": instance,
            "message": "Instance resumed",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Resume instance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resume instance failed: {str(e)}",
        )


@router.post("/instances/{instance_id}/cancel", summary="取消实例")
async def cancel_instance(instance_id: str) -> dict[str, Any]:
    """取消工作流实例"""
    try:
        instance = engine.cancel_instance(instance_id)
        return {
            "success": True,
            "instance": instance,
            "message": "Instance cancelled",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Cancel instance failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cancel instance failed: {str(e)}",
        )


@router.post(
    "/instances/{instance_id}/nodes/{node_id}/complete",
    summary="完成节点",
)
async def complete_node(
    instance_id: str,
    node_id: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    完成节点
    
    Args:
        instance_id: 实例ID
        node_id: 节点ID
        result: 节点结果
    """
    try:
        instance = engine.complete_node(
            instance_id=instance_id,
            node_id=node_id,
            result=result,
        )
        return {
            "success": True,
            "instance": instance,
            "message": f"Node {node_id} completed",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Complete node failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Complete node failed: {str(e)}",
        )


@router.post(
    "/instances/{instance_id}/nodes/{node_id}/fail",
    summary="失败节点",
)
async def fail_node(
    instance_id: str,
    node_id: str,
    error: str = "Unknown error",
) -> dict[str, Any]:
    """
    失败节点
    
    Args:
        instance_id: 实例ID
        node_id: 节点ID
        error: 错误信息
    """
    try:
        instance = engine.fail_node(
            instance_id=instance_id,
            node_id=node_id,
            error=error,
        )
        return {
            "success": True,
            "instance": instance,
            "message": f"Node {node_id} failed",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Fail node failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fail node failed: {str(e)}",
        )


@router.post(
    "/instances/{instance_id}/nodes/{node_id}/retry",
    summary="重试节点",
)
async def retry_node(
    instance_id: str,
    node_id: str,
) -> dict[str, Any]:
    """
    重试节点
    
    Args:
        instance_id: 实例ID
        node_id: 节点ID
    """
    try:
        instance = engine.retry_node(
            instance_id=instance_id,
            node_id=node_id,
        )
        return {
            "success": True,
            "instance": instance,
            "message": f"Node {node_id} retried",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Retry node failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retry node failed: {str(e)}",
        )


# ============================================
# 集成端点 - 连接现有服务
# ============================================

@router.post("/instances/{instance_id}/run-selection", summary="运行选品节点")
async def run_selection_node(instance_id: str) -> dict[str, Any]:
    """
    运行选品节点 - 调用现有的选品服务
    
    这会调用现有的 product_pipeline_service 来运行选品分析
    """
    try:
        instance = engine.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        # 调用现有的选品服务
        from app.services.product_pipeline_service import analyze_and_generate_report
        
        product_info = instance.get("product_info", {})
        if not product_info:
            raise ValueError("Product info is empty")
        
        # 运行分析
        result = await analyze_and_generate_report(product_info)
        
        if result["success"]:
            # 完成节点
            instance = engine.complete_node(
                instance_id=instance_id,
                node_id="selection",
                result=result,
            )
            return {
                "success": True,
                "instance": instance,
                "node_result": result,
                "message": "Selection node completed",
            }
        else:
            # 失败节点
            instance = engine.fail_node(
                instance_id=instance_id,
                node_id="selection",
                error=result.get("error", "Analysis failed"),
            )
            return {
                "success": False,
                "instance": instance,
                "node_result": result,
                "message": "Selection node failed",
            }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Run selection node failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Run selection node failed: {str(e)}",
        )


@router.post("/instances/{instance_id}/run-listing", summary="运行上架节点")
async def run_listing_node(instance_id: str) -> dict[str, Any]:
    """
    运行上架节点 - 调用现有的产品上架服务
    """
    try:
        instance = engine.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        # 调用现有的产品上架服务
        from app.services.product_listing_service import list_to_woocommerce
        
        # 从实例中获取产品数据
        selection_result = instance.get("nodes", {}).get("selection", {}).get("result", {})
        if not selection_result:
            raise ValueError("Selection result not found, run selection first")
        
        # 调用上架服务
        result = await list_to_woocommerce(selection_result)
        
        if result.get("success"):
            # 完成节点
            instance = engine.complete_node(
                instance_id=instance_id,
                node_id="listing",
                result=result,
            )
            return {
                "success": True,
                "instance": instance,
                "node_result": result,
                "message": "Listing node completed",
            }
        else:
            # 失败节点
            instance = engine.fail_node(
                instance_id=instance_id,
                node_id="listing",
                error=result.get("error", "Listing failed"),
            )
            return {
                "success": False,
                "instance": instance,
                "node_result": result,
                "message": "Listing node failed",
            }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Run listing node failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Run listing node failed: {str(e)}",
        )