# Nuotao AI OS - 告警系统配置

## 1. 告警规则

### 1.1 认证告警

| 规则 | 条件 | 严重性 | 动作 |
|------|------|--------|------|
| 暴力破解 | 同一 IP 15分钟内登录失败 > 5次 | High | 邮件 + Slack |
| 异常登录 | 未知 IP 登录成功 | Medium | 邮件 |
| 管理员登录 | 任何管理员登录 | Low | 记录 |
| MFA 失败 | MFA 验证失败 > 3次 | Medium | 邮件 |

### 1.2 API 安全告警

| 规则 | 条件 | 严重性 | 动作 |
|------|------|--------|------|
| 速率限制 | 触发速率限制 | Medium | 邮件 |
| 认证失败 | 401 响应 > 100次/小时 | Medium | 邮件 |
| 未授权访问 | 403 响应 > 50次/小时 | Low | 记录 |

### 1.3 系统告警

| 规则 | 条件 | 严重性 | 动作 |
|------|------|--------|------|
| 服务宕机 | 健康检查失败 | Critical | 邮件 + 短信 |
| 高 CPU | CPU > 80% 持续 5分钟 | Medium | 邮件 |
| 低磁盘 | 磁盘 < 10% | High | 邮件 + Slack |
| 内存不足 | 内存 > 90% | Medium | 邮件 |

### 1.4 数据库告警

| 规则 | 条件 | 严重性 | 动作 |
|------|------|--------|------|
| 连接异常 | 连接失败 | Critical | 邮件 + 短信 |
| 慢查询 | 查询 > 10秒 | Low | 记录 |
| 磁盘满 | 数据库磁盘 < 5% | Critical | 邮件 + 短信 |

---

## 2. 告警渠道

### 2.1 邮件告警

**配置**:
```yaml
smtp_server: smtp.nuotaooutdoor.com
smtp_port: 587
smtp_username: security@nuotaooutdoor.com
smtp_password: ${SMTP_PASSWORD}
from: security@nuotaooutdoor.com
to:
  - security@nuotaooutdoor.com
  - admin@nuotaooutdoor.com
```

**模板**:
```
主题: [Nuotao 安全告警] {severity} - {alert_name}

内容:
时间: {timestamp}
规则: {rule_name}
详情: {details}
IP: {ip_address}
建议: {recommendation}
```

### 2.2 Slack 告警

**配置**:
```yaml
webhook_url: https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx
channel: #security
username: Nuotao Security Bot
```

**模板**:
```
*{severity_icon}* *{severity}* *{alert_name}*
```

### 2.3 短信告警 (Critical)

**配置**:
```yaml
provider: twilio
account_sid: ${TWILIO_ACCOUNT_SID}
auth_token: ${TWILIO_AUTH_TOKEN}
from_number: +1234567890
to_numbers:
  - +1234567890
```

---

## 3. 告警抑制

### 3.1 维护窗口

**配置**:
```yaml
maintenance_windows:
  - name: 计划维护
    start: "2026-10-03 02:00:00"
    end: "2026-10-03 04:00:00"
    suppress: all
```

### 3.2 重复告警

**规则**:
- 同一告警在 1 小时内只发送一次
- 相同 IP 的暴力破解告警合并

### 3.3 低优先级告警

**规则**:
- Low 级别告警只在 Slack 发送
- 工作时间外不发送 Medium 告警

---

## 4. 告警升级

### 4.1 升级策略

| 严重性 | 首次响应 | 升级时间 | 升级对象 |
|--------|----------|----------|----------|
| Critical | 立即 | 15分钟 | 运维负责人 |
| High | 立即 | 30分钟 | 安全负责人 |
| Medium | 1小时 | 4小时 | 值班工程师 |
| Low | 24小时 | - | - |

### 4.2 升级流程

1. **首次告警** → 邮件 + Slack
2. **未响应** → 短信 (Critical/High)
3. **仍未响应** → 电话 (Critical)
4. **升级** → 上级负责人

---

## 5. 告警仪表板

### 5.1 Grafana 面板

**面板 1: 安全概览**
- 活跃告警数
- 告警趋势 (24小时)
- 告警分布 (按严重性)

