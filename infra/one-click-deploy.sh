#!/bin/bash
# ============================================
# Nuotao AI OS 一键部署脚本
# ============================================
# 适用于 Ubuntu 22.04 / 24.04 / Debian 12
# 功能：环境检查 → 依赖安装 → Docker 安装 → 配置生成 → 服务启动 → 健康检查
#
# 用法：
#   sudo bash one-click-deploy.sh
#   sudo bash one-click-deploy.sh --domain api.example.com --email admin@example.com
# ============================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置变量
DOMAIN=""
EMAIL=""
PROJECT_DIR="/opt/nuotao-ai-os"
POSTGRES_PASSWORD=""
DEEPSEEK_API_KEY=""

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain)
            DOMAIN="$2"
            shift 2
            ;;
        --email)
            EMAIL="$2"
            shift 2
            ;;
        --project-dir)
            PROJECT_DIR="$2"
            shift 2
            ;;
        --help)
            echo "用法: sudo bash one-click-deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --domain DOMAIN     API 域名（如 api.example.com）"
            echo "  --email EMAIL      管理员邮箱（用于 SSL 证书）"
            echo "  --project-dir DIR  项目安装目录（默认 /opt/nuotao-ai-os）"
            echo "  --help             显示帮助信息"
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

# ============================================
# 第 1 步：环境检查
# ============================================
step1_environment_check() {
    echo ""
    echo "============================================"
    echo "第 1 步：环境检查"
    echo "============================================"

    # 检查 root 权限
    if [[ $EUID -ne 0 ]]; then
        log_error "请使用 root 权限运行此脚本：sudo bash one-click-deploy.sh"
        exit 1
    fi
    log_success "Root 权限检查通过"

    # 检查操作系统
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        log_info "操作系统: $NAME $VERSION"
        if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
            log_warning "此脚本主要针对 Ubuntu/Debian，其他系统可能需要手动调整"
        fi
    else
        log_warning "无法检测操作系统"
    fi

    # 检查内存
    MEM_TOTAL=$(free -m | awk '/^Mem:/{print $2}')
    log_info "内存: ${MEM_TOTAL}MB"
    if [[ $MEM_TOTAL -lt 2048 ]]; then
        log_warning "建议至少 2GB 内存，当前 ${MEM_TOTAL}MB 可能影响性能"
    fi

    # 检查磁盘空间
    DISK_AVAILABLE=$(df -m / | awk 'NR==2{print $4}')
    log_info "可用磁盘空间: ${DISK_AVAILABLE}MB"
    if [[ $DISK_AVAILABLE -lt 10240 ]]; then
        log_warning "建议至少 10GB 磁盘空间，当前 ${DISK_AVAILABLE}MB"
    fi

    # 检查端口
    for port in 80 443 5432 6379 8000; do
        if ss -tlnp | grep -q ":$port "; then
            log_warning "端口 $port 已被占用，部署前请确认"
        fi
    done
    log_success "端口检查完成"

    log_success "环境检查完成"
}

# ============================================
# 第 2 步：安装系统依赖
# ============================================
step2_install_dependencies() {
    echo ""
    echo "============================================"
    echo "第 2 步：安装系统依赖"
    echo "============================================"

    log_info "更新软件包列表..."
    apt-get update -qq

    log_info "安装基础工具..."
    apt-get install -y -qq \
        curl \
        wget \
        git \
        vim \
        htop \
        net-tools \
        apt-transport-https \
        ca-certificates \
        gnupg \
        lsb-release \
        software-properties-common \
        ufw \
        fail2ban

    log_success "系统依赖安装完成"
}

# ============================================
# 第 3 步：安装 Docker 和 Docker Compose
# ============================================
step3_install_docker() {
    echo ""
    echo "============================================"
    echo "第 3 步：安装 Docker 和 Docker Compose"
    echo "============================================"

    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
        log_success "Docker 已安装: $DOCKER_VERSION"
    else
        log_info "安装 Docker..."
        curl -fsSL https://get.docker.com | bash
        log_success "Docker 安装完成"
    fi

    # 启动 Docker
    systemctl enable docker
    systemctl start docker

    if command -v docker-compose &> /dev/null; then
        COMPOSE_VERSION=$(docker-compose --version | awk '{print $3}' | tr -d ',')
        log_success "Docker Compose 已安装: $COMPOSE_VERSION"
    else
        log_info "Docker Compose 插件已包含在 Docker 中，使用 'docker compose' 命令"
    fi

    # 验证 Docker 运行
    if docker info &> /dev/null; then
        log_success "Docker 运行正常"
    else
        log_error "Docker 启动失败，请检查系统日志"
        exit 1
    fi
}

