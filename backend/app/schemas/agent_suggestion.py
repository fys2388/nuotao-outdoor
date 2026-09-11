"""Agent 建议相关的 Pydantic schemas（API 出入参）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 创建
# --------------------------------------------------------------------------- #

class SuggestionCreate(BaseModel):
    """创建建议请求。"""
    agent_id: str = Field(..., description="生成建议的Agent ID", min_length=1, max_length=64)
    suggestion_type: str = Field(..., description="建议类型", min_length=1, max_length=32)
    title: str = Field(..., description="建议标题", min_length=1, max_length=256)
    description: str = Field(..., description="建议详细描述", min_length=1)
    execution_params: dict[str, Any] = Field(default_factory=dict, description="执行参数")
    execution_action: str | None = Field(None, description="执行动作标识", max_length=128)
    expected_impact: str | None = Field(None, description="预期影响")
    priority: str = Field("medium", description="优先级: high/medium/low")
    risk_level: str = Field("medium", description="风险等级: low/medium/high")
    agent_run_id: int | None = Field(None, description="关联的Agent运行记录ID")


# --------------------------------------------------------------------------- #
# 查询/过滤
# --------------------------------------------------------------------------- #

class SuggestionFilter(BaseModel):
    """建议列表过滤条件。"""
    status: str | None = Field(None, description="状态过滤")
    agent_id: str | None = Field(None, description="Agent ID过滤")
    suggestion_type: str | None = Field(None, description="类型过滤")
    priority: str | None = Field(None, description="优先级过滤")
    risk_level: str | None = Field(None, description="风险等级过滤")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class SuggestionUpdate(BaseModel):
    """更新建议请求（仅允许更新部分字段）。"""
    title: str | None = Field(None, max_length=256)
    description: str | None = None
    priority: str | None = None
    execution_params: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# 审批
# --------------------------------------------------------------------------- #

class ApproveRequest(BaseModel):
    """审批通过请求。"""
    approved_by: str = Field(..., description="审批人", min_length=1)
    comment: str | None = Field(None, description="审批意见")
    auto_execute: bool = Field(True, description="是否自动执行（仅低风险）")


class RejectRequest(BaseModel):
    """拒绝请求。"""
    rejected_by: str = Field(..., description="拒绝人", min_length=1)
    comment: str | None = Field(None, description="拒绝原因")


class SkipRequest(BaseModel):
    """跳过请求。"""
    skipped_by: str = Field(..., description="操作人", min_length=1)
    comment: str | None = Field(None, description="跳过原因")


# --------------------------------------------------------------------------- #
# 反馈
# --------------------------------------------------------------------------- #

class FeedbackRequest(BaseModel):
    """提交反馈请求。"""
    score: int = Field(..., ge=1, le=5, description="反馈评分 1-5")
    comment: str | None = Field(None, description="反馈意见")


# --------------------------------------------------------------------------- #
# 响应
# --------------------------------------------------------------------------- #

class SuggestionResponse(BaseModel):
    """建议响应。"""
    id: int
    agent_id: str
    agent_run_id: int | None = None
    suggestion_type: str
    title: str
    description: str
    expected_impact: str | None = None
    priority: str
    risk_level: str
    execution_params: dict[str, Any] = Field(default_factory=dict)
    execution_action: str | None = None
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_comment: str | None = None
    executed_at: datetime | None = None
    execution_result: dict[str, Any] = Field(default_factory=dict)
    execution_error: str | None = None
    feedback_score: int | None = None
    feedback_comment: str | None = None
    feedback_at: datetime | None = None
    learned: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SuggestionListResponse(BaseModel):
    """建议列表响应。"""
    items: list[SuggestionResponse]
    total: int
    limit: int
    offset: int


class PendingStatsResponse(BaseModel):
    """待审批统计响应。"""
    total: int
    by_type: dict[str, int] = Field(default_factory=dict)


class ExecutionResponse(BaseModel):
    """执行结果响应。"""
    success: bool
    action: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    suggestion_id: int | None = None


class FeedbackStatsResponse(BaseModel):
    """反馈统计响应。"""
    total_suggestions: int
    approval_rate: float
    execution_rate: float
    failure_rate: float
    avg_feedback_score: float
    by_type: dict[str, Any] = Field(default_factory=dict)
    by_agent: dict[str, Any] = Field(default_factory=dict)


class LearningSummaryResponse(BaseModel):
    """学习摘要响应。"""
    agent_id: str
    days: int
    summary: str
