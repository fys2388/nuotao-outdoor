"""
工作流引擎核心 - 流程化、职能化、智能化

核心能力：
1. 流程化 - 状态机驱动，节点流转，实例跟踪
2. 职能化 - 角色分工，职责分离，权限控制
3. 智能化 - AI决策，自动路由，智能评分

工作流节点：
- selection: 选品Agent - 商品采集、AI评分、风险识别
- editing: 编辑Agent - 产品信息编辑、文案优化、图片生成
- listing: 上架Agent - WooCommerce上架、数据校验
- sync: 同步Agent - WC同步、库存更新、状态回调
- review: 人工审核 - 节点间的人工确认点
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================
# 状态定义
# ============================================

class NodeStatus(str, Enum):
    """节点状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"


class InstanceStatus(str, Enum):
    """实例状态"""
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowType(str, Enum):
    """工作流类型"""
    SELECTION_TO_WC = "selection_to_wc"  # 选品到WC完整流程


# ============================================
# 节点定义
# ============================================

NODE_DEFINITIONS = {
    "selection": {
        "id": "selection",
        "name": "选品Agent",
        "description": "商品采集、AI评分、风险识别、候选推荐",
        "agent_role": "selection_manager",
        "auto_start": False,  # 需要手动触发
        "required": True,
        "next_nodes": ["editing"],
        "timeout_minutes": 30,
    },
    "editing": {
        "id": "editing",
        "name": "编辑Agent",
        "description": "产品信息编辑、文案优化、图片生成、描述生成",
        "agent_role": "content_editor",
        "auto_start": True,  # 选品完成后自动启动
        "required": True,
        "next_nodes": ["listing", "review"],
        "timeout_minutes": 60,
    },
    "listing": {
        "id": "listing",
        "name": "上架Agent",
        "description": "WooCommerce上架、数据校验、发布管理",
        "agent_role": "listing_manager",
        "auto_start": False,  # 需要人工确认
        "required": True,
        "next_nodes": ["sync"],
        "timeout_minutes": 30,
    },
    "sync": {
        "id": "sync",
        "name": "同步Agent",
        "description": "WC同步、库存更新、状态回调、双向同步",
        "agent_role": "sync_manager",
        "auto_start": True,  # 上架完成后自动启动
        "required": False,  # 可选
        "next_nodes": [],
        "timeout_minutes": 60,
    },
    "review": {
        "id": "review",
        "name": "人工审核",
        "description": "节点间人工确认点，支持暂停/继续/回退",
        "agent_role": "human_approver",
        "auto_start": False,  # 需要人工触发
        "required": False,  # 可选
        "next_nodes": ["listing", "sync"],
        "timeout_minutes": 1440,  # 24小时
    },
}


# ============================================
# 工作流引擎核心
# ============================================