# ============================================
# 第 4 步：配置防火墙
# ============================================
step4_configure_firewall() {
    echo ""
    echo "============================================"
    echo "第 4 步：配置防火墙"
    echo "============================================"

    log_info "配置 UFW 防火墙..."

    # 允许 SSH
    ufw allow 22/tcp

    # 允许 HTTP/HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp

    # 允许 Grafana（可选，建议只允许内网）
    # ufw allow 3000/tcp

    # 启用防火墙
    ufw --force enable

    log_success "防火墙配置完成"
    ufw status verbose
}

# ============================================
# 第 5 步：部署项目
# ============================================
step5_deploy_project() {
    echo ""
    echo "============================================"
    echo "第 5 步：部署项目"
    echo "============================================"

    # 创建项目目录
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    # 如果项目目录为空，克隆代码
    if [[ -z "$(ls -A $PROJECT_DIR)" ]]; then
        log_info "项目目录为空，请将代码上传到 $PROJECT_DIR"
        log_info "或者使用 git clone 克隆代码仓库"
        echo ""
        read -p "请输入 Git 仓库地址（留空跳过）: " GIT_REPO
        if [[ -n "$GIT_REPO" ]]; then
            git clone "$GIT_REPO" .
            log_success "代码克隆完成"
        fi
    else
        log_info "项目目录已存在代码，跳过克隆"
    fi

    # 生成随机密码
    POSTGRES_PASSWORD=$(openssl rand -hex 16)
    APP_SECRET_KEY=$(openssl rand -hex 32)
    JWT_SECRET_KEY=$(openssl rand -hex 32)

    # 询问 DeepSeek API Key
    if [[ -z "$DEEPSEEK_API_KEY" ]]; then
        echo ""
        read -p "请输入 DeepSeek API Key（留空跳过，后续可在 .env 中配置）: " DEEPSEEK_API_KEY
    fi

    # 生成 .env 文件
    log_info "生成 .env 配置文件..."
    cat > .env << EOF
# ============================================
# Nuotao AI OS 生产环境配置
# 自动生成时间: $(date)
# ============================================

# 应用配置
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=$APP_SECRET_KEY
APP_LOG_LEVEL=INFO

# 数据库
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=nuotao
POSTGRES_USER=nuotao
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
DATABASE_URL=postgresql+asyncpg://nuotao:$POSTGRES_PASSWORD@postgres:5432/nuotao

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_URL=redis://redis:6379/0

# 任务队列
TASK_QUEUE_BACKEND=redis
TASK_QUEUE_CONCURRENCY=4

# LLM 配置
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_DEFAULT_MODEL=deepseek-chat
LLM_MAX_COST_PER_MONTH_USD=50.0

# JWT 认证
ACTOR_PROVIDER=jwt
JWT_SECRET_KEY=$JWT_SECRET_KEY
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS
CORS_ORIGINS=https://$DOMAIN,http://localhost:5173
CORS_ALLOW_CREDENTIALS=true

# 监控
PROMETHEUS_ENABLED=true

# WooCommerce（可选）
WOOCOMMERCE_BASE_URL=
WOOCOMMERCE_CONSUMER_KEY=
WOOCOMMERCE_CONSUMER_SECRET=
EOF

    log_success ".env 配置文件已生成"
    log_info "数据库密码: $POSTGRES_PASSWORD"
    log_info "请妥善保存这些密码，丢失后无法找回"

    # 创建数据目录
    mkdir -p data/postgres data/redis data/backups data/certbot/conf data/certbot/www data/nginx/logs data/prometheus data/grafana

    log_success "项目部署准备完成"
}

# ============================================
# 第 6 步：启动服务
# ============================================
step6_start_services() {
    echo ""
    echo "============================================"
    echo "第 6 步：启动服务"
    echo "============================================"

    cd "$PROJECT_DIR"

    log_info "构建 Docker 镜像..."
    docker compose -f docker-compose.yml -f docker-compose.prod.yml build

    log_info "启动服务..."
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

    log_info "等待服务启动（30秒）..."
    sleep 30

    # 检查服务状态
    log_info "服务状态:"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

    # 健康检查
    log_info "执行健康检查..."
    if curl -s http://localhost:8000/api/v1/healthz | grep -q "ok"; then
        log_success "API 服务健康检查通过"
    else
        log_warning "API 服务健康检查失败，请检查日志: docker compose logs api"
    fi

    if curl -s http://localhost:8000/metrics | grep -q "nuotao_"; then
        log_success "Metrics 端点正常"
    else
        log_warning "Metrics 端点检查失败"
    fi

    log_success "服务启动完成"
}

# ============================================
# 第 7 步：配置 SSL 证书（可选）
# ============================================
step7_configure_ssl() {
    echo ""
    echo "============================================"
    echo "第 7 步：配置 SSL 证书（可选）"
    echo "============================================"

    if [[ -z "$DOMAIN" ]]; then
        read -p "请输入域名（如 api.example.com，留空跳过 SSL 配置）: " DOMAIN
    fi

    if [[ -z "$DOMAIN" ]]; then
        log_warning "跳过 SSL 配置"
        return
    fi

    if [[ -z "$EMAIL" ]]; then
        read -p "请输入管理员邮箱（用于 SSL 证书通知）: " EMAIL
    fi

    log_info "为域名 $DOMAIN 申请 Let's Encrypt SSL 证书..."

    # 安装 Certbot
    apt-get install -y -qq certbot

    # 停止 Nginx 容器（如果在运行）
    cd "$PROJECT_DIR"
    docker compose stop nginx 2>/dev/null || true

    # 申请证书
    certbot certonly --standalone \
        -d "$DOMAIN" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive

    # 复制证书到项目目录
    mkdir -p data/certbot/conf/live/$DOMAIN
    cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem data/certbot/conf/live/$DOMAIN/
    cp /etc/letsencrypt/live/$DOMAIN/privkey.pem data/certbot/conf/live/$DOMAIN/

    # 更新 Nginx 配置中的域名
    sed -i "s/your-domain.com/$DOMAIN/g" infra/nginx/nginx.conf

    # 重启 Nginx
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d nginx

    log_success "SSL 证书配置完成"
    log_info "请确保域名 DNS 已解析到服务器 IP"
    log_info "访问 https://$DOMAIN 验证 SSL 证书"
}

# ============================================
# 第 8 步：部署完成总结
# ============================================
step8_summary() {
    echo ""
    echo "============================================"
    echo "🎉 部署完成！"
    echo "============================================"
    echo ""
    echo "📋 部署信息:"
    echo "  项目目录: $PROJECT_DIR"
    echo "  数据库密码: $POSTGRES_PASSWORD"
    echo ""
    echo "🌐 访问地址:"
    echo "  API 文档: http://localhost:8000/docs"
    echo "  健康检查: http://localhost:8000/api/v1/healthz"
    echo "  Metrics: http://localhost:8000/metrics"
    if [[ -n "$DOMAIN" ]]; then
        echo "  生产域名: https://$DOMAIN"
    fi
    echo ""
    echo "🔧 常用命令:"
    echo "  查看服务状态: cd $PROJECT_DIR && docker compose ps"
    echo "  查看日志: cd $PROJECT_DIR && docker compose logs -f"
    echo "  重启服务: cd $PROJECT_DIR && docker compose restart"
    echo "  停止服务: cd $PROJECT_DIR && docker compose down"
    echo "  备份数据库: docker compose exec postgres pg_dump -U nuotao nuotao | gzip > backup.sql.gz"
    echo ""
    echo "📚 相关文档:"
    echo "  部署指南: docs/deployment_guide.md"
    echo "  WooCommerce 配置: docs/woocommerce_quickstart.md"
    echo "  监控配置: infra/prometheus/prometheus.yml"
    echo ""
    echo "⚠️  安全提示:"
    echo "  1. 请立即修改数据库密码和 JWT 密钥"
    echo "  2. 请配置防火墙，只开放必要端口"
    echo "  3. 请定期备份数据库"
    echo "  4. 请配置 SSL 证书（生产环境必须）"
    echo ""
}

# ============================================
# 主函数
# ============================================
main() {
    echo ""
    echo "============================================"
    echo "  Nuotao AI OS 一键部署脚本"
    echo "============================================"
    echo ""

    step1_environment_check
    step2_install_dependencies
    step3_install_docker
    step4_configure_firewall
    step5_deploy_project
    step6_start_services
    step7_configure_ssl
    step8_summary
}

# 运行主函数
main
