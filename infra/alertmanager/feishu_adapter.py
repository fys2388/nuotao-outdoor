"""
飞书告警通知适配器
接收 Alertmanager Webhook，转换为飞书消息格式并发送
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

import requests
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

# 配置
FEISHU_WEBHOOK_URL = os.getenv(
    "FEISHU_WEBHOOK_URL",
    "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371"
)

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="飞书告警适配器", version="1.0.0")


class Alert(BaseModel):
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: str
    endsAt: str = ""
    generatorURL: str = ""


class AlertmanagerWebhook(BaseModel):
    version: str
    groupKey: str
    status: str
    receiver: str
    groupLabels: Dict[str, str]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]
    externalURL: str
    alerts: List[Alert]


def get_severity_color(severity: str) -> str:
    """根据告警级别返回飞书卡片颜色"""
    color_map = {
        "critical": "red",
        "warning": "orange",
        "info": "blue",
        "none": "grey",
    }
    return color_map.get(severity.lower(), "blue")


def get_severity_emoji(severity: str) -> str:
    """根据告警级别返回 emoji"""
    emoji_map = {
        "critical": "🔴",
        "warning": "🟠",
        "info": "🔵",
        "none": "⚪",
    }
    return emoji_map.get(severity.lower(), "🔵")


def format_alert_message(alert: Alert) -> str:
    """格式化单条告警消息"""
    severity = alert.labels.get("severity", "info")
    emoji = get_severity_emoji(severity)
    alertname = alert.labels.get("alertname", "未知告警")
    instance = alert.labels.get("instance", "未知")
    description = alert.annotations.get("description", alert.annotations.get("summary", "无描述"))

    # 格式化时间
    try:
        start_time = datetime.fromisoformat(alert.startsAt.replace("Z", "+00:00"))
        start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    except:
        start_str = alert.startsAt

    message = f"""**{emoji} {alertname}**
**级别**: {severity.upper()}
**实例**: {instance}
**时间**: {start_str}
**描述**: {description}"""

    return message


def build_feishu_card(webhook: AlertmanagerWebhook) -> Dict[str, Any]:
    """构建飞书卡片消息"""
    status = webhook.status
    is_resolved = status == "resolved"

    # 获取最高告警级别
    severities = [alert.labels.get("severity", "info") for alert in webhook.alerts]
    highest_severity = "critical" if "critical" in severities else "warning" if "warning" in severities else "info"

    # 标题
    if is_resolved:
        title = f"✅ 告警已恢复 ({len(webhook.alerts)} 条)"
        template = "green"
    else:
        title = f"🚨 告警触发 ({len(webhook.alerts)} 条)"
        template = get_severity_color(highest_severity)

    # 构建卡片元素
    elements = []

    # 告警列表
    for i, alert in enumerate(webhook.alerts[:5]):  # 最多显示5条
        message = format_alert_message(alert)
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": message
            }
        })
        if i < min(len(webhook.alerts), 5) - 1:
            elements.append({"tag": "hr"})

    # 如果超过5条，显示省略
    if len(webhook.alerts) > 5:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"... 还有 {len(webhook.alerts) - 5} 条告警"
            }
        })

    # 分隔线
    elements.append({"tag": "hr"})

    # 底部信息
    group_labels = ", ".join([f"{k}={v}" for k, v in webhook.groupLabels.items()])
    elements.append({
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": f"分组: {group_labels} | 接收者: {webhook.receiver}"
            }
        ]
    })

    # 构建完整卡片
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": template
            },
            "elements": elements
        }
    }

    return card


def send_to_feishu(card: Dict[str, Any]) -> bool:
    """发送消息到飞书"""
    try:
        response = requests.post(
            FEISHU_WEBHOOK_URL,
            json=card,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        result = response.json()

        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info("飞书消息发送成功")
            return True
        else:
            logger.error(f"飞书消息发送失败: {result}")
            return False
    except Exception as e:
        logger.error(f"发送飞书消息异常: {e}")
        return False


@app.post("/webhook")
async def receive_alert(request: Request):
    """接收 Alertmanager Webhook"""
    try:
        body = await request.json()
        webhook = AlertmanagerWebhook(**body)

        logger.info(f"收到告警: status={webhook.status}, alerts={len(webhook.alerts)}")

        # 构建飞书卡片
        card = build_feishu_card(webhook)

        # 发送到飞书
        success = send_to_feishu(card)

        if success:
            return {"status": "ok", "message": "告警已发送到飞书"}
        else:
            raise HTTPException(status_code=500, detail="发送飞书消息失败")

    except Exception as e:
        logger.error(f"处理告警失败: {e}")
        raise HTTPException(status_code=400, detail=f"处理告警失败: {str(e)}")


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "service": "feishu-alert-adapter"}


@app.post("/test")
async def test_alert():
    """发送测试告警"""
    test_webhook = AlertmanagerWebhook(
        version="4",
        groupKey="test",
        status="firing",
        receiver="feishu",
        groupLabels={"alertname": "测试告警"},
        commonLabels={"severity": "warning"},
        commonAnnotations={"description": "这是一条测试告警消息"},
        externalURL="",
        alerts=[
            Alert(
                status="firing",
                labels={"alertname": "测试告警", "severity": "warning", "instance": "localhost:9090"},
                annotations={"description": "这是一条测试告警消息，用于验证飞书通知是否正常工作。"},
                startsAt=datetime.now().isoformat() + "Z",
                endsAt="",
                generatorURL=""
            )
        ]
    )

    card = build_feishu_card(test_webhook)
    success = send_to_feishu(card)

    if success:
        return {"status": "ok", "message": "测试告警已发送到飞书"}
    else:
        raise HTTPException(status_code=500, detail="发送测试告警失败")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8060)
