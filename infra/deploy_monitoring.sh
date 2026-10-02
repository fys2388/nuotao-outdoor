#!/bin/bash
# Nuotao AI OS - Alertmanager & Grafana Deployment Script

set -e

echo "=========================================="
echo "  Nuotao AI OS - 监控告警部署"
echo "=========================================="
echo "日期: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Configuration
ALERTMANAGER_PORT=9093
GRAFANA_PORT=3000
ALERTMANAGER_USER=alertmanager
GRAFANA_USER=grafana

# ============================================
# 1. 安装 Alertmanager
# ============================================
echo "=== 1. 安装 Alertmanager ==="

if ! command -v alertmanager &> /dev/null; then
    echo "下载 Alertmanager..."
    wget -q https://github.com/prometheus/alertmanager/releases/download/v0.27.0/alertmanager-0.27.0.linux-amd64.tar.gz -O /tmp/alertmanager.tar.gz
    tar -xzf /tmp/alertmanager.tar.gz -C /tmp/
    mv /tmp/alertmanager-0.27.0.linux-amd64/alertmanager /usr/local/bin/
    rm -rf /tmp/alertmanager*
    echo "✅ Alertmanager 安装完成"
else
    echo "Alertmanager 已安装"
fi

# 创建配置目录
mkdir -p /etc/alertmanager
cp /opt/nuotao/infra/alertmanager.yml /etc/alertmanager/alertmanager.yml

# 创建数据目录
mkdir -p /var/lib/alertmanager

# 创建用户
if ! id -u $ALERTMANAGER_USER &> /dev/null; then
    useradd -r -s /bin/false $ALERTMANAGER_USER
fi

chown -R $ALERTMANAGER_USER:$ALERTMANAGER_USER /etc/alertmanager /var/lib/alertmanager

# 创建 systemd 服务
cat > /etc/systemd/system/alertmanager.service << EOF
[Unit]
Description=Alertmanager
Documentation=https://prometheus.io/docs/alerting/latest/alertmanager/
After=network.target

[Service]
Type=simple
User=$ALERTMANAGER_USER
Group=$ALERTMANAGER_USER
Restart=always
ExecStart=/usr/local/bin/alertmanager \
    --config.file=/etc/alertmanager/alertmanager.yml \
    --storage.path=/var/lib/alertmanager \
    --web.listen-address=:$(($ALERTMANAGER_PORT)) \
    --cluster.listen-address=

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable alertmanager
systemctl start alertmanager

echo "✅ Alertmanager 部署完成 (端口: $ALERTMANAGER_PORT)"
echo ""

# ============================================
# 2. 安装 Grafana
# ============================================
echo "=== 2. 安装 Grafana ==="

if ! command -v grafana-server &> /dev/null; then
    echo "下载 Grafana..."
    
    # 添加 Grafana 仓库
    apt-get update -qq
    apt-get install -y -qq apt-transport-https software-properties-common wget
    
    wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
    echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" > /etc/apt/sources.list.d/grafana.list
    
    apt-get update -qq
    apt-get install -y -qq grafana
    echo "✅ Grafana 安装完成"
else
    echo "Grafana 已安装"
fi

# 配置 Grafana
echo "# Grafana Configuration" > /etc/grafana/grafana.ini
cat >> /etc/grafana/grafana.ini << EOF

[server]
port = $GRAFANA_PORT
domain = nuotaooutdoor.com

[security]
admin_user = admin
admin_password = NUOTA0_GRAFANA_ADMIN_PASSWORD

[users]
default_allow_sign_up = false

[analytics]
reporting_enabled = false
EOF

systemctl daemon-reload
systemctl enable grafana-server
systemctl restart grafana-server

echo "✅ Grafana 部署完成 (端口: $GRAFANA_PORT)"
echo ""

# ============================================
# 3. 配置 Prometheus 数据源
# ============================================
echo "=== 3. 配置数据源 ==="

