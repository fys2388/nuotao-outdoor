# Nuotao AI OS - SMTP 邮箱配置指南

## 1. 配置 Gmail SMTP

### 步骤 1: 创建 Gmail 应用密码

1. 访问 https://myaccount.google.com/
2. 选择 "安全性"
3. 找到 "2 步验证" 并开启
4. 返回安全性页面，选择 "应用密码"
5. 选择 "邮件" 作为应用
6. 选择设备名称 (如: Nuotao Alertmanager)
7. 复制生成的应用密码 (格式: xxxx xxxx xxxx xxxx)

### 步骤 2: 配置 Alertmanager

编辑 `/etc/alertmanager/alertmanager.yml`:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'security@nuotaooutdoor.com'
  smtp_auth_username: 'security@nuotaooutdoor.com'
  smtp_auth_password: 'your_app_password_here'
  smtp_require_tls: true
  resolve_timeout: 5m
```

### 步骤 3: 重启 Alertmanager

```bash
systemctl restart alertmanager
```

## 2. 配置其他邮箱服务商

### QQ 邮箱

```yaml
global:
  smtp_smarthost: 'smtp.qq.com:587'
  smtp_from: 'security@qq.com'
  smtp_auth_username: 'security@qq.com'
  smtp_auth_password: 'your_app_password_here'
  smtp_require_tls: true
```

### 企业邮箱

```yaml
global:
  smtp_smarthost: 'smtp.yourcompany.com:587'
  smtp_from: 'security@yourcompany.com'
  smtp_auth_username: 'security@yourcompany.com'
  smtp_auth_password: 'your_password_here'
  smtp_require_tls: true
```

## 3. 测试 SMTP 配置

### 步骤 1: 发送测试告警

```bash
# 创建测试告警
cat > /tmp/test_email_alert.json << EOF
[
  {
    "labels": {
      "alertname": "TestEmailAlert",
      "severity": "warning",
      "instance": "localhost"
    },
    "annotations": {
      "summary": "Nuotao 邮件告警测试",
      "description": "这是一个测试邮件告警，验证 SMTP 配置"
    }
  }
]
EOF

# 发送测试告警
curl -X POST http://localhost:9093/api/v2/alerts \
  -H 'Content-Type: application/json' \
  -d @/tmp/test_email_alert.json
```

### 步骤 2: 检查邮件收件箱

- 检查邮箱是否收到告警邮件
- 验证邮件格式是否正确
- 确认发件人地址正确

### 步骤 3: 检查 Alertmanager 日志

```bash
# 查看 Alertmanager 日志
journalctl -u alertmanager -n 50

# 查看错误日志
journalctl -u alertmanager -n 50 | grep -i error
```

## 4. 邮件模板

### 告警邮件主题

```
[Nuotao 安全告警] {{ .GroupLabels.severity }} - {{ .GroupLabels.alertname }}
```

### 告警邮件正文

Alertmanager 会自动生成邮件正文，包含以下信息:
- 告警名称
- 告警严重性
- 告警详情
- 时间戳
- 运行手册链接

### 自定义邮件模板

创建模板文件 `/etc/alertmanager/templates/email.tmpl`:

```go
{{ define "email.subject" }}
[Nuotao 安全告警] {{ .GroupLabels.severity | toUpper }} - {{ .GroupLabels.alertname }}
{{ end }}

{{ define "email.html" }}
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; }
        .header { color: #333; }
        .critical { color: #FF0000; font-weight: bold; }
        .high { color: #FFA500; font-weight: bold; }
        .medium { color: #FFFF00; font-weight: bold; }
        .low { color: #32CD32; font-weight: bold; }
        .footer { color: #666; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Nuotao 安全告警</h1>
    </div>

    <h2>
        {{ if eq .GroupLabels.severity "critical" }}
        <span class="critical">CRITICAL</span>
        {{ else if eq .GroupLabels.severity "high" }}
        <span class="high">HIGH</span>
        {{ else if eq .GroupLabels.severity "medium" }}
        <span class="medium">MEDIUM</span>
        {{ else }}
        <span class="low">LOW</span>
        {{ end }}
    </h2>

    <h3>告警详情</h3>
    <ul>
        <li><strong>告警名称</strong>: {{ .GroupLabels.alertname }}</li>
        <li><strong>严重性</strong>: {{ .GroupLabels.severity }}</li>
        <li><strong>实例</strong>: {{ .GroupLabels.instance }}</li>
        <li><strong>时间</strong>: {{ .GroupLabels.startsAt }}</li>
    </ul>

    <h3>告警内容</h3>
    {{ range .Alerts }}
    <div style="margin: 10px 0; padding: 10px; background: #f5f5f5;">
        <p><strong>摘要</strong>: {{ .Annotations.summary }}</p>
        <p><strong>描述</strong>: {{ .Annotations.description }}</p>
        {{ if .Annotations.runbook }}
        <p><strong>运行手册</strong>: <a href="{{ .Annotations.runbook }}">{{ .Annotations.runbook }}</a></p>
        {{ end }}
    </div>
    {{ end }}

    <div class="footer">
        <p>此邮件由 Nuotao AI OS Alertmanager 自动发送</p>
        <p>请勿直接回复此邮件</p>
    </div>
</body>
</html>
{{ end }}
```

## 5. 安全最佳实践

### 5.1 应用密码

- 使用应用密码而非账户密码
- 定期轮换应用密码
- 存储应用密码在安全位置

### 5.2 邮件安全

- 不在邮件中包含敏感信息
- 使用 TLS 加密传输
- 配置 SPF/DKIM/DMARC

### 5.3 监控

- 监控邮件发送失败
- 记录所有邮件发送
- 定期审查邮件日志

## 6. 故障排查

### 问题 1: 邮件无法发送

**可能原因**:
- SMTP 服务器地址错误
- 端口错误
- 认证失败

**解决方法**:
```bash
# 检查 SMTP 连接
telnet smtp.gmail.com 587

# 检查 Alertmanager 日志
journalctl -u alertmanager -n 50

# 检查错误日志
journalctl -u alertmanager -n 50 | grep -i error
```

### 问题 2: 认证失败

**可能原因**:
- 应用密码错误
- 2 步验证未开启

**解决方法**:
- 重新生成应用密码
- 确认 2 步验证已开启
- 检查用户名是否正确

### 问题 3: 邮件被标记为垃圾邮件

**可能原因**:
- 未配置 SPF/DKIM/DMARC
- 邮件内容触发垃圾邮件过滤器

**解决方法**:
- 配置 SPF 记录
- 配置 DKIM 签名
- 配置 DMARC 记录
- 检查邮件内容

## 7. 参考资源

- [Gmail 应用密码](https://support.google.com/accounts/answer/185833)
- [Alertmanager SMTP 配置](https://prometheus.io/docs/alerting/latest/configuration/#email_config)
- [SPF 配置](https://support.google.com/a/answer/33786)
- [DKIM 配置](https://support.google.com/a/answer/2466580)
- [DMARC 配置](https://support.google.com/a/answer/2466583)

---

**更新日期**: 2026-10-02
**维护者**: Security Team