#!/bin/bash
# Nuotao AI OS - Security Status Check Script
# Runs daily to check security status

echo "=========================================="
echo "  Nuotao AI OS - 安全状态检查"
echo "=========================================="
echo "日期: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

echo "=== 1. 服务健康检查 ==="
HEALTH=$(curl -s http://127.0.0.1:8000/api/v1/readyz 2>/dev/null)
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "✅ 服务健康"
else
    echo "❌ 服务异常"
    echo "$HEALTH"
fi
echo ""

echo "=== 2. 认证统计 (24小时) ==="
LOGIN_SUCCESS=$(journalctl -u nuotao-backend --since "24 hours ago" --no-pager 2>/dev/null | grep "LOGIN_SUCCESS" | wc -l)
LOGIN_FAILED=$(journalctl -u nuotao-backend --since "24 hours ago" --no-pager 2>/dev/null | grep "LOGIN_FAILED" | wc -l)
echo "登录成功: $LOGIN_SUCCESS"
echo "登录失败: $LOGIN_FAILED"
echo ""

echo "=== 3. 速率限制 ==="
RATE_LIMIT=$(journalctl -u nuotao-backend --since "24 hours ago" --no-pager 2>/dev/null | grep "rate_limit" | wc -l)
echo "速率限制触发: $RATE_LIMIT"
echo ""

echo "=== 4. 系统资源 ==="
CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}')
MEM=$(free | awk 'NR==2{printf "%.1f", $3/$2*100}')
DISK=$(df / | awk 'NR==2{print $5}')
echo "CPU: ${CPU}%"
echo "内存: ${MEM}%"
echo "磁盘: ${DISK}"
echo ""

echo "=== 5. 活跃连接 ==="
CONN=$(ss -tlnp 2>/dev/null | grep -E ':(8000|8080|5432|6379)' | wc -l)
echo "活跃端口: $CONN"
echo ""

echo "=== 6. 最近认证事件 ==="
journalctl -u nuotao-backend --since "1 hour ago" --no-pager 2>/dev/null | grep -E "LOGIN|AUTH" | tail -5
echo ""

echo "=========================================="
echo "  检查完成"
echo "=========================================="