# Grafana API 配置
GRAFANA_URL="http://localhost:$GRAFANA_PORT"
GRAFANA_ADMIN="admin:NUOTA0_GRAFANA_ADMIN_PASSWORD"

# 等待 Grafana 启动
sleep 3

# 添加 Prometheus 数据源
curl -s -X POST "$GRAFANA_URL/api/datasources" \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_ADMIN" \
    -d '{
        "name": "Prometheus",
        "type": "prometheus",
        "url": "http://localhost:9090",
        "access": "proxy",
        "isDefault": true,
        "basicAuth": false,
        "withCredentials": false
    }' 2>/dev/null || echo "Prometheus 数据源已存在"

# 添加 Loki 数据源
curl -s -X POST "$GRAFANA_URL/api/datasources" \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_ADMIN" \
    -d '{
        "name": "Loki",
        "type": "loki",
        "url": "http://localhost:3100",
        "access": "proxy",
        "isDefault": false,
        "basicAuth": false,
        "withCredentials": false
    }' 2>/dev/null || echo "Loki 数据源已存在"

# 添加 PostgreSQL 数据源
curl -s -X POST "$GRAFANA_URL/api/datasources" \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_ADMIN" \
    -d '{
        "name": "PostgreSQL",
        "type": "postgres",
        "url": "localhost:5432",
        "user": "nuotao",
        "database": "nuotao",
        "secureJsonData": {
            "password": "NUOTA0_DB_PASSWORD"
        },
        "access": "proxy",
        "isDefault": false,
        "basicAuth": false,
        "withCredentials": false
    }' 2>/dev/null || echo "PostgreSQL 数据源已存在"

echo "✅ 数据源配置完成"
echo ""

# ============================================
# 4. 导入安全仪表板
# ============================================
echo "=== 4. 导入安全仪表板 ==="

# 创建仪表板 JSON
DASHBOARD_JSON='{
    "title": "Nuotao 安全概览",
    "uid": "nuotao-security-overview",
    "panels": [
        {
            "title": "活跃告警数",
            "type": "stat",
            "targets": [{
                "expr": "sum(ALERTS_FOR_STATE{state=\"firing\"})",
                "refId": "A"
            }]
        },
        {
            "title": "告警趋势 (24小时)",
            "type": "graph",
            "targets": [{
                "expr": "sum by (alertname) (changes(alerts_total[1h]))",
                "refId": "A"
            }]
        },
        {
            "title": "认证安全",
            "type": "table",
            "targets": [{
                "expr": "login_failures_total",
                "refId": "A"
            }]
        }
    ]
}'

# 导入仪表板
curl -s -X POST "$GRAFANA_URL/api/dashboards/db" \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_ADMIN" \
    -d "$DASHBOARD_JSON" 2>/dev/null || echo "仪表板已存在"

echo "✅ 安全仪表板导入完成"
echo ""

# ============================================
# 5. 验证部署
# ============================================
echo "=== 5. 验证部署 ==="

# 检查 Alertmanager
if curl -s http://localhost:$ALERTMANAGER_PORT/-/healthy | grep -q "OK"; then
    echo "✅ Alertmanager 健康"
else
    echo "❌ Alertmanager 异常"
fi

# 检查 Grafana
if curl -s http://localhost:$GRAFANA_PORT/api/health | grep -q "ok"; then
    echo "✅ Grafana 健康"
else
    echo "❌ Grafana 异常"
fi

echo ""
echo "=========================================="
echo "  部署完成!"
echo "=========================================="
echo ""
echo "Alertmanager: http://localhost:$ALERTMANAGER_PORT"
echo "Grafana: http://localhost:$GRAFANA_PORT"
echo ""
echo "Grafana 管理员密码: NUOTA0_GRAFANA_ADMIN_PASSWORD"
echo ""
echo "请修改以下密码:"
echo "1. /etc/grafana/grafana.ini - admin_password"
echo "2. /etc/alertmanager/alertmanager.yml - smtp_auth_password"