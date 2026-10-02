# Nuotao AI OS - Security Log Monitoring

## 1. 认证事件监控

### 1.1 登录失败告警

**规则**: 同一 IP 在 15 分钟内登录失败超过 5 次

```bash
# 检查最近的登录失败
journalctl -u nuotao-backend -n 1000 --no-pager | grep "LOGIN_FAILED" | wc -l
```

**告警阈值**: > 5 次/15分钟/IP

### 1.2 登录成功监控

**规则**: 监控所有登录成功事件

```bash
# 查看最近的登录成功
journalctl -u nuotao-backend -n 1000 --no-pager | grep "LOGIN_SUCCESS"
```

### 1.3 异常 IP 监控

**规则**: 监控来自未知 IP 的认证事件

```bash
# 提取所有认证事件的 IP
journalctl -u nuotao-backend -n 1000 --no-pager | grep -oP 'ip=\S+' | sort | uniq -c | sort -rn
```

## 2. API 速率限制监控

### 2.1 速率限制触发

**规则**: 监控速率限制触发事件

```bash
# 查看速率限制事件
journalctl -u nuotao-backend -n 1000 --no-pager | grep "rate_limit"
```

## 3. 数据库安全监控

### 3.1 异常查询监控

**规则**: 监控慢查询和异常查询

```sql
-- 查看慢查询
SELECT query, calls, total_time, rows
FROM pg_stat_statements
WHERE total_time > 1000
ORDER BY total_time DESC
LIMIT 10;
```

## 4. 部署监控

### 4.1 健康检查

**规则**: 每 5 分钟检查一次服务健康

```bash
# 健康检查
curl -s http://127.0.0.1:8000/api/v1/readyz | jq .status
```

### 4.2 资源监控

**规则**: 监控 CPU、内存、磁盘使用率

```bash
# CPU 使用率
top -bn1 | grep "Cpu(s)" | awk '{print $2}'

# 内存使用率
free | awk 'NR==2{printf "%.1f%%\n", $3/$2*100}'

# 磁盘使用率
df / | awk 'NR==2{print $5}'
```

## 5. 安全事件响应

### 5.1 紧急事件

| 事件 | 响应时间 | 操作 |
|------|----------|------|
| 暴力破解 | 立即 | 封禁 IP，重置密码 |
| 数据泄露 | 立即 | 隔离系统，调查原因 |
| 未授权访问 | 立即 | 撤销 token，审查日志 |

### 5.2 告警渠道

1. **邮件**: security@nuotaooutdoor.com
2. **Slack**: #security 频道
3. **短信**: 紧急事件

## 6. 定期安全检查

### 6.1 每日检查

```bash
# 查看最近的认证失败
journalctl -u nuotao-backend --since "24 hours ago" | grep "LOGIN_FAILED" | wc -l
```

### 6.2 每周检查

```bash
# 运行漏洞扫描
python scripts/scan_vulnerabilities.py

# 查看登录统计
journalctl -u nuotao-backend --since "7 days ago" | grep "LOGIN_SUCCESS" | wc -l
```

### 6.3 每月检查

```bash
# 审查所有管理员账户
sudo -u postgres psql -d nuotao -c "SELECT username, email, last_login FROM users WHERE role='admin';"

# 审查认证日志
journalctl -u nuotao-backend --since "30 days ago" | grep "AUTH_"
```

## 7. 监控脚本

### 7.1 安全状态检查

```bash
#!/bin/bash
# security_check.sh

echo "=== 安全状态检查 ==="
echo ""

# 1. 服务健康
echo "1. 服务健康检查:"
curl -s http://127.0.0.1:8000/api/v1/readyz | python3 -m json.tool 2>/dev/null | head -5

echo ""
echo "2. 最近认证失败 (24小时):"
journalctl -u nuotao-backend --since "24 hours ago" | grep "LOGIN_FAILED" | wc -l

echo ""
echo "3. 最近登录成功 (24小时):"
journalctl -u nuotao-backend --since "24 hours ago" | grep "LOGIN_SUCCESS" | wc -l

echo ""
echo "4. 速率限制触发:"
journalctl -u nuotao-backend --since "24 hours ago" | grep "rate_limit" | wc -l

echo ""
echo "5. 活跃连接:"
ss -tlnp | grep -E ':(8000|8080|5432|6379)' | wc -l

echo ""
echo "=== 检查完成 ==="
```

### 7.2 配置 Cron 任务

```bash
# 每日安全状态检查
0 8 * * * /opt/nuotao/scripts/security_check.sh >> /var/log/nuotao/security_daily.log

# 每周漏洞扫描
0 9 * * 1 cd /opt/nuotao && python scripts/scan_vulnerabilities.py >> /var/log/nuotao/security_weekly.log
```

## 8. 日志轮转

### 8.1 系统日志配置

```bash
# /etc/logrotate.d/nuotao
/var/log/nuotao/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```

### 8.2 Journal 日志配置

```bash
# /etc/systemd/journald.conf
[Journal]
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=30day
```

## 9. 告警配置

### 9.1 邮件告警

```bash
# /etc/aliases
nuotao-security: security@nuotaooutdoor.com
```

### 9.2 Alertmanager 配置

```yaml
# alertmanager.yml
global:
  smtp_smarthost: 'smtp.nuotaooutdoor.com:587'
  smtp_from: 'security@nuotaooutdoor.com'
  smtp_auth_username: 'security@nuotaooutdoor.com'
  smtp_auth_password: 'password'

receivers:
  - name: 'security'
    email_configs:
      - to: 'security@nuotaooutdoor.com'
        send_resolved: true

route:
  receiver: 'security'
  group_by: ['alertname']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
```

## 10. 安全仪表板

### 10.1 Grafana 数据源

- PostgreSQL (nuotao)
- Prometheus (metrics)
- Loki (logs)

### 10.2 关键面板

1. **认证概览**
   - 登录成功/失败趋势
   - 活跃用户数
   - 异常登录告警

2. **API 安全**
   - 速率限制触发
   - 认证失败趋势
   - Top 异常 IP

3. **系统健康**
   - 服务状态
   - 资源使用率
   - 错误率趋势

---

**更新日期**: 2026-10-02
**维护者**: Security Team