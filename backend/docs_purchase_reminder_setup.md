# 新订单提醒 - 定期运行配置

## 一、脚本说明

`check_new_purchase_orders.py` 会检查pending状态的采购单，只提醒新增的（基于上次检查时间）。

- 检查记录保存在 `data/purchase_order_last_check.json`
- 已提醒过的采购单不会重复提醒
- 建议每小时运行一次

## 二、Windows 任务计划（本地开发环境）

### 方法1: 图形界面配置

1. 按 `Win + R`，输入 `taskschd.msc`，打开任务计划程序
2. 右侧点击「创建基本任务」
3. 名称: `Nuotao采购单提醒`
4. 触发器: 每天，每1小时重复一次
5. 操作: 启动程序
   - 程序: `E:\AI\nuotao-ai-os\backend\.venv\Scripts\python.exe`
   - 参数: `E:\AI\nuotao-ai-os\backend\check_new_purchase_orders.py`
   - 起始于: `E:\AI\nuotao-ai-os\backend`
6. 完成

### 方法2: PowerShell命令（一键创建）

```powershell
$action = New-ScheduledTaskAction -Execute "E:\AI\nuotao-ai-os\backend\.venv\Scripts\python.exe" -Argument "E:\AI\nuotao-ai-os\backend\check_new_purchase_orders.py" -WorkingDirectory "E:\AI\nuotao-ai-os\backend"
$trigger = New-ScheduledTaskTrigger -Daily -At 0:00
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)).Repetition
Register-ScheduledTask -TaskName "Nuotao采购单提醒" -Action $action -Trigger $trigger -Description "每小时检查新增1688采购单"
```

### 方法3: 简单bat脚本（手动运行）

创建 `check_purchase.bat`:
```bat
@echo off
cd /d E:\AI\nuotao-ai-os\backend
.venv\Scripts\python.exe check_new_purchase_orders.py
pause
```

## 三、Linux Cron（生产服务器）

### 编辑crontab

```bash
crontab -e
```

### 添加以下内容（每小时运行一次）

```cron
# 每小时检查新增1688采购单，输出到日志
0 * * * * cd /opt/nuotao/backend && /opt/nuotao/backend/.venv/bin/python check_new_purchase_orders.py >> /var/log/nuotao/purchase_check.log 2>&1
```

### 查看日志

```bash
tail -f /var/log/nuotao/purchase_check.log
```

## 四、扩展：飞书/邮件通知（后续）

当前版本仅输出到控制台/日志。后续可扩展：

### 飞书Webhook通知

在 `check_new_purchase_orders.py` 的提醒输出部分，添加飞书Webhook调用：

```python
import requests

def send_feishu_notification(message: str, webhook_url: str):
    """发送飞书通知"""
    payload = {
        "msg_type": "text",
        "content": {"text": message}
    }
    requests.post(webhook_url, json=payload, timeout=10)
```

### 邮件通知

复用项目已有的 `email_service.py`，发送HTML格式的采购单提醒邮件。

## 五、手动检查

任何时候都可以手动运行：

```bash
cd E:\AI\nuotao-ai-os\backend
python check_new_purchase_orders.py
```

或者查看所有待确认采购单：

```bash
python manage_purchase_orders.py list --status pending
```
