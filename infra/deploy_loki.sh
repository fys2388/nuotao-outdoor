#!/bin/bash
# Nuotao AI OS - Loki & Promtail Deployment Script

set -e

echo "=========================================="
echo "  Nuotao AI OS - Loki 部署"
echo "=========================================="
echo "日期: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Configuration
LOKI_PORT=3100
LOKI_USER=loki
PROMTAIL_USER=promtail

# ============================================
# 1. 安装 Loki
# ============================================
echo "=== 1. 安装 Loki ==="

if ! command -v loki &> /dev/null; then
    echo "下载 Loki..."
    
    # 下载 Loki
    wget -q https://github.com/grafana/loki/releases/download/v3.0.0/loki-linux-amd64 -O /usr/local/bin/loki
    chmod +x /usr/local/bin/loki
    
    echo "✅ Loki 下载完成"
else
    echo "Loki 已安装"
fi

# 创建配置目录
mkdir -p /etc/loki
cp /opt/nuotao/infra/loki.yml /etc/loki/loki.yml

# 创建数据目录
mkdir -p /var/lib/loki/chunks
mkdir -p /var/lib/loki/tsdb-index
mkdir -p /var/lib/loki/tsdb-cache
mkdir -p /var/lib/loki/compactor

# 创建用户
if ! id -u $LOKI_USER &> /dev/null; then
    useradd -r -s /bin/false $LOKI_USER
fi

chown -R $LOKI_USER:$LOKI_USER /etc/loki /var/lib/loki

# 创建 systemd 服务
cat > /etc/systemd/system/loki.service << EOF
[Unit]
Description=Grafana Loki - Log Aggregation System
Documentation=https://grafana.com/docs/loki/latest/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$LOKI_USER
Group=$LOKI_USER
Restart=always
RestartSec=5
ExecStart=/usr/local/bin/loki -config.file=/etc/loki/loki.yml
ExecReload=/bin/kill -HUP \$MAINPID

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable loki
systemctl start loki

echo "✅ Loki 部署完成 (端口: $LOKI_PORT)"
echo ""

# ============================================
# 2. 安装 Promtail
# ============================================
echo "=== 2. 安装 Promtail ==="

if ! command -v promtail &> /dev/null; then
    echo "下载 Promtail..."
    
    # 下载 Promtail
    wget -q https://github.com/grafana/loki/releases/download/v3.0.0/loki-linux-amd64 -O /usr/local/bin/promtail
    chmod +x /usr/local/bin/promtail
    
    # Promtail 需要不同的配置
    cat > /usr/local/bin/promtail << 'PROMTAIL_EOF'
#!/bin/bash
exec loki -config.file=/etc/promtail/promtail.yml
PROMTAIL_EOF
    chmod +x /usr/local/bin/promtail
    
    echo "✅ Promtail 下载完成"
else
    echo "Promtail 已安装"
fi

# 创建 Promtail 配置
cat > /etc/promtail/promtail.yml << EOF
server:
  http_listen_address: 0.0.0.0
  http_listen_port: 9080
  grpc_listen_address: 0.0.0.0
  grpc_listen_port: 0

positions:
  filename: /var/lib/promtail/positions.yaml

clients:
  - url: http://localhost:3100/loki/api/v1/push

scrape_configs:
  - job_name: nuotao-backend
    static_configs:
      - targets: [.]
        labels:
          job: nuotao-backend
          host: localhost
          __path__: /var/log/nuotao/*.log

  - job_name: system
    static_configs:
      - targets: [.]
        labels:
          job: system
          host: localhost
          __path__: /var/log/syslog

  - job_name: auth
    static_configs:
      - targets: [.]
        labels:
          job: auth
          host: localhost
          __path__: /var/log/auth.log
EOF

# 创建数据目录
mkdir -p /var/lib/promtail

# 创建用户
if ! id -u $PROMTAIL_USER &> /dev/null; then
    useradd -r -s /bin/false $PROMTAIL_USER
fi

chown -R $PROMTAIL_USER:$PROMTAIL_USER /var/lib/promtail /etc/promtail

# 创建 systemd 服务
cat > /etc/systemd/system/promtail.service << EOF
[Unit]
Description=Grafana Promtail - Log Shipping Agent
Documentation=https://grafana.com/docs/loki/latest/send-data/
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$PROMTAIL_USER
Group=$PROMTAIL_USER
Restart=always
RestartSec=5
ExecStart=/usr/local/bin/promtail -config.file=/etc/promtail/promtail.yml

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable promtail
systemctl start promtail

echo "✅ Promtail 部署完成"
echo ""

# ============================================
# 3. 验证部署
# ============================================
echo "=== 3. 验证部署 ==="

# 检查 Loki
if curl -s http://localhost:$LOKI_PORT/ready | grep -q "ready"; then
    echo "✅ Loki 健康"
else
    echo "❌ Loki 异常"
fi

# 检查 Promtail
if curl -s http://localhost:9080/ready | grep -q "ready"; then
    echo "✅ Promtail 健康"
else
    echo "❌ Promtail 异常"
fi

echo ""
echo "=========================================="
echo "  部署完成!"
echo "=========================================="
echo ""
echo "Loki: http://localhost:$LOKI_PORT"
echo "Promtail: http://localhost:9080"