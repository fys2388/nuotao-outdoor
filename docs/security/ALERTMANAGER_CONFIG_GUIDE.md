# Alertmanager 配置指南

**文档**: Alertmanager 告警配置
**版本**: v1.0
**日期**: 2026-10-02

---

## 1. 概述

Alertmanager 是 Prometheus 生态的告警管理组件，负责:
- 接收 Prometheus 告警
- 分组、去重、抑制告警
- 路由告警到合适的接收器
- 发送告警通知 (Slack、Email、Webhook)

---

## 2. 当前配置状态

### 2.1 已配置接收器

| 接收器 | 类型 | 状态 |
|--------|------|------|
| security-email | Email | ✅ 已配置 (占位符) |
| security-slack | Slack | ✅ 已配置 (占位符) |
| security-sms | Webhook | ✅ 已配置 |

### 2.2 告警路由

| 严重级别 | 接收器 | 重复间隔 |
|----------|--------|----------|
| critical | security-sms | 15 分钟 |
| high | security-slack | 1 小时 |
| medium | security-email | 4 小时 |

---

## 3. 配置真实 Slack Webhook

### 3.1 创建 Slack 应用

1. 访问 https://api.slack.com/apps
2. 点击 "Create New App"
3. 选择 "From scratch"
4. 输入应用名称 (例如: Nuotao Security Alert)
5. 选择 Workspace

### 3.2 配置 Incoming Webhook

1. 在应用页面，点击 "Incoming Webhooks"
2. 点击 "Activate"
3. 选择频道 (#security 或新建)
4. 复制 Webhook URL

### 3.3 更新 Alertmanager 配置

编辑 `/etc/alertmanager/alertmanager.yml`:

```yaml
receivers:
  - name: 'security-slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/TXXXXXXX/BXXXXXXX/xxxxxxxxxxxxxxxx'
        channel: '#security'
        title: '[{{ .GroupLabels.severity | toUpper }}] {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
        send_resolved: true
        color: '{{ if eq .GroupLabels.severity "critical" }}danger{{ else if eq .GroupLabels.severity "high" }}warning{{ else }}good{{ end }}'
        fields:
          - title: '严重级别'
            value: '{{ .GroupLabels.severity }}'
            short: true
          - title: '实例'
            value: '{{ .CommonLabels.instance }}'
            short: true
```

### 3.4 重启 Alertmanager

```bash
systemctl restart alertmanager
```

---

## 4. 配置真实 SMTP 邮箱

### 4.1 创建 Gmail 应用密码

1. 访问 https://myaccount.google.com/apppasswords
2. 选择应用: Mail
3. 选择设备: Computer
4. 点击 "生成"
5. 复制生成的应用密码

### 4.2 更新 Alertmanager 配置

编辑 `/etc/alertmanager/alertmanager.yml`:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'security@your-gmail.com'
  smtp_auth_username: 'security@your-gmail.com'
  smtp_auth_password: 'your-app-password'
  smtp_require_tls: true
  resolve_timeout: 5m

receivers:
  - name: 'security-email'
    email_configs:
      - to: 'admin@your-company.com'
        send_resolved: true
        headers:
          Subject: '[Nuotao 安全告警] {{ .GroupLabels.severity }} - {{ .GroupLabels.alertname }}'
          From: 'security@your-gmail.com'
        html: '<b>严重级别</b>: {{ .GroupLabels.severity }}<br><b>告警名称</b>: {{ .GroupLabels.alertname }}<br><b>实例</b>: {{ .CommonLabels.instance }}<br><b>摘要</b>: {{ range .Alerts }}{{ .Annotations.summary }}<br>{{ end }}'
```

### 4.3 重启 Alertmanager

```bash
systemctl restart alertmanager
```

---

## 5. 测试告警

### 5.1 发送测试告警

```bash
curl -X POST http://localhost:9093/api/v2/alerts \
  -H 'Content-Type: application/json' \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "critical",
      "instance": "localhost:8000"
    },
    "annotations": {
      "summary": "测试告警",
      "description": "这是一个测试告警"
    }
  }]'
```

### 5.2 检查告警状态

```bash
curl -X GET http://localhost:9093/api/v2/alerts
```

---

## 6. 告警规则

### 6.1 API 服务告警

| 告警名称 | 严重级别 | 条件 |
|----------|----------|------|
| ApiServiceDown | critical | up == 0 |
| ApiHighErrorRate | warning | 5xx > 5% |
| ApiHighLatency | warning | p95 > 2s |
| ApiRateLimitExceeded | info | 429 > 10/min |

### 6.2 数据库告警

| 告警名称 | 严重级别 | 条件 |
|----------|----------|------|
| PostgresqlDown | critical | pg_up == 0 |
| PostgresqlHighConnections | warning | 连接 > 80% |
| PostgresqlSlowQueries | warning | 平均查询 > 1s |

### 6.3 系统告警

| 告警名称 | 严重级别 | 条件 |
|----------|----------|------|
| HighCpuUsage | warning | CPU > 80% |
| HighMemoryUsage | warning | 内存 > 80% |
| HighDiskUsage | warning | 磁盘 > 80% |
| DiskSpaceLow | critical | 磁盘 > 95% |

---

## 7. 故障排查

### 7.1 Alertmanager 不发送告警

1. 检查 Alertmanager 状态:
   ```bash
   systemctl status alertmanager
   ```

2. 检查配置语法:
   ```bash
   amtool config check /etc/alertmanager/alertmanager.yml
   ```

3. 查看日志:
   ```bash
   journalctl -u alertmanager -f
   ```

### 7.2 Slack 告警未收到

1. 检查 Webhook URL 是否正确
2. 检查频道是否有权限
3. 检查 Slack 应用是否已激活
4. 查看 Alertmanager 日志

### 7.3 邮件告警未收到

1. 检查 SMTP 配置是否正确
2. 检查应用密码是否正确
3. 检查收件人地址是否正确
4. 查看 Alertmanager 日志

---

## 8. 安全建议

1. **密钥管理**: 将 Slack Webhook URL 和 SMTP 密码存入 Secrets 管理
2. **最小权限**: Slack 应用只授予必要权限
3. **审计日志**: 记录所有告警发送事件
4. **定期测试**: 每月测试告警是否正常

---

## 9. 参考文档

- [Alertmanager 官方文档](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Slack Webhook 文档](https://api.slack.com/messaging/webhooks)
- [Gmail 应用密码](https://support.google.com/mail/answer/185833)

---

**文档生成**: 2026-10-02
**生成者**: DeepSeek Harness AI Agent