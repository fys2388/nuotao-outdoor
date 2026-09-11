"""飞书审批服务 — 推送带批准/拒绝按钮的交互式卡片，接收回调并自动执行。

工作流程：
1. AI Agent 创建建议 → 自动推送飞书交互式卡片（带「批准」「拒绝」按钮）
2. 用户在飞书点击按钮 → 飞书向回调地址发送 POST 请求
3. 后端接收回调 → 更新建议状态（approved/rejected）
4. 已批准的建议 → 自动进入执行队列

配置要求：
- 飞书自建应用（不是群机器人），已开启「卡片」权限
- 回调地址配置：https://your-domain.com/api/v1/feishu/card-callback
- 环境变量：FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_WEBHOOK_URL
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

FEISHU_WEBHOOK_URL = os.getenv(
    "FEISHU_WEBHOOK_URL",
    "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371",
)
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_CHAT_ID = os.getenv("FEISHU_CHAT_ID", "")
FEISHU_CALLBACK_BASE_URL = os.getenv("FEISHU_CALLBACK_BASE_URL", "")

# 飞书消息推送时间限制（避免打扰用户休息）
PUSH_START_HOUR = int(os.getenv("FEISHU_PUSH_START_HOUR", "6"))   # 早上6点开始推送
PUSH_END_HOUR = int(os.getenv("FEISHU_PUSH_END_HOUR", "23"))       # 晚上11点停止推送

# 风险等级对应的卡片颜色
RISK_COLORS = {
    "low": "green",
    "medium": "orange",
    "high": "red",
}

# 建议类型对应的中文名称
SUGGESTION_TYPE_NAMES = {
    "product_optimization": "产品优化",
    "marketing_optimization": "营销优化",
    "inventory_restock": "库存补货",
    "pricing_adjustment": "价格调整",
    "listing_optimization": "上架优化",
    "customer_operation": "客户运营",
    "supply_chain": "供应链优化",
    "business_insight": "商业洞察",
}


def _is_within_push_hours() -> bool:
    """检查当前时间是否在允许推送的时间段内（默认 6:00-23:00）。"""
    now = datetime.now()
    current_hour = now.hour
    return PUSH_START_HOUR <= current_hour < PUSH_END_HOUR


def _get_tenant_access_token() -> str | None:
    """获取飞书 tenant_access_token（用于发送应用消息）。"""
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return None
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            return data.get("tenant_access_token")
        logger.warning("获取 tenant_access_token 失败: %s", data)
        return None
    except Exception as e:
        logger.error("获取 tenant_access_token 异常: %s", e)
        return None


def _send_card_via_app_api(card: dict[str, Any], chat_id: str | None = None) -> dict[str, Any]:
    """通过飞书自建应用 API 发送交互式卡片（支持按钮回调）。"""
    token = _get_tenant_access_token()
    if not token:
        return {"success": False, "error": "无法获取 tenant_access_token"}

    target_chat = chat_id or FEISHU_CHAT_ID
    if not target_chat:
        return {"success": False, "error": "FEISHU_CHAT_ID 未配置"}

    try:
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "receive_id": target_chat,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 0:
            message_id = data.get("data", {}).get("message_id", "")
            logger.info("自建应用 API 发送卡片成功: message_id=%s", message_id)
            return {"success": True, "message_id": message_id, "channel": "app_api"}
        logger.warning("自建应用 API 发送卡片失败: %s", data)
        return {"success": False, "error": data.get("msg", str(data))}
    except Exception as e:
        logger.error("自建应用 API 发送卡片异常: %s", e)
        return {"success": False, "error": str(e)}


def send_approval_card(
    *,
    suggestion_id: int,
    title: str,
    description: str,
    agent_name: str,
    suggestion_type: str,
    risk_level: str = "medium",
    execution_params: dict[str, Any] | None = None,
    webhook_url: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """发送带「批准」「拒绝」按钮的飞书交互式审批卡片。

    Args:
        suggestion_id: 建议 ID
        title: 建议标题
        description: 建议描述
        agent_name: 生成建议的 Agent 名称
        suggestion_type: 建议类型
        risk_level: 风险等级（low/medium/high）
        execution_params: 执行参数（展示在卡片中）
        webhook_url: 飞书 webhook URL（可选，降级用）
        chat_id: 飞书群 chat_id（可选，自建应用发送用）

    Returns:
        发送结果
    """
    # 推送时间限制（非推送时段不发送，避免打扰用户休息）
    if not _is_within_push_hours():
        logger.info(
            "当前时间不在推送时段（%d:00-%d:00），跳过发送审批卡片: suggestion_id=%s",
            PUSH_START_HOUR, PUSH_END_HOUR, suggestion_id,
        )
        return {"success": False, "skipped": True, "reason": "outside_push_hours"}

    url = webhook_url or FEISHU_WEBHOOK_URL
    type_name = SUGGESTION_TYPE_NAMES.get(suggestion_type, suggestion_type)
    color = RISK_COLORS.get(risk_level, "blue")

    # 构建执行参数摘要
    params_summary = ""
    if execution_params:
        lines = []
        for k, v in list(execution_params.items())[:5]:
            val_str = str(v)[:50]
            lines.append(f"**{k}**: {val_str}")
        params_summary = "\n" + "\n".join(lines)

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"🤖 AI 建议审批 | {type_name}"},
            "template": color,
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**标题**: {title[:60]}\n"
                        f"**来源 Agent**: {agent_name}\n"
                        f"**风险等级**: {risk_level.upper()}\n"
                        f"**建议 ID**: {suggestion_id}"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**建议内容**:\n{description[:300]}{params_summary}",
                },
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 批准并执行"},
                        "type": "primary",
                        "value": {"action": "approve", "suggestion_id": suggestion_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 拒绝"},
                        "type": "danger",
                        "value": {"action": "reject", "suggestion_id": suggestion_id},
                    },
                ],
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"点击按钮后自动回调处理 | 回调: {FEISHU_CALLBACK_BASE_URL or '未配置'}",
                    }
                ],
            },
        ],
    }

    # 优先通过自建应用 API 发送（支持按钮回调），失败则降级到 Webhook
    if FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_CHAT_ID:
        app_result = _send_card_via_app_api(card, chat_id=chat_id)
        if app_result.get("success"):
            return app_result
        logger.warning("自建应用 API 发送失败，降级到 Webhook: %s", app_result.get("error"))

    # 降级：通过 Webhook 发送（注意：Webhook 发送的卡片不支持按钮回调）
    try:
        payload = {"msg_type": "interactive", "card": card}
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 or data.get("StatusCode") == 0:
                logger.info("Webhook 发送审批卡片成功（注意：Webhook卡片不支持按钮回调）: suggestion_id=%s", suggestion_id)
                return {"success": True, "message_id": None, "channel": "webhook"}
        return {"success": False, "error": data.get("msg", str(data))}
    except Exception as e:
        logger.error("飞书审批卡片发送异常(Webhook): %s", e)
        return {"success": False, "error": str(e)}


def send_approval_result_notification(
    *,
    suggestion_id: int,
    title: str,
    action: str,
    operator: str = "飞书用户",
    webhook_url: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """发送审批结果通知（批准/拒绝后发送新消息通知）。

    优先通过自建应用 API 发送（统一用 Nuotao AI OS），失败则降级到 Webhook。
    """
    # 推送时间限制（非推送时段不发送结果通知）
    if not _is_within_push_hours():
        logger.info(
            "当前时间不在推送时段（%d:00-%d:00），跳过发送审批结果通知: suggestion_id=%s",
            PUSH_START_HOUR, PUSH_END_HOUR, suggestion_id,
        )
        return {"success": False, "skipped": True, "reason": "outside_push_hours"}

    action_text = "✅ 已批准并进入执行队列" if action == "approve" else "❌ 已拒绝"
    color = "green" if action == "approve" else "red"

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"审批结果 | {title[:30]}"},
            "template": color,
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**建议 ID**: {suggestion_id}\n"
                        f"**操作**: {action_text}\n"
                        f"**操作人**: {operator}\n"
                        f"**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                    ),
                },
            }
        ],
    }

    # 优先通过自建应用 API 发送（统一用 Nuotao AI OS）
    if FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_CHAT_ID:
        app_result = _send_card_via_app_api(card, chat_id=chat_id)
        if app_result.get("success"):
            return app_result
        logger.warning("自建应用 API 发送结果通知失败，降级到 Webhook: %s", app_result.get("error"))

    # 降级：通过 Webhook 发送
    url = webhook_url or FEISHU_WEBHOOK_URL
    try:
        payload = {"msg_type": "interactive", "card": card}
        resp = requests.post(url, json=payload, timeout=10)
        return {"success": resp.status_code == 200, "channel": "webhook"}
    except Exception as e:
        logger.error("发送审批结果通知失败: %s", e)
        return {"success": False, "error": str(e)}
def verify_feishu_request(headers: dict[str, str], body: dict[str, Any]) -> bool:
    """验证飞书回调请求的合法性（简化版，生产环境应验证签名）。"""
    # 飞书 URL 验证挑战
    if body.get("type") == "url_verification":
        return True
    # 卡片回调
    if body.get("header", {}).get("event_type") == "card.action.trigger":
        return True
    return False
