# Nuotao AI OS - Slack Webhook 配置

## 1. Slack Webhook 配置

### 1.1 创建 Slack 应用

1. 访问 https://api.slack.com/apps
2. 点击 "Create New App"
3. 选择 "From a manifest"
4. 使用以下清单:

```yaml
api_version: '1.0'
app_name: 'Nuotao Security Bot'
app_manifest:
  _comment: Nuotao AI OS Security Alerts
  name: 'Nuotao Security Bot'
  description: 'Nuotao AI OS 安全告警机器人'
  contact_email: security@nuotaooutdoor.com
  bot_user:
    display_name: 'Nuotao Security'
    description: 'Nuotao AI OS 安全告警'
  scopes:
    bot:
      - commands
      - chat:write
  oauth_config:
    install_path: '/oauth/v2/authorize'
```

### 1.2 创建 Incoming Webhook

1. 在 Slack App 中，进入 "Incoming Webhooks"
2. 点击 "Activate"
3. 选择目标频道 (#security)
4. 复制 Webhook URL

### 1.3 配置环境变量

```bash
# 在 /etc/alertmanager/alertmanager.yml 中
receivers:
  - name: 'security-slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx'
        channel: '#security'
```

## 2. 测试 Webhook

### 2.1 发送测试消息

```bash
curl -X POST "https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx" \
  -H "Content-type: application/json" \
  --data '{"text":"Nuotao 安全告警测试消息"}'
```

### 2.2 验证消息

- 检查 Slack 频道是否收到消息
- 验证消息格式是否正确

## 3. 告警模板

### 3.1 Critical 告警

```json
{
  "text": ":red_circle: *CRITICAL: 服务宕机*\n*时间*: {{ .StartsAt }}\n*服务*: {{ .Labels.instance }}\n*详情*: {{ .Annotations.description }}",
  "attachments": [
    {
      "color": "#FF0000",
      "blocks": [
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Nuotao 安全告警*\n状态: 触发\n建议: 立即响应"
          }
        }
      ]
    }
  ]
}
```

### 3.2 High 告警

```json
{
  "text": ":orange_circle: *HIGH: 暴力破解尝试*\n*时间*: {{ .StartsAt }}\n*IP*: {{ .Labels.ip }}\n*详情*: {{ .Annotations.description }}",
  "attachments": [
    {
      "color": "#FFA500",
      "blocks": [
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Nuotao 安全告警*\n状态: 触发\n建议: 1 小时内响应"
          }
        }
      ]
    }
  ]
}
```

### 3.3 Medium 告警

```json
{
  "text": ":yellow_circle: *MEDIUM: 速率限制触发*\n*时间*: {{ .StartsAt }}\n*IP*: {{ .Labels.ip }}",
  "attachments": [
    {
      "color": "#FFFF00",
      "blocks": [
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Nuotao 安全告警*\n状态: 触发\n建议: 4 小时内响应"
          }
        }
      ]
    }
  ]
}
```

## 4. 告警规则示例

### 4.1 暴力破解

```yaml
groups:
  - name: security
    rules:
      - alert: BruteForceLogin
        expr: sum(rate(login_failures_total[15m])) by (ip) > 5
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "暴力破解尝试 ({{ $labels.ip }})"
          description: "IP {{ $labels.ip }} 在 15 分钟内登录失败超过 5 次"
```

### 4.2 服务宕机

```yaml
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "服务宕机 ({{ $labels.instance }})"
          description: "服务 {{ $labels.instance }} 已宕机"
```

## 5. 告警抑制

### 5.1 维护窗口

```yaml
# 在 Prometheus 规则中
inhibit_rules:
  - source_match:
      maintenance: 'true'
    target_match:
      severity: 'critical'
```

### 5.2 重复告警

```yaml
# Alertmanager 配置
route:
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

## 6. 告警测试

### 6.1 发送测试告警

```bash
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[
    {
      "labels": {
        "alertname": "TestAlert",
        "severity": "warning",
        "instance": "localhost"
      },
      "annotations": {
        "summary": "测试告警",
        "description": "这是一个测试告警"
      }
    }
  ]'
```

### 6.2 检查告警状态

```bash
curl http://localhost:9093/api/v2/alerts
```

## 7. 安全最佳实践

1. **Webhook 安全**
   - 定期轮换 Webhook URL
   - 限制 Webhook 的权限
   - 监控 Webhook 使用

2. **告警安全**
   - 不在告警中包含敏感信息
   - 使用安全的告警渠道
   - 定期审查告警规则

3. **响应安全**
   - 快速响应 Critical 告警
   - 记录所有告警响应
   - 定期审查告警历史

## 8. 故障排查

### 8.1 Webhook 无法发送

```bash
# 检查网络连接
curl -v https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx

# 检查防火墙
ufw status

# 检查代理
echo $http_proxy
echo $https_proxy
```

### 8.2 告警未收到

```bash
# 检查 Alertmanager 日志
journalctl -u alertmanager -n 50

# 检查告警路由
curl http://localhost:9093/api/v2/routes

# 检查告警状态
curl http://localhost:9093/api/v2/alerts
```

## 9. 参考资源

- [Slack Webhooks](https://api.slack.com/messaging/webhooks)
- [Alertmanager Slack](https://prometheus.io/docs/alerting/latest/configuration/#slack_config)
- [Slack API](https://api.slack.com/)

---

**更新日期**: 2026-10-02
**维护者**: Security Team