#!/bin/bash
# ============================================
# Nuotao AI OS - 生产环境部署脚本
# ============================================
# 功能：
#   1. 克隆/更新代码
#   2. 安装 Python 依赖
#   3. 安装前端依赖并构建
#   4. 配置环境变量
#   5. 数据库迁移
#   6. 配置 systemd 服务
#   7. 配置 Nginx
#   8. 启动服务
#
# 前置条件：
#   - 已运行 server-setup.sh
#   - 已配置 SSH 密钥或 Git 访问权限
#   - 已准备好生产环境配置
#
# 用法：
#   sudo bash deploy-production.sh
# ============================================

set -e

# 配置
APP_DIR="/opt/nuotao-ai-os"
APP_USER="nuotao"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
LOG_DIR="/var/log/nuotao"
BACKUP_DIR="/var/backups/nuotao"
GIT_REPO="git@github.com:your-org/nuotao-ai-os.git"  # 替换为实际仓库地址
DOMAIN="nuotaooutdoor.com"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 权限运行: sudo bash $0"
    exit 1
fi

echo "============================================"
echo " Nuotao AI OS - Production Deployment"
echo "============================================"
echo ""

# ============================================
# 1. 克隆/更新代码
# ============================================
log_info "Step 1/8: 克隆/更新代码..."

if [ -d "$APP_DIR/.git" ]; then
    log_info "更新现有代码..."
    cd $APP_DIR
    sudo -u $APP_USER git pull origin main
else
    log_info "克隆代码仓库..."
    mkdir -p $APP_DIR
    chown $APP_USER:$APP_USER $APP_DIR
    sudo -u $APP_USER git clone $GIT_REPO $APP_DIR
fi

log_success "代码更新完成"

# ============================================
# 2. 安装 Python 依赖
# ============================================
log_info "Step 2/8: 安装 Python 依赖..."

cd $BACKEND_DIR

# 创建虚拟环境
if [ ! -d "$BACKEND_DIR/.venv" ]; then
    sudo -u $APP_USER python3.12 -m venv .venv
fi

# 安装依赖
sudo -u $APP_USER $BACKEND_DIR/.venv/bin/pip install --upgrade pip
sudo -u $APP_USER $BACKEND_DIR/.venv/bin/pip install -r requirements.txt
sudo -u $APP_USER $BACKEND_DIR/.venv/bin/pip install gunicorn uvicorn[standard]

log_success "Python 依赖安装完成"

# ============================================
# 3. 安装前端依赖并构建
# ============================================
log_info "Step 3/8: 前端构建..."

cd $FRONTEND_DIR

sudo -u $APP_USER npm ci
sudo -u $APP_USER npm run build

log_success "前端构建完成"

# ============================================
# 4. 配置环境变量
# ============================================
log_info "Step 4/8: 配置环境变量..."

if [ ! -f "$BACKEND_DIR/.env" ]; then
    log_warning "未找到 .env 文件，从模板复制..."
    sudo -u $APP_USER cp $BACKEND_DIR/.env.production.template $BACKEND_DIR/.env
    log_warning "请编辑 $BACKEND_DIR/.env 配置生产环境密钥"
else
    log_info ".env 文件已存在"
fi

log_success "环境变量配置完成"

# ============================================
# 5. 数据库迁移
# ============================================
log_info "Step 5/8: 数据库迁移..."

cd $BACKEND_DIR

# 创建数据库表（使用 SQLAlchemy create_all）
sudo -u $APP_USER $BACKEND_DIR/.venv/bin/python -c "
import asyncio
from app.core.database import Base, _engine
async def init():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Database tables created successfully')
asyncio.run(init())
"

log_success "数据库迁移完成"

# ============================================
# 6. 配置 systemd 服务
# ============================================
log_info "Step 6/8: 配置 systemd 服务..."

# 后端服务
cat > /etc/systemd/system/nuotao-backend.service <<EOF
[Unit]
Description=Nuotao AI OS Backend
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/.venv/bin"
ExecStart=$BACKEND_DIR/.venv/bin/gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --access-logfile $LOG_DIR/backend-access.log \
    --error-logfile $LOG_DIR/backend-error.log
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$BACKEND_DIR $LOG_DIR $BACKUP_DIR

[Install]
WantedBy=multi-user.target
EOF

# 监控服务
cat > /etc/systemd/system/nuotao-monitor.service <<EOF
[Unit]
Description=Nuotao AI OS Monitor
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$BACKEND_DIR/.venv/bin/python $APP_DIR/scripts/monitor_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nuotao-backend
systemctl enable nuotao-monitor

log_success "systemd 服务配置完成"

# ============================================
# 7. 配置 Nginx
# ============================================
log_info "Step 7/8: 配置 Nginx..."

# 复制 Nginx 配置
cp $APP_DIR/infra/nginx/nginx-cdn.conf /etc/nginx/sites-available/nuotao.conf

# 替换域名和路径
sed -i "s|nuotaooutdoor.com|$DOMAIN|g" /etc/nginx/sites-available/nuotao.conf
sed -i "s|/opt/nuotao-ai-os/frontend/dist|$FRONTEND_DIR/dist|g" /etc/nginx/sites-available/nuotao.conf

# 启用站点
ln -sf /etc/nginx/sites-available/nuotao.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 测试 Nginx 配置
nginx -t

log_success "Nginx 配置完成"

# ============================================
# 8. 启动服务
# ============================================
log_info "Step 8/8: 启动服务..."

systemctl restart nuotao-backend
systemctl restart nuotao-monitor
systemctl restart nginx

# 等待服务启动
sleep 3

# 检查服务状态
echo ""
log_info "服务状态检查："
systemctl is-active nuotao-backend && log_success "后端服务: 运行中" || log_error "后端服务: 未运行"
systemctl is-active nuotao-monitor && log_success "监控服务: 运行中" || log_warning "监控服务: 未运行"
systemctl is-active nginx && log_success "Nginx: 运行中" || log_error "Nginx: 未运行"
systemctl is-active postgresql && log_success "PostgreSQL: 运行中" || log_error "PostgreSQL: 未运行"
systemctl is-active redis-server && log_success "Redis: 运行中" || log_error "Redis: 未运行"

# ============================================
# 完成
# ============================================
echo ""
echo "============================================"
echo " Production Deployment Complete!"
echo "============================================"
echo ""
echo "访问地址："
echo "  前端: http://$DOMAIN"
echo "  API:  http://$DOMAIN/api/v1"
echo "  文档: http://$DOMAIN/docs"
echo ""
echo "服务管理："
echo "  启动: sudo systemctl start nuotao-backend"
echo "  停止: sudo systemctl stop nuotao-backend"
echo "  重启: sudo systemctl restart nuotao-backend"
echo "  状态: sudo systemctl status nuotao-backend"
echo "  日志: sudo journalctl -u nuotao-backend -f"
echo ""
echo "后续步骤："
echo "  1. 配置 SSL 证书: sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo "  2. 验证 .env 配置: sudo nano $BACKEND_DIR/.env"
echo "  3. 修改默认密码（数据库/Redis/管理员）"
echo "  4. 配置数据库自动备份"
echo "  5. 配置监控告警"
echo "============================================"
