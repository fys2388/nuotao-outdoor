"""成长记忆审核端点 — 待审核记忆列表 / 审批通过 / 拒绝 / 统计。

对应 P1-6「记忆置信度人工审核流程」：低置信度记忆置为 pending_review，
由本端点人工审核后（active / archived）才决定是否注入 Agent 上下文。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.growth_memory import GrowthMemory
from app.services import growth_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["growth-memory"])

DbSession = AsyncSession


def _memory_out(m) -> dict[str, Any]:
    return {
        "id": m.id,
        "agent_id": m.agent_id,
        "memory_type": m.memory_type,
        "title": m.title,
        "content": m.content,
        "summary": m.summary,
        "tags": m.tags,
        "source": m.source,
        "source_id": m.source_id,
        "confidence": m.confidence,
        "status": m.status,
        "access_count": m.access_count,
        "useful_count": m.useful_count,
        "metadata": m.metadata_ or {},
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/memories")
async def list_memories(
    status: str | None = Query(None, description="active/archived/pending_review"),
    agent_id: str | None = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """按状态列出记忆；status=pending_review 走人工审核队列。"""
    if status == "pending_review":
        memories = await growth_memory_service.list_pending_review(
            db, agent_id=agent_id, limit=limit
        )
    else:
        stmt = select(GrowthMemory).order_by(GrowthMemory.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(GrowthMemory.status == status)
        if agent_id:
            stmt = stmt.where(GrowthMemory.agent_id == agent_id)
        result = await db.execute(stmt)
        memories = list(result.scalars().all())
    return {"items": [_memory_out(m) for m in memories], "total": len(memories)}


@router.get("/memories/stats")
async def memory_stats(
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """记忆统计（含 pending_review 数量）。"""
    return await growth_memory_service.get_memory_stats(db, agent_id=agent_id)


@router.post("/memories/{memory_id}/approve")
async def approve_memory(
    memory_id: int,
    approved_by: str = "user",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """人工审核通过：状态置 active，置信度提升至 >=0.7。"""
    memory = await growth_memory_service.approve_memory(
        db, memory_id, approved_by=approved_by
    )
    if memory is None:
        raise HTTPException(status_code=404, detail=f"记忆不存在: {memory_id}")
    return _memory_out(memory)


@router.post("/memories/{memory_id}/reject")
async def reject_memory(
    memory_id: int,
    rejected_by: str = "user",
    reason: str = "",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """人工审核拒绝：归档（不再注入上下文）。"""
    memory = await growth_memory_service.reject_memory(
        db, memory_id, rejected_by=rejected_by, reason=reason
    )
    if memory is None:
        raise HTTPException(status_code=404, detail=f"记忆不存在: {memory_id}")
    return _memory_out(memory)
