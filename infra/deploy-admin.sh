#!/bin/bash
# ============================================================
# Nuotao AI OS - 部署到 admin.nuotaooutdoor.com
# ============================================================

set -e

echo "============================================"
echo "  Nuotao AI OS - Admin Console Deployment"
echo "============================================"

# 配置
DOMAIN="admin.nuotaooutdoor.com"
FRONTEND_DIR="/var/www/nuotao-console"
BACKEND_DIR="/opt/nuotao-ai-os"
BACKEND_PORT=8000
LOG_DIR="/var/log/nuotao-ai-os"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否以root运行
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 权限运行此脚本"
    exit 1
fi

# 步骤1: 创建目录
log_info "步骤1/6: 创建目录..."
mkdir -p "$FRONTEND_DIR"
mkdir -p "$BACKEND_DIR"
mkdir -p "$LOG_DIR"

# 步骤2: 复制前端文件
log_info "步骤2/6: 部署前端..."
cd /root/nuotao-ai-os/frontend
npm install
npm run build
rm -rf "$FRONTEND_DIR"/*
cp -r dist/* "$FRONTEND_DIR"/
log_info "前端已部署到 $FRONTEND_DIR"

# 步骤3: 复制后端文件
log_info "步骤3/6: 部署后端..."
cd /root/nuotao-ai-os
cp -r backend "$BACKEND_DIR"/
cp -r workflow "$BACKEND_DIR"/
cp -r data "$BACKEND_DIR"/ 2>/dev/null || true
cp requirements.txt "$BACKEND_DIR"/

# 步骤4: 创建Python虚拟环境
log_info "步骤4/6: 配置Python环境..."
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# 步骤5: 初始化数据库
log_info "步骤5/6: 初始化数据库..."
cd "$BACKEND_DIR"
source venv/bin/activate
python backend/init_db.py
deactivate

# 步骤6: 配置Nginx
log_info "步骤6/6: 配置Nginx..."
cp infra/nginx/admin-console.conf /etc/nginx/sites-available/nuotao-admin
ln -sf /etc/nginx/sites-available/nuotao-admin /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试Nginx配置
nginx -t
if [ $? -ne 0 ]; then
    log_error "Nginx配置测试失败"
    exit 1
fi

# 重载Nginx
systemctl reload nginx

# 步骤7: 配置systemd服务
log_info "配置systemd服务..."
cat > /etc/systemd/system/nuotao-backend.service << 'EOF'
[Unit]
Description=Nuotao AI OS Backend API
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/nuotao-ai-os
Environment="PATH=/opt/nuotao-ai-os/venv/bin:/usr/local/bin:/usr/bin"
Environment="VIRTUAL_ENV=/opt/nuotao-ai-os/venv"
Environment="WORKFLOW_CONFIG=/opt/nuotao-ai-os/workflow/nuotao_product_wc_publish_v1.json"
Environment="DATABASE_PATH=/opt/nuotao-ai-os/data"
ExecStart=/opt/nuotao-ai-os/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nuotao-backend

[Install]
WantedBy=multi-user.target
EOF

# 启用并启动服务
systemctl daemon-reload
systemctl enable nuotao-backend
systemctl start nuotao-backend

# 等待服务启动
sleep 5

# 检查服务状态
if systemctl is-active --quiet nuotao-backend; then
    log_info "后端服务已启动"
else
    log_error "后端服务启动失败"
    journalctl -u nuotao-backend -n 20
    exit 1
fi

# 配置SSL证书
log_info "配置SSL证书..."
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@nuotaooutdoor.com

# 完成
echo ""
echo "============================================"
echo -e "${GREEN}  部署完成！${NC}"
echo "============================================"
echo ""
echo "  访问地址:"
echo "  https://$DOMAIN"
echo ""
echo "  管理命令:"
echo "  查看后端日志: journalctl -u nuotao-backend -f"
echo "  重启后端: systemctl restart nuotao-backend"
echo "  查看状态: systemctl status nuotao-backend"
echo ""
echo "  前端更新:"
echo "  cd /root/nuotao-ai-os/frontend && npm run build"
echo "  cp -r dist/* $FRONTEND_DIR/"
echo ""
echo "============================================"