class WorkflowEngine:
    """
    工作流引擎核心
    
    职责：
    1. 实例管理 - 创建、查询、更新工作流实例
    2. 节点流转 - 节点状态变更、路由决策
    3. 事件驱动 - 事件触发节点流转
    4. 持久化 - 实例状态持久化
    """
    
    def __init__(self):
        self.instances: dict[str, dict[str, Any]] = {}
        self.node_definitions = NODE_DEFINITIONS
        self.logger = logger
    
    def create_instance(
        self,
        product_info: dict[str, Any],
        workflow_type: str = "selection_to_wc",
        trigger_source: str = "manual",
    ) -> dict[str, Any]:
        """
        创建工作流实例
        
        Args:
            product_info: 商品信息
            workflow_type: 工作流类型
            trigger_source: 触发来源 (manual/api/cron)
        
        Returns:
            工作流实例
        """
        instance_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        instance = {
            "id": instance_id,
            "workflow_type": workflow_type,
            "status": InstanceStatus.CREATED.value,
            "current_node": "selection",
            "nodes": {},
            "product_info": product_info,
            "trigger_source": trigger_source,
            "created_at": now,
            "updated_at": now,
            "history": [],
            "metadata": {},
        }
        
        # 初始化节点状态
        for node_id, node_def in self.node_definitions.items():
            instance["nodes"][node_id] = {
                "id": node_id,
                "status": NodeStatus.PENDING.value,
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
                "retry_count": 0,
            }
        
        self.instances[instance_id] = instance
        
        # 记录历史
        self._record_history(instance, "instance_created", {
            "workflow_type": workflow_type,
            "trigger_source": trigger_source,
        })
        
        self.logger.info("Workflow instance created: %s", instance_id)
        return instance
    
    def get_instance(self, instance_id: str) -> dict[str, Any] | None:
        """获取工作流实例"""
        return self.instances.get(instance_id)
    
    def list_instances(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """列出工作流实例"""
        instances = list(self.instances.values())
        
        # 过滤
        if status:
            instances = [i for i in instances if i["status"] == status]
        
        # 分页
        total = len(instances)
        instances = instances[offset:offset + limit]
        
        return {
            "items": instances,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    
    def start_instance(self, instance_id: str) -> dict[str, Any]:
        """启动工作流实例"""
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        if instance["status"] != InstanceStatus.CREATED.value:
            raise ValueError(f"Instance cannot be started: {instance['status']}")
        
        instance["status"] = InstanceStatus.RUNNING.value
        instance["updated_at"] = datetime.now().isoformat()
        
        # 启动第一个节点
        first_node = instance["current_node"]
        self._start_node(instance, first_node)
        
        self._record_history(instance, "instance_started", {
            "first_node": first_node,
        })
        
        self.logger.info("Workflow instance started: %s", instance_id)
        return instance
    
    def pause_instance(self, instance_id: str) -> dict[str, Any]:
        """暂停工作流实例"""
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        instance["status"] = InstanceStatus.PAUSED.value
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "instance_paused", {})
        
        self.logger.info("Workflow instance paused: %s", instance_id)
        return instance
    
    def resume_instance(self, instance_id: str) -> dict[str, Any]:
        """恢复工作流实例"""
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        if instance["status"] != InstanceStatus.PAUSED.value:
            raise ValueError(f"Instance cannot be resumed: {instance['status']}")
        
        instance["status"] = InstanceStatus.RUNNING.value
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "instance_resumed", {})
        
        self.logger.info("Workflow instance resumed: %s", instance_id)
        return instance
    
    def cancel_instance(self, instance_id: str) -> dict[str, Any]:
        """取消工作流实例"""
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        instance["status"] = InstanceStatus.CANCELLED.value
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "instance_cancelled", {})
        
        self.logger.info("Workflow instance cancelled: %s", instance_id)
        return instance
    
    def complete_instance(self, instance_id: str) -> dict[str, Any]:
        """完成工作流实例"""
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        instance["status"] = InstanceStatus.COMPLETED.value
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "instance_completed", {})
        
        self.logger.info("Workflow instance completed: %s", instance_id)
        return instance
    
    def fail_instance(self, instance_id: str, error: str) -> dict[str, Any]:
        """失败工作流实例"""
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        instance["status"] = InstanceStatus.FAILED.value
        instance["updated_at"] = datetime.now().isoformat()
        instance["metadata"]["error"] = error
        
        self._record_history(instance, "instance_failed", {"error": error})
        
        self.logger.info("Workflow instance failed: %s", instance_id)
        return instance
    
    def _start_node(self, instance: dict[str, Any], node_id: str) -> None:
        """启动节点"""
        node = instance["nodes"].get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")
        
        node["status"] = NodeStatus.RUNNING.value
        node["started_at"] = datetime.now().isoformat()
        
        instance["current_node"] = node_id
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "node_started", {
            "node_id": node_id,
        })
    
    def complete_node(
        self,
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
        
        Returns:
            工作流实例
        """
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        node = instance["nodes"].get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")
        
        node["status"] = NodeStatus.COMPLETED.value
        node["completed_at"] = datetime.now().isoformat()
        node["result"] = result
        
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "node_completed", {
            "node_id": node_id,
            "result": result,
        })
        
        # 路由到下一个节点
        self._route_to_next_node(instance, node_id)
        
        return instance
    
    def fail_node(
        self,
        instance_id: str,
        node_id: str,
        error: str,
    ) -> dict[str, Any]:
        """
        失败节点
        
        Args:
            instance_id: 实例ID
            node_id: 节点ID
            error: 错误信息
        
        Returns:
            工作流实例
        """
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        node = instance["nodes"].get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")
        
        node["status"] = NodeStatus.FAILED.value
        node["error"] = error
        node["completed_at"] = datetime.now().isoformat()
        
        instance["status"] = InstanceStatus.FAILED.value
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "node_failed", {
            "node_id": node_id,
            "error": error,
        })
        
        return instance
    
    def retry_node(
        self,
        instance_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        """
        重试节点
        
        Args:
            instance_id: 实例ID
            node_id: 节点ID
        
        Returns:
            工作流实例
        """
        instance = self.get_instance(instance_id)
        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")
        
        node = instance["nodes"].get(node_id)
        if not node:
            raise ValueError(f"Node not found: {node_id}")
        
        if node["status"] != NodeStatus.FAILED.value:
            raise ValueError(f"Node cannot be retried: {node['status']}")
        
        node["status"] = NodeStatus.RUNNING.value
        node["started_at"] = datetime.now().isoformat()
        node["retry_count"] += 1
        node["error"] = None
        
        instance["status"] = InstanceStatus.RUNNING.value
        instance["current_node"] = node_id
        instance["updated_at"] = datetime.now().isoformat()
        
        self._record_history(instance, "node_retried", {
            "node_id": node_id,
            "retry_count": node["retry_count"],
        })
        
        return instance
    
    def _route_to_next_node(
        self,
        instance: dict[str, Any],
        current_node_id: str,
    ) -> None:
        """
        路由到下一个节点
        
        Args:
            instance: 工作流实例
            current_node_id: 当前节点ID
        """
        node_def = self.node_definitions.get(current_node_id)
        if not node_def:
            return
        
        next_nodes = node_def.get("next_nodes", [])
        if not next_nodes:
            # 没有下一个节点，完成实例
            self.complete_instance(instance["id"])
            return
        
        # 自动路由逻辑
        next_node_id = next_nodes[0]
        
        # 检查是否需要人工审核
        if next_node_id == "review":
            instance["status"] = InstanceStatus.PAUSED.value
            self._record_history(instance, "route_to_review", {
                "from_node": current_node_id,
                "to_node": next_node_id,
            })
            return
        
        # 自动启动下一个节点
        self._start_node(instance, next_node_id)
        
        self._record_history(instance, "route_next", {
            "from_node": current_node_id,
            "to_node": next_node_id,
        })
    
    def _record_history(
        self,
        instance: dict[str, Any],
        event: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """记录历史事件"""
        instance["history"].append({
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "data": data or {},
        })


# ============================================
# 全局实例
# ============================================

engine = WorkflowEngine()


# ============================================
# 辅助函数
# ============================================

def get_engine() -> WorkflowEngine:
    """获取工作流引擎实例"""
    return engine


def get_workflow_status() -> dict[str, Any]:
    """获取工作流引擎状态"""
    return {
        "service": "workflow_engine",
        "version": "1.0.0",
        "status": "operational",
        "nodes": {k: {"id": k, "name": v["name"]} for k, v in NODE_DEFINITIONS.items()},
        "node_statuses": [s.value for s in NodeStatus],
        "instance_statuses": [s.value for s in InstanceStatus],
    }