# SMTP 邮箱配置指南

**文档**: SMTP 邮箱配置
**版本**: v1.0
**日期**: 2026-10-02

---

## 1. 概述

配置 SMTP 邮箱用于接收安全告警邮件通知。支持多种邮箱服务商:
- Gmail
- Outlook / Microsoft 365
- QQ 邮箱
- 企业邮箱 (Exchange)

---

## 2. Gmail 配置

### 2.1 启用两步验证

1. 访问 https://myaccount.google.com/security
2. 点击 "两步验证"
3. 按提示启用

### 2.2 创建应用密码

1. 访问 https://myaccount.google.com/apppasswords
2. 选择应用: Mail
3. 选择设备: Computer
4. 输入自定义名称 (例如: Alertmanager)
5. 点击 "生成"
6. 复制生成的应用密码 (例如: `abcd efgh ijkl mnop`)

### 2.3 更新 Alertmanager 配置

编辑 `/etc/alertmanager/alertmanager.yml`:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@your-gmail.com'
  smtp_auth_username: 'alerts@your-gmail.com'
  smtp_auth_password: 'abcdefghijk1'  # 应用密码 (无空格)
  smtp_require_tls: true
  resolve_timeout: 5m

receivers:
  - name: 'security-email'
    email_configs:
      - to: 'admin@your-company.com'
        send_resolved: true
        headers:
          Subject: '[Nuotao 安全告警] {{ .GroupLabels.severity }} - {{ .GroupLabels.alertname }}'
          From: 'alerts@your-gmail.com'
```

### 2.4 重启 Alertmanager

```bash
systemctl restart alertmanager
```

---

## 3. Outlook / Microsoft 365 配置

### 3.1 创建应用密码

1. 访问 https://account.live.com/proofs/manage
2. 启用两因素身份验证
3. 生成应用密码

### 3.2 更新 Alertmanager 配置

```yaml
global:
  smtp_smarthost: 'smtp.office365.com:587'
  smtp_from: 'alerts@your-outlook.com'
  smtp_auth_username: 'alerts@your-outlook.com'
  smtp_auth_password: 'your-app-password'
  smtp_require_tls: true
  resolve_timeout: 5m
```

---

## 4. QQ 邮箱配置

### 4.1 开启 SMTP 服务

1. 登录 QQ 邮箱
2. 点击 "设置" -> "账号"
3. 找到 "POP3/IMAP/SMTP..."
4. 开启 SMTP 服务
5. 生成授权码

### 4.2 更新 Alertmanager 配置

```yaml
global:
  smtp_smarthost: 'smtp.qq.com:465'
  smtp_from: 'alerts@your-qq.com'
  smtp_auth_username: 'alerts@your-qq.com'
  smtp_auth_password: 'your-authorization-code'
  smtp_require_tls: true
  smtp_skip_verify: false
  resolve_timeout: 5m
```

---

## 5. 企业邮箱配置

### 5.1 Exchange Online

```yaml
global:
  smtp_smarthost: 'smtp.office365.com:587'
  smtp_from: 'alerts@your-company.com'
  smtp_auth_username: 'alerts@your-company.com'
  smtp_auth_password: 'your-app-password'
  smtp_require_tls: true
  resolve_timeout: 5m
```

### 5.2 Exchange On-Premises

```yaml
global:
  smtp_smarthost: 'smtp.your-company.com:587'
  smtp_from: 'alerts@your-company.com'
  smtp_auth_username: 'alerts@your-company.com'
  smtp_auth_password: 'your-password'
  smtp_require_tls: true
  resolve_timeout: 5m
```

---

## 6. 邮件模板

### 6.1 基础模板

```yaml
receivers:
  - name: 'security-email'
    email_configs:
      - to: 'admin@your-company.com'
        send_resolved: true
        headers:
          Subject: '[Nuotao 安全告警] {{ .GroupLabels.severity }} - {{ .GroupLabels.alertname }}'
          From: 'alerts@your-company.com'
        html: |
          <h2>Nuotao 安全告警</h2>
          <table>
            <tr><td><b>严重级别</b></td><td>{{ .GroupLabels.severity }}</td></tr>
            <tr><td><b>告警名称</b></td><td>{{ .GroupLabels.alertname }}</td></tr>
            <tr><td><b>实例</b></td><td>{{ .CommonLabels.instance }}</td></tr>
            <tr><td><b>开始时间</b></td><td>{{ .StartsAt.Format "2006-01-02 15:04:05" }}</td></tr>
          </table>
          <h3>告警详情</h3>
          <ul>
            {{ range .Alerts }}
            <li><b>{{ .Annotations.summary }}</b><br>
                {{ .Annotations.description }}
            </li>
            {{ end }}
          </ul>
