# Nuotao AI OS - Slack Webhook 配置指南

## 1. 创建 Slack 应用

### 步骤 1: 访问 Slack API

1. 访问 https://api.slack.com/apps
2. 使用 Nuotao 团队的 Slack 账户登录
3. 点击 "Create New App"

### 步骤 2: 创建新应用

1. 选择 "From a manifest"
2. 使用以下 Manifest:

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

3. 点击 "Create"

### 步骤 3: 创建 Incoming Webhook

1. 在 Slack App 中，进入 "Incoming Webhooks"
2. 点击 "Activate"
3. 选择目标频道 (建议: #security)
4. 复制生成的 Webhook URL，格式如下:
   ```
   https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxxxxxx
   ```

## 2. 配置 Alertmanager

### 步骤 1: 更新配置文件

编辑 `/etc/alertmanager/alertmanager.yml`:

```yaml
receivers:
  - name: 'security-slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx'
        channel: '#security'
        title: '[{{ .GroupLabels.severity | toUpper }}] {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
        send_resolved: true
```

### 步骤 2: 重启 Alertmanager

```bash
systemctl restart alertmanager
```

### 步骤 3: 验证配置

```bash
# 检查 Alertmanager 状态
systemctl status alertmanager

# 查看 Alertmanager 日志
journalctl -u alertmanager -n 20
```

## 3. 测试 Webhook

### 步骤 1: 发送测试消息

```bash
# 创建测试 JSON
cat > /tmp/test_slack.json << EOF
{
  "text": ":warning: Nuotao 安全告警测试\n这是一个测试消息，验证 Slack Webhook 配置",
  "attachments": [
    {
      "color": "#FFA500",
      "blocks": [
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*Nuotao 安全告警*\n*时间*: $(date)\n*严重性*: Warning\n*建议*: 1 小时内响应"
          }
        }
      ]
    }
  ]
}
EOF

# 发送测试消息
curl -X POST "https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx" \
  -H "Content-type: application/json" \
  -d @/tmp/test_slack.json
```

### 步骤 2: 验证消息

- 检查 Slack 频道是否收到消息
- 验证消息格式是否正确
- 确认时间戳和严重性显示正确

## 4. 配置环境变量

### 步骤 1: 创建环境变量文件

```bash
cat > /etc/alertmanager/secrets.env << EOF
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx
SLACK_CHANNEL=#security
EOF

# 设置权限
chmod 600 /etc/alertmanager/secrets.env
```

### 步骤 2: 在 systemd 服务中加载环境变量

编辑 `/etc/systemd/system/alertmanager.service`:

```ini
[Service]
EnvironmentFile=/etc/alertmanager/secrets.env
```

### 步骤 3: 重新加载 systemd

```bash
systemctl daemon-reload
systemctl restart alertmanager
```

## 5. 告警模板

### Critical 告警模板

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

### High 告警模板

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

### Medium 告警模板

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

## 6. 故障排查

### 问题 1: Webhook 无法发送

**可能原因**:
- Webhook URL 错误
- 网络问题
- 防火墙限制

**解决方法**:
```bash
# 检查网络连接
curl -v https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx

# 检查防火墙
ufw status

# 检查代理
echo $http_proxy
echo $https_proxy
```

### 问题 2: 告警未收到

**可能原因**:
- Alertmanager 配置错误
- 告警路由错误
- Webhook 未配置

**解决方法**:
```bash
# 检查 Alertmanager 日志
journalctl -u alertmanager -n 50

# 检查告警路由
curl http://localhost:9093/api/v2/routes

# 检查告警状态
curl http://localhost:9093/api/v2/alerts
```

### 问题 3: 消息格式错误

**可能原因**:
- JSON 格式错误
- 模板语法错误

**解决方法**:
```bash
# 验证 JSON 格式
cat /tmp/test_slack.json | python3 -m json.tool

# 查看 Alertmanager 错误日志
journalctl -u alertmanager -n 50 | grep -i error
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

## 8. 参考资源

- [Slack Webhooks](https://api.slack.com/messaging/webhooks)
- [Alertmanager Slack](https://prometheus.io/docs/alerting/latest/configuration/#slack_config)
- [Slack API](https://api.slack.com/)

---

**更新日期**: 2026-10-02
**维护者**: Security Team