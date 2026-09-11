"""
Nuotao AI OS - 系统监控与告警服务
功能：
  1. 系统资源监控（CPU、内存、磁盘、网络）
  2. 服务健康检查（后端API、PostgreSQL、Redis、前端）
  3. 阈值告警（飞书通知）
  4. 监控数据记录（JSON文件）
  5. 告警去重（同一问题30分钟内只告警一次）
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import requests

# ========== 配置 ==========
CONFIG = {
    # 监控间隔（秒）
    "check_interval": 60,
    # 告警阈值
    "thresholds": {
        "cpu_percent": 85,
        "memory_percent": 85,
        "disk_percent": 90,
        "api_response_time_ms": 5000,
    },
    # 服务健康检查
    "services": {
        "backend_api": "http://localhost:8000/docs",
        "frontend": "http://localhost:3000",
        "postgres": "localhost:5432",
        "redis": "localhost:6379",
    },
    # 飞书 Webhook
    "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/1035e5f2-8984-44d1-83f4-9fb60f274371",
    # 告警去重时间（秒）
    "alert_dedup_seconds": 1800,
    # 数据目录
    "data_dir": "E:/AI/nuotao-ai-os/backups/monitoring",
}

# ========== 初始化 ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("monitor")

data_dir = Path(CONFIG["data_dir"])
data_dir.mkdir(parents=True, exist_ok=True)

alert_history_file = data_dir / "alert_history.json"
metrics_file = data_dir / "metrics.json"

# 告警历史（用于去重）
alert_history: dict[str, float] = {}


def load_alert_history() -> None:
    """加载告警历史"""
    global alert_history
    if alert_history_file.exists():
        try:
            alert_history = json.loads(alert_history_file.read_text(encoding="utf-8"))
        except Exception:
            alert_history = {}


def save_alert_history() -> None:
    """保存告警历史"""
    try:
        alert_history_file.write_text(json.dumps(alert_history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save alert history: %s", e)


def send_feishu_alert(title: str, message: str, color: str = "red") -> None:
    """发送飞书告警通知"""
    alert_key = f"{title}:{message[:50]}"
    now = time.time()

    # 告警去重
    if alert_key in alert_history:
        if now - alert_history[alert_key] < CONFIG["alert_dedup_seconds"]:
            logger.info("Alert deduplicated: %s", title)
            return

    alert_history[alert_key] = now
    save_alert_history()

    try:
        body = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "plain_text", "content": message},
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 主机: {socket.gethostname()}"}
                        ],
                    },
                ],
            },
        }
        requests.post(
            CONFIG["feishu_webhook"],
            json=body,
            timeout=10,
        )
        logger.info("Feishu alert sent: %s", title)
    except Exception as e:
        logger.warning("Failed to send feishu alert: %s", e)


def check_system_resources() -> dict[str, Any]:
    """检查系统资源"""
    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "cpu": {
            "percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
            "percent": psutil.virtual_memory().percent,
        },
        "disk": {
            "total_gb": round(psutil.disk_usage("/").total / (1024**3), 2),
            "used_gb": round(psutil.disk_usage("/").used / (1024**3), 2),
            "percent": psutil.disk_usage("/").percent,
        },
        "network": {
            "bytes_sent_mb": round(psutil.net_io_counters().bytes_sent / (1024**2), 2),
            "bytes_recv_mb": round(psutil.net_io_counters().bytes_recv / (1024**2), 2),
        },
    }

    # 阈值检查
    thresholds = CONFIG["thresholds"]
    alerts = []

    if metrics["cpu"]["percent"] > thresholds["cpu_percent"]:
        alerts.append(f"CPU 使用率过高: {metrics['cpu']['percent']}% (阈值: {thresholds['cpu_percent']}%)")

    if metrics["memory"]["percent"] > thresholds["memory_percent"]:
        alerts.append(f"内存使用率过高: {metrics['memory']['percent']}% (阈值: {thresholds['memory_percent']}%)")

    if metrics["disk"]["percent"] > thresholds["disk_percent"]:
        alerts.append(f"磁盘使用率过高: {metrics['disk']['percent']}% (阈值: {thresholds['disk_percent']}%)")

    if alerts:
        send_feishu_alert(
            "⚠️ 系统资源告警",
            "\n".join(alerts) + f"\n\nCPU: {metrics['cpu']['percent']}%\n内存: {metrics['memory']['percent']}%\n磁盘: {metrics['disk']['percent']}%",
            color="orange",
        )

    return metrics


def check_service_health() -> dict[str, Any]:
    """检查服务健康状态"""
    services_status = {}

    # 后端 API（端口连接检查 + HTTP 检查）
    try:
        # 先检查端口
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(("localhost", 8000))
        sock.close()

        if result == 0:
            # 端口通，再尝试 HTTP 检查
            try:
                start = time.time()
                response = requests.get("http://localhost:8000/docs", timeout=5, allow_redirects=True)
                response_time = (time.time() - start) * 1000
                services_status["backend_api"] = {
                    "status": "healthy",
                    "status_code": response.status_code,
                    "response_time_ms": round(response_time, 2),
                }
            except Exception:
                services_status["backend_api"] = {"status": "healthy", "note": "port open, http check skipped"}
        else:
            services_status["backend_api"] = {"status": "down", "error": "port 8000 not reachable"}
            send_feishu_alert(
                "❌ 后端 API 服务不可用",
                "无法连接到 localhost:8000\n请检查后端服务是否正常运行",
                color="red",
            )
    except Exception as e:
        services_status["backend_api"] = {"status": "down", "error": str(e)}

    # 前端（端口连接检查）
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex(("localhost", 3000))
        sock.close()
        services_status["frontend"] = {"status": "healthy" if result == 0 else "down"}
        if result != 0:
            send_feishu_alert(
                "❌ 前端服务不可用",
                "无法连接到 localhost:3000\n请检查前端服务是否正常运行",
                color="red",
            )
    except Exception as e:
        services_status["frontend"] = {"status": "down", "error": str(e)}

    # PostgreSQL
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        host, port = CONFIG["services"]["postgres"].split(":")
        result = sock.connect_ex((host, int(port)))
        sock.close()
        services_status["postgres"] = {"status": "healthy" if result == 0 else "unhealthy"}
        if result != 0:
            send_feishu_alert(
                "❌ PostgreSQL 数据库不可用",
                f"无法连接到 {CONFIG['services']['postgres']}\n请检查数据库服务是否正常运行",
                color="red",
            )
    except Exception as e:
        services_status["postgres"] = {"status": "down", "error": str(e)}

    # Redis
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        host, port = CONFIG["services"]["redis"].split(":")
        result = sock.connect_ex((host, int(port)))
        sock.close()
        services_status["redis"] = {"status": "healthy" if result == 0 else "unhealthy"}
        if result != 0:
            send_feishu_alert(
                "❌ Redis 缓存不可用",
                f"无法连接到 {CONFIG['services']['redis']}\n请检查 Redis 服务是否正常运行",
                color="red",
            )
    except Exception as e:
        services_status["redis"] = {"status": "down", "error": str(e)}

    return services_status


def save_metrics(metrics: dict[str, Any], services: dict[str, Any]) -> None:
    """保存监控指标"""
    record = {
        "timestamp": metrics["timestamp"],
        "system": metrics,
        "services": services,
    }

    # 追加到指标文件（保留最近1000条）
    records = []
    if metrics_file.exists():
        try:
            records = json.loads(metrics_file.read_text(encoding="utf-8"))
        except Exception:
            records = []

    records.append(record)
    if len(records) > 1000:
        records = records[-1000:]

    try:
        metrics_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save metrics: %s", e)


def print_status(metrics: dict[str, Any], services: dict[str, Any]) -> None:
    """打印监控状态"""
    logger.info("=" * 60)
    logger.info("系统监控状态")
    logger.info("=" * 60)
    logger.info("CPU: %.1f%% | 内存: %.1f%% (%s/%s GB) | 磁盘: %.1f%%",
                metrics["cpu"]["percent"],
                metrics["memory"]["percent"],
                metrics["memory"]["used_gb"],
                metrics["memory"]["total_gb"],
                metrics["disk"]["percent"])

    logger.info("-" * 60)
    logger.info("服务健康状态:")
    for name, status in services.items():
        state = status.get("status", "unknown")
        if state == "healthy":
            logger.info("  ✅ %s: %s", name, state)
        elif state == "unhealthy":
            logger.info("  ⚠️  %s: %s", name, state)
        else:
            logger.info("  ❌ %s: %s", name, state)
    logger.info("=" * 60)


def main() -> None:
    """主监控循环"""
    logger.info("Nuotao AI OS 监控服务启动")
    logger.info("检查间隔: %s 秒", CONFIG["check_interval"])
    logger.info("数据目录: %s", data_dir)

    load_alert_history()

    # 启动时发送通知
    send_feishu_alert(
        "✅ 监控服务已启动",
        f"主机: {socket.gethostname()}\n系统: {platform.system()}\n检查间隔: {CONFIG['check_interval']}秒\n监控项: CPU/内存/磁盘/后端API/前端/PostgreSQL/Redis",
        color="green",
    )

    while True:
        try:
            metrics = check_system_resources()
            services = check_service_health()
            save_metrics(metrics, services)
            print_status(metrics, services)
        except Exception as e:
            logger.error("Monitor loop error: %s", e, exc_info=True)

        time.sleep(CONFIG["check_interval"])


if __name__ == "__main__":
    main()