```

### 6.2 简版模板

```yaml
receivers:
  - name: 'security-email'
    email_configs:
      - to: 'admin@your-company.com'
        send_resolved: true
        headers:
          Subject: '[{{ .GroupLabels.severity | toUpper }}] {{ .GroupLabels.alertname }}'
          From: 'alerts@your-company.com'
        html: |
          <p><b>严重级别</b>: {{ .GroupLabels.severity }}</p>
          <p><b>告警名称</b>: {{ .GroupLabels.alertname }}</p>
          <p><b>实例</b>: {{ .CommonLabels.instance }}</p>
          {{ range .Alerts }}
          <p><b>摘要</b>: {{ .Annotations.summary }}</p>
          {{ end }}
```

---

## 7. 测试配置

### 7.1 发送测试告警

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
      "summary": "测试告警 - 请确认邮件接收",
      "description": "这是一个测试告警，用于验证邮件配置"
    }
  }]'
```

### 7.2 检查告警状态

```bash
curl -X GET http://localhost:9093/api/v2/alerts | python3 -m json.tool
```

### 7.3 查看 Alertmanager 日志

```bash
journalctl -u alertmanager -f
```

---

## 8. 故障排查

### 8.1 邮件发送失败

**错误**: `dial tcp: lookup smtp.gmail.com: no such host`

**解决**:
```bash
# 检查 DNS 解析
nslookup smtp.gmail.com

# 检查网络连接
telnet smtp.gmail.com 587
```

**错误**: `authentication failed`

**解决**:
- 检查用户名和密码是否正确
- 确认是否使用应用密码而非邮箱密码
- 检查是否已启用两步验证

**错误**: `TLS handshake failed`

**解决**:
- 检查服务器是否支持 TLS
- 尝试更改端口 (587 -> 465)
- 检查防火墙设置

### 8.2 邮件未收到

**检查项**:
1. 收件人地址是否正确
2. 是否进入垃圾邮件文件夹
3. 发送方地址是否在白名单

**调试命令**:
```bash
# 查看 Alertmanager 日志
journalctl -u alertmanager -f

# 手动测试 SMTP 连接
swaks --to admin@your-company.com \
      --from alerts@your-gmail.com \
      --server smtp.gmail.com:587 \
      --tls \
      --auth \
      --html "Test email"
```

---

## 9. 安全建议

### 9.1 密钥管理

1. **不要硬编码密码**: 使用环境变量或 Secrets 管理
2. **使用应用密码**: 不要使用邮箱主密码
3. **定期更换密码**: 每 90 天更换应用密码
4. **限制权限**: 应用密码只用于邮件发送

### 9.2 配置示例

```yaml
global:
  smtp_smarthost: '{{ env "SMTP_HOST" }}:{{ env "SMTP_PORT" }}'
  smtp_from: '{{ env "SMTP_FROM" }}'
  smtp_auth_username: '{{ env "SMTP_USERNAME" }}'
  smtp_auth_password: '{{ env "SMTP_PASSWORD" }}'
  smtp_require_tls: true
  resolve_timeout: 5m
```

---

## 10. 参考文档

- [Alertmanager 配置文档](https://prometheus.io/docs/alerting/latest/configuration/)
- [Gmail 应用密码](https://support.google.com/mail/answer/185833)
- [Microsoft 应用密码](https://support.microsoft.com/en-us/office/use-an-app-password-with-2-step-verification)
- [QQ 邮箱 SMTP](https://help.mail.qq.com/detail/10001371)

---

**文档生成**: 2026-10-02
**生成者**: DeepSeek Harness AI Agent