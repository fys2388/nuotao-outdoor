#!/bin/bash
# ============================================
# Nuotao AI OS - 非 Docker 生产环境部署脚本
# ============================================
# 适用：Ubuntu 22.04 / Debian 12 / CentOS 8+
# 功能：系统依赖安装、Python环境、PostgreSQL、Redis、Nginx、服务部署
# ============================================

set -euo pipefail

# 配置
PROJECT_DIR="/opt/nuotao-ai-os"
BACKUP_DIR="/opt/nuotao-ai-os/backups"
LOG_DIR="/opt/nuotao-ai-os/logs"
DATA_DIR="/opt/nuotao-ai-os/backend/data"
DB_USER="nuotao"
DB_NAME="nuotao"
DB_PASSWORD=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)

# 颜色
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
    log_error "请使用 root 用户运行此脚本"
    exit 1
fi

# ============================================
# 1. 系统依赖安装
# ============================================
install_system_deps() {
    log_info "安装系统依赖..."

    if command -v apt &> /dev/null; then
        apt update -y
        apt install -y python3 python3-pip python3-venv python3-dev \
            postgresql postgresql-contrib redis-server nginx \
            build-essential libpq-dev curl git openssl
    elif command -v yum &> /dev/null; then
        yum update -y
        yum groupinstall -y "Development Tools"
        yum install -y python3 python3-pip python3-devel \
            postgresql-server postgresql-contrib redis nginx \
            libpq-devel curl git openssl
        # 初始化 PostgreSQL
        postgresql-setup --initdb
    else
        log_error "不支持的操作系统，请手动安装依赖"
        exit 1
    fi

    log_success "系统依赖安装完成"
}

# ============================================
# 2. 启动数据库和 Redis
# ============================================
setup_services() {
    log_info "启动 PostgreSQL 和 Redis..."

    systemctl enable postgresql redis-server nginx 2>/dev/null || \
    systemctl enable postgresql redis nginx 2>/dev/null || true

    systemctl start postgresql 2>/dev/null || systemctl start postgresql 2>/dev/null || true
    systemctl start redis-server 2>/dev/null || systemctl start redis 2>/dev/null || true

    # 等待 PostgreSQL 启动
    sleep 3

    log_success "数据库和 Redis 已启动"
}

# ============================================
# 3. 创建数据库和用户
# ============================================
setup_database() {
    log_info "创建数据库和用户..."

    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || \
        log_warning "用户可能已存在"
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || \
        log_warning "数据库可能已存在"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

    # 安装 pgvector 扩展（如果可用）
    sudo -u postgres psql -d ${DB_NAME} -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || \
        log_warning "pgvector 扩展不可用，跳过"

    log_success "数据库创建完成"
    log_info "数据库用户: ${DB_USER}"
    log_info "数据库名称: ${DB_NAME}"
    log_info "数据库密码: ${DB_PASSWORD}"
}

# ============================================
# 4. 部署项目代码
# ============================================
deploy_project() {
    log_info "部署项目代码..."

    # 创建目录
    mkdir -p ${PROJECT_DIR} ${BACKUP_DIR} ${LOG_DIR} ${DATA_DIR}

    # 如果是从 Git 仓库部署
    if [ -d "/tmp/nuotao-ai-os" ]; then
        cp -r /tmp/nuotao-ai-os/* ${PROJECT_DIR}/
    elif [ -d "./backend" ]; then
        cp -r ./* ${PROJECT_DIR}/
    else
        log_warning "未找到项目代码，请手动复制到 ${PROJECT_DIR}"
    fi

    # 创建 Python 虚拟环境
    cd ${PROJECT_DIR}/backend
    python3 -m venv .venv
    source .venv/bin/activate

    # 安装 Python 依赖
    pip install --upgrade pip
    pip install -r requirements.txt

    log_success "项目代码部署完成"
}

# ============================================
# 5. 配置环境变量
# ============================================
configure_env() {
    log_info "配置环境变量..."

    cat > ${PROJECT_DIR}/.env << EOF
# 应用配置
APP_NAME="Nuotao AI OS"
ENVIRONMENT="production"
DEBUG=false

# 数据库
DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}"
REDIS_URL="redis://localhost:6379/0"

# JWT
JWT_SECRET_KEY="${JWT_SECRET}"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# WooCommerce（请填入实际值）
WOOCOMMERCE_BASE_URL="https://nuotaooutdoor.com"
WOOCOMMERCE_CONSUMER_KEY=""
WOOCOMMERCE_CONSUMER_SECRET=""
WOOCOMMERCE_WEBHOOK_SECRET=""

# LLM（请填入实际值）
LLM_PROVIDER="deepseek"
DEEPSEEK_API_KEY=""

# 飞书通知（请填入实际值）
FEISHU_WEBHOOK_URL=""

# CORS
CORS_ORIGINS="https://nuotaooutdoor.com,https://www.nuotaooutdoor.com"
EOF

    chmod 600 ${PROJECT_DIR}/.env
    log_success "环境变量配置完成（请编辑 .env 填入 WooCommerce/LLM/飞书密钥）"
}

# ============================================
# 6. 前端构建
# ============================================
build_frontend() {
    log_info "构建前端..."

    # 安装 Node.js
    if ! command -v node &> /dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt install -y nodejs
    fi

    cd ${PROJECT_DIR}/frontend
    npm install
    npm run build

    # 创建静态文件目录
    mkdir -p /var/www/nuotao
    cp -r dist/* /var/www/nuotao/

    log_success "前端构建完成"
}

# ============================================
# 7. 配置 Nginx
# ============================================
configure_nginx() {
    log_info "配置 Nginx..."

    # 复制 Nginx 配置
    cp ${PROJECT_DIR}/infra/nginx/nginx.conf /etc/nginx/nginx.conf

    # 修改上游服务器地址（非 Docker 模式）
    sed -i 's/server backend:8000/server 127.0.0.1:8000/' /etc/nginx/nginx.conf
    sed -i 's/server frontend:80/server 127.0.0.1:8080/' /etc/nginx/nginx.conf

    # 测试配置
    nginx -t

    # 重启 Nginx
    systemctl restart nginx

    log_success "Nginx 配置完成"
}

# ============================================
# 8. 配置 systemd 服务
# ============================================
configure_systemd() {
    log_info "配置 systemd 服务..."

    # 创建运行用户
    id -u nuotao &>/dev/null || useradd -r -s /bin/false nuotao

    # 设置目录权限
    chown -R nuotao:nuotao ${PROJECT_DIR}
    chmod -R 755 ${PROJECT_DIR}

    # 复制服务文件
    cp ${PROJECT_DIR}/infra/systemd/nuotao-backend.service /etc/systemd/system/

    # 重新加载 systemd
    systemctl daemon-reload
    systemctl enable nuotao-backend
    systemctl start nuotao-backend

    log_success "systemd 服务配置完成"
}

# ============================================
# 9. 配置防火墙
# ============================================
configure_firewall() {
    log_info "配置防火墙..."

    if command -v ufw &> /dev/null; then
        ufw allow 80/tcp
        ufw allow 443/tcp
        ufw --force enable
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --reload
    fi

    log_success "防火墙配置完成"
}

# ============================================
# 10. 配置 SSL 证书（可选）
# ============================================
configure_ssl() {
    log_info "配置 SSL 证书（可选）..."
    read -p "是否配置 SSL 证书？需要域名已解析到本服务器 [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        apt install -y certbot python3-certbot-nginx
        certbot --nginx -d nuotaooutdoor.com -d www.nuotaooutdoor.com
        log_success "SSL 证书配置完成"
    else
        log_warning "跳过 SSL 配置，请稍后手动配置"
    fi
}

# ============================================
# 主函数
# ============================================
main() {
    echo "============================================"
    echo "  Nuotao AI OS - 生产环境部署脚本"
    echo "============================================"
    echo ""

    install_system_deps
    setup_services
    setup_database
    deploy_project
    configure_env
    build_frontend
    configure_nginx
    configure_systemd
    configure_firewall
    configure_ssl

    echo ""
    echo "============================================"
    echo "  部署完成！"
    echo "============================================"
    echo ""
    echo "重要信息："
    echo "  数据库密码: ${DB_PASSWORD}"
    echo "  JWT 密钥: ${JWT_SECRET}"
    echo "  项目目录: ${PROJECT_DIR}"
    echo ""
    echo "下一步："
    echo "  1. 编辑 ${PROJECT_DIR}/.env 填入 WooCommerce/LLM/飞书密钥"
    echo "  2. 重启后端服务: systemctl restart nuotao-backend"
    echo "  3. 访问: http://your-server-ip 或 https://your-domain"
    echo "  4. 默认管理员: admin / Admin@2026（请立即修改密码）"
    echo ""
    echo "服务状态检查："
    echo "  systemctl status nuotao-backend"
    echo "  systemctl status nginx"
    echo "  systemctl status postgresql"
    echo "  systemctl status redis-server"
    echo ""
}

main "$@"
