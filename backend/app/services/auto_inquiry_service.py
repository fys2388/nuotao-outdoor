"""
自动询盘服务

在订单创建后，自动根据采购单中的1688商品映射触发批量询盘。
询盘内容包括：采购数量、价格确认、交期、物流方式等。

遵循AGENTS.md规范：
- 业务规则集中在服务层
- 外部调用有超时、重试、降级
- 全链路可审计
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
INQUIRY_LOG_FILE = os.path.join(DATA_DIR, "auto_inquiry_log.json")

# 询盘策略配置
INQUIRY_STRATEGIES = {
    "spot": {
        "name": "现货采购",
        "questions": [
            "确认当前库存数量，是否有现货？",
            "确认采购{quantity}个的单价和总价",
            "确认发货时间和物流方式",
            "是否支持一件代发/小包直邮？",
        ],
    },
    "custom": {
        "name": "定制采购",
        "questions": [
            "是否支持定制LOGO/包装？起订量多少？",
            "打样周期和打样费用？",
            "大货生产周期？",
            "阶梯报价：100/500/1000个分别什么价格？",
        ],
    },
    "standard": {
        "name": "标准询盘",
        "questions": [
            "确认商品规格、材质、尺寸",
            "采购{quantity}个的单价？",
            "最小起订量和交期？",
            "支持的付款方式和物流渠道？",
        ],
    },
}


def _ensure_data_dir() -> None:
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_inquiry_log() -> list[dict[str, Any]]:
    """加载询盘日志"""
    if not os.path.exists(INQUIRY_LOG_FILE):
        return []
    try:
        with open(INQUIRY_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("加载询盘日志失败: %s", str(e))
        return []


def _save_inquiry_log(logs: list[dict[str, Any]]) -> None:
    """保存询盘日志（保留最近100条）"""
    _ensure_data_dir()
    recent = logs[-100:] if len(logs) > 100 else logs
    try:
        with open(INQUIRY_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error("保存询盘日志失败: %s", str(e))


def build_inquiry_message(
    purchase_order: dict[str, Any],
    strategy: str = "standard",
) -> str:
    """
    根据采购单构建询盘消息

    Args:
        purchase_order: 采购单数据
        strategy: 询盘策略（spot/custom/standard）

    Returns:
        询盘消息文本
    """
    items = purchase_order.get("items", [])
    if not items:
        return ""

    strategy_config = INQUIRY_STRATEGIES.get(strategy, INQUIRY_STRATEGIES["standard"])
    total_quantity = sum(item.get("quantity", 1) for item in items)

    # 构建商品列表
    product_lines = []
    for i, item in enumerate(items, 1):
        product_lines.append(
            f"{i}. 商品ID: {item.get('ali1688_product_id', 'N/A')}, "
            f"名称: {item.get('woo_name', 'N/A')}, "
            f"数量: {item.get('quantity', 1)}个, "
            f"参考单价: ¥{item.get('unit_cost', 0)}"
        )

    # 构建问题列表
    questions = []
    for q in strategy_config["questions"]:
        questions.append(f"- {q.format(quantity=total_quantity)}")

    message = (
        f"您好，我有以下采购需求，请帮忙报价：\n\n"
        f"【采购商品】\n"
        f"{chr(10).join(product_lines)}\n\n"
        f"【采购信息】\n"
        f"- 订单号: {purchase_order.get('wc_order_number', 'N/A')}\n"
        f"- 总数量: {total_quantity}个\n"
        f"- 预计总成本: ¥{purchase_order.get('total_cost', 0)}\n\n"
        f"【需要确认】\n"
        f"{chr(10).join(questions)}\n\n"
        f"请尽快回复，谢谢！"
    )

    return message


def extract_product_ids(purchase_order: dict[str, Any]) -> list[str]:
    """
    从采购单中提取1688商品ID列表

    Args:
        purchase_order: 采购单数据

    Returns:
        1688商品ID列表
    """
    items = purchase_order.get("items", [])
    product_ids = []
    for item in items:
        pid = item.get("ali1688_product_id", "")
        if pid and str(pid).strip():
            product_ids.append(str(pid).strip())
    return product_ids


def trigger_auto_inquiry(
    purchase_order: dict[str, Any],
    strategy: str = "standard",
    auto: bool = True,
) -> dict[str, Any]:
    """
    触发自动批量询盘

    在订单创建后自动调用，向采购单中的1688供应商发起询盘。

    Args:
        purchase_order: 采购单数据
        strategy: 询盘策略（spot/custom/standard）
        auto: 是否自动执行（True=自动，False=仅生成询盘草稿）

    Returns:
        询盘结果，包含：
        - success: 是否成功
        - strategy: 使用的策略
        - product_ids: 询盘的商品ID列表
        - product_count: 商品数量
        - inquiry_message: 询盘消息
        - task_id: 牛顿Agent任务ID（如果执行）
        - result: 牛顿Agent返回结果
        - error: 错误信息（如果失败）
    """
    po_id = purchase_order.get("purchase_order_id", "unknown")
    product_ids = extract_product_ids(purchase_order)

    result: dict[str, Any] = {
        "success": False,
        "purchase_order_id": po_id,
        "strategy": strategy,
        "product_ids": product_ids,
        "product_count": len(product_ids),
        "inquiry_message": "",
        "task_id": None,
        "result": None,
        "error": None,
        "triggered_at": datetime.now().isoformat(),
        "auto": auto,
    }

    # 检查是否有可询盘的商品
    if not product_ids:
        result["error"] = "采购单中没有映射到1688商品，无法自动询盘"
        logger.warning("自动询盘跳过: 采购单%s没有1688商品映射", po_id)
        _log_inquiry(result)
        return result

    # 构建询盘消息
    inquiry_message = build_inquiry_message(purchase_order, strategy)
    result["inquiry_message"] = inquiry_message

    if not auto:
        # 仅生成询盘草稿，不实际执行
        result["success"] = True
        result["note"] = "询盘草稿已生成，未自动执行"
        logger.info("询盘草稿已生成: 采购单%s, %d个商品", po_id, len(product_ids))
        _log_inquiry(result)
        return result

    # 调用牛顿Agent批量询盘
    try:
        from app.services.newton_agent_service import batch_inquiry, is_configured

        if not is_configured():
            result["error"] = "牛顿Agent未配置，无法自动询盘"
            logger.warning("自动询盘跳过: 牛顿Agent未配置")
            _log_inquiry(result)
            return result

        inquiry_result = batch_inquiry(
            product_ids=product_ids,
            inquiry_message=inquiry_message,
        )

        if inquiry_result.get("success"):
            result["success"] = True
            result["task_id"] = inquiry_result.get("task_id")
            result["result"] = inquiry_result
            logger.info(
                "自动询盘成功: 采购单%s, %d个商品, 任务ID=%s",
                po_id, len(product_ids), result["task_id"],
            )
        else:
            result["error"] = inquiry_result.get("error", "批量询盘失败")
            logger.error("自动询盘失败: 采购单%s, %s", po_id, result["error"])

    except Exception as e:
        result["error"] = f"调用牛顿Agent异常: {str(e)}"
        logger.exception("自动询盘异常: 采购单%s", po_id)

    _log_inquiry(result)
    return result


def _log_inquiry(result: dict[str, Any]) -> None:
    """记录询盘到日志"""
    logs = _load_inquiry_log()
    logs.append(result)
    _save_inquiry_log(logs)


def get_inquiry_history(
    purchase_order_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    查询自动询盘历史

    Args:
        purchase_order_id: 采购单ID（可选，不传则返回全部）
        limit: 返回条数限制

    Returns:
        询盘历史记录列表（按时间倒序）
    """
    logs = _load_inquiry_log()

    if purchase_order_id:
        logs = [log for log in logs if log.get("purchase_order_id") == purchase_order_id]

    # 按时间倒序
    logs.sort(key=lambda x: x.get("triggered_at", ""), reverse=True)
    return logs[:limit]


def get_inquiry_stats() -> dict[str, Any]:
    """
    获取自动询盘统计

    Returns:
        统计信息
    """
    logs = _load_inquiry_log()
    total = len(logs)
    success = sum(1 for log in logs if log.get("success"))
    failed = total - success
    auto_count = sum(1 for log in logs if log.get("auto"))
    draft_count = total - auto_count

    # 按策略统计
    strategy_stats: dict[str, int] = {}
    for log in logs:
        strategy = log.get("strategy", "unknown")
        strategy_stats[strategy] = strategy_stats.get(strategy, 0) + 1

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "success_rate": round(success / total * 100, 1) if total > 0 else 0,
        "auto_executed": auto_count,
        "draft_only": draft_count,
        "by_strategy": strategy_stats,
    }