**面板 2: 认证安全**
- 登录成功/失败趋势
- 暴力破解尝试
- 异常登录 IP

**面板 3: API 安全**
- 速率限制触发
- 认证失败趋势
- Top 异常 IP

**面板 4: 系统健康**
- 服务状态
- 资源使用率
- 错误率趋势

### 5.2 数据源

- **Loki**: 应用日志
- **Prometheus**: 系统指标
- **PostgreSQL**: 业务数据

---

## 6. 告警响应流程

### 6.1 标准响应

1. **接收告警**
   - 查看告警详情
   - 确认告警真实性

2. **评估影响**
   - 判断影响范围
   - 确定严重性

3. **执行响应**
   - 查看相关日志
   - 检查系统状态
   - 执行应急措施

4. **记录处理**
   - 更新告警状态
   - 记录处理过程
   - 发送处理报告

### 6.2 应急措施

| 场景 | 措施 |
|------|------|
| 暴力破解 | 封禁 IP，重置密码 |
| 数据泄露 | 隔离系统，调查原因 |
| 未授权访问 | 撤销 token，审查日志 |
| 服务宕机 | 重启服务，检查日志 |
| 高负载 | 扩容，优化查询 |

---

## 7. 测试计划

### 7.1 告警测试

**频率**: 每周一次

**测试内容**:
1. 模拟登录失败 → 触发暴力破解告警
2. 模拟服务宕机 → 触发 Critical 告警
3. 模拟高 CPU → 触发 Medium 告警

**验证**:
- 邮件是否发送
- Slack 是否收到
- 短信是否收到 (Critical)

### 7.2 响应测试

**频率**: 每月一次

**测试内容**:
1. 模拟安全事件
2. 测试响应流程
3. 验证升级机制

---

## 8. 配置示例

### 8.1 Alertmanager 配置

```yaml
# alertmanager.yml
global:
  smtp_smarthost: 'smtp.nuotaooutdoor.com:587'
  smtp_from: 'security@nuotaooutdoor.com'
  smtp_auth_username: 'security@nuotaooutdoor.com'
  smtp_auth_password: 'password'
  smtp_require_tls: true

receivers:
  - name: 'email'
    email_configs:
      - to: 'security@nuotaooutdoor.com'
        send_resolved: true
        headers:
          Subject: '[Nuotao 安全告警] {{ .GroupLabels.severity }}'

  - name: 'slack'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/T00000000/B00000000/xxxxxxxx'
        channel: '#security'
        title: '[{{ .GroupLabels.severity }}] {{ .GroupLabels.alertname }}'
        send_resolved: true

  - name: 'sms'
    webhook_configs:
      - url: 'http://localhost:8080/webhook/sms'

route:
  receiver: 'email'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match:
        severity: 'critical'
      receiver: 'sms'
      continue: true
    - match:
        severity: 'high'
      receiver: 'slack'
      continue: true

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'high'
    equal: ['alertname', 'instance']
```

### 8.2 Prometheus 告警规则

```yaml
# prometheus-rules.yml
groups:
  - name: security_alerts
    rules:
      - alert: HighLoginFailure
        expr: rate(login_failures_total[15m]) > 5
        for: 5m
        labels:
          severity: high
        annotations:
          summary: "Login failures from {{ $labels.ip }}"
          description: "IP {{ $labels.ip }} has {{ $value }} login failures in 15m"

      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is down"

      - alert: HighCPU
        expr: instance:node_cpu:rate:5m > 0.8
        for: 5m
        labels:
          severity: medium
        annotations:
          summary: "High CPU on {{ $labels.instance }}"
```

---

## 9. 安全最佳实践

1. **最小权限**: 告警系统只读取必要数据
2. **加密传输**: 所有告警通信使用 TLS
3. **密钥管理**: 敏感配置存储在 Secrets 管理
4. **审计日志**: 记录所有告警发送和接收
5. **定期测试**: 定期测试告警系统
6. **文档化**: 维护告警规则和响应流程

---

## 10. 参考资源

- [Alertmanager 文档](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Slack Webhooks](https://api.slack.com/messaging/webhooks)
- [Twilio SMS API](https://www.twilio.com/docs/sms)

---

**更新日期**: 2026-10-02
**维护者**: Security Team