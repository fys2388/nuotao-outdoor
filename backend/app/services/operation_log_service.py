"""
操作日志服务层
使用PostgreSQL数据库存储，支持异步操作
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_log import OperationLog as OperationLogModel
from app.schemas.operation_log import OperationLog, OperationLogStatsResponse

logger = logging.getLogger(__name__)


def _model_to_schema(model: OperationLogModel) -> OperationLog:
    """将数据库模型转换为Pydantic schema"""
    return OperationLog(
        id=str(model.id),
        timestamp=model.created_at,
        user=model.operator,
        user_role="operator",
        action=model.operation_type,
        module=model.module,
        detail=model.description,
        ip_address=model.operator_ip or "",
        status=model.status,
        duration_ms=model.duration_ms,
    )


async def _ensure_initialized(db: AsyncSession) -> None:
    """确保日志已初始化（首次调用时生成模拟数据）"""
    result = await db.execute(select(func.count(OperationLogModel.id)))
    count = result.scalar() or 0

    if count == 0:
        # 生成模拟日志数据
        now = datetime.now()
        mock_data = [
            ("admin", "登录", "认证", "管理员登录系统", "192.168.1.1", "success", 120),
            ("joran", "创建订单", "订单管理", "创建订单 #ORD-2026-0905-001", "192.168.1.2", "success", 350),
            ("operator1", "更新商品", "产品管理", "更新商品 LED头灯 Pro 库存", "192.168.1.3", "success", 200),
            ("admin", "导出报表", "经营分析", "导出月度财务报表", "192.168.1.1", "success", 1500),
            ("operator2", "删除商品", "产品管理", "删除已下架商品 旧款头灯", "192.168.1.4", "failed", 80),
            ("joran", "审批采购单", "采购管理", "审批采购单 #PO-2026-0905-001", "192.168.1.2", "success", 420),
            ("admin", "修改设置", "系统设置", "修改低库存阈值为 15", "192.168.1.1", "success", 90),
            ("operator1", "同步库存", "库存管理", "同步1688供应商库存", "192.168.1.3", "success", 2800),
            ("joran", "生成周报", "经营分析", "AI生成第36周经营周报", "192.168.1.2", "success", 5200),
            ("admin", "异常登录检测", "安全", "检测到异常IP登录尝试", "10.0.0.99", "failed", None),
        ]

        for i, (user, action, module, detail, ip, status, duration) in enumerate(mock_data):
            log = OperationLogModel(
                operation_type=action,
                module=module,
                operator=user,
                operator_ip=ip,
                description=detail,
                status=status,
                duration_ms=duration,
                created_at=now - timedelta(minutes=i * 15),
            )
            db.add(log)

        await db.commit()
        logger.info("Initial mock operation logs created in database")


async def list_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    action_filter: Optional[str] = None,
    module_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    search_text: Optional[str] = None,
) -> tuple[list[OperationLog], int]:
    """获取操作日志列表（支持筛选和分页，从数据库）"""
    await _ensure_initialized(db)

    query = select(OperationLogModel)

    if action_filter and action_filter != "all":
        query = query.where(OperationLogModel.operation_type == action_filter)

    if module_filter and module_filter != "all":
        query = query.where(OperationLogModel.module == module_filter)

    if status_filter and status_filter != "all":
        query = query.where(OperationLogModel.status == status_filter)

    if search_text:
        search_lower = f"%{search_text.lower()}%"
        query = query.where(
            func.lower(OperationLogModel.operator).like(search_lower)
            | func.lower(OperationLogModel.operation_type).like(search_lower)
            | func.lower(OperationLogModel.module).like(search_lower)
            | func.lower(OperationLogModel.description).like(search_lower)
        )

    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    query = query.order_by(OperationLogModel.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    models = result.scalars().all()

    items = [_model_to_schema(model) for model in models]
    return items, total


async def get_log_stats(db: AsyncSession) -> OperationLogStatsResponse:
    """获取操作日志统计（从数据库）"""
    await _ensure_initialized(db)

    # 总数
    result = await db.execute(select(func.count(OperationLogModel.id)))
    total = result.scalar() or 0

    # 成功数
    result = await db.execute(
        select(func.count(OperationLogModel.id)).where(OperationLogModel.status == "success")
    )
    success_count = result.scalar() or 0
    success_rate = round((success_count / total * 100), 1) if total > 0 else 0.0

    # 安全告警（状态为failed且模块为安全）
    result = await db.execute(
        select(func.count(OperationLogModel.id)).where(
            OperationLogModel.status == "failed",
            OperationLogModel.module == "安全",
        )
    )
    security_alerts = result.scalar() or 0

    # 数据变更（创建、更新、删除操作）
    result = await db.execute(
        select(func.count(OperationLogModel.id)).where(
            OperationLogModel.operation_type.in_(["创建", "更新", "删除", "修改"])
        )
    )
    data_changes = result.scalar() or 0

    # 今日操作数
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(OperationLogModel.id)).where(
            OperationLogModel.created_at >= today_start
        )
    )
    today_operations = result.scalar() or 0

    # 失败操作数
    result = await db.execute(
        select(func.count(OperationLogModel.id)).where(OperationLogModel.status == "failed")
    )
    failed_operations = result.scalar() or 0

    return OperationLogStatsResponse(
        total_operations=total,
        success_rate=success_rate,
        security_alerts=security_alerts,
        data_changes=data_changes,
        today_operations=today_operations,
        failed_operations=failed_operations,
    )


async def add_log(
    db: AsyncSession,
    user: str,
    action: str,
    module: str,
    detail: str = "",
    ip_address: str = "",
    status: str = "success",
    duration_ms: Optional[int] = None,
    user_role: str = "operator",
) -> OperationLog:
    """添加操作日志（保存到数据库）"""
    log = OperationLogModel(
        operation_type=action,
        module=module,
        operator=user,
        operator_ip=ip_address or None,
        description=detail,
        status=status,
        duration_ms=duration_ms,
    )

    db.add(log)
    await db.commit()
    await db.refresh(log)

    logger.info("Operation log added to database: %s - %s - %s", user, action, module)
    return _model_to_schema(log)
