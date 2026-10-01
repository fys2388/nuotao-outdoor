#!/bin/bash
# ============================================
# Nuotao AI OS - Staging 环境部署脚本
# ============================================
# 在服务器上执行，部署到独立 staging 环境
# 
# 用法：
#   sudo bash deploy-staging.sh
#   sudo bash deploy-staging.sh --skip-db       # 跳过数据库创建
#   sudo bash deploy-staging.sh --skip-seed     # 跳过数据初始化
# ============================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 配置
STAGING_DIR="/opt/nuotao/staging"
FRONTEND_DIR="/var/www/nuotao-staging"
DB_NAME="nuotao_staging"
DB_USER="nuotao"
BACKEND_PORT=8001
FRONTEND_PORT=8082

# 解析参数
SKIP_DB=false
SKIP_SEED=false
SKIP_FRONTEND=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-db)
            SKIP_DB=true
            shift
            ;;
        --skip-seed)
            SKIP_SEED=true
            shift
            ;;
        --skip-frontend)
            SKIP_FRONTEND=true
            shift
            ;;
        --help)
            echo "用法：sudo bash deploy-staging.sh [选项]"
            echo ""
            echo "选项："
            echo "  --skip-db        跳过数据库创建"
            echo "  --skip-seed      跳过数据初始化"
            echo "  --skip-frontend  跳过前端部署"
            echo "  --help           显示帮助"
            exit 0
            ;;
        *)
            log_error "未知参数：$1"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "Nuotao AI OS - Staging 环境部署"
echo "============================================"
echo ""

# ============================================
# 第 1 步：环境检查
# ============================================
step1_environment_check() {
    log_info "第 1 步：环境检查"
    
    # 检查 root 权限
    if [[ $EUID -ne 0 ]]; then
        log_error "请使用 root 权限运行此脚本：sudo bash deploy-staging.sh"
        exit 1
    fi
    
    # 检查代码目录
    if [[ ! -d "$STAGING_DIR" ]]; then
        log_error "staging 代码目录不存在：$STAGING_DIR"
        log_info "请先同步代码到 staging 目录"
        exit 1
    fi
    
    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    
    # 检查 Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js 未安装"
        exit 1
    fi
    
    # 检查 PostgreSQL
    if ! command -v psql &> /dev/null; then
        log_error "PostgreSQL 未安装"
        exit 1
    fi
    
    log_success "环境检查通过"
}

# ============================================
# 第 2 步：创建 staging 数据库
# ============================================
step2_create_database() {
    if [[ "$SKIP_DB" == true ]]; then
        log_warning "跳过数据库创建"
        return
    fi
    
    log_info "第 2 步：创建 staging 数据库"
    
    # 检查数据库是否已存在
    if sudo -u postgres psql -lqt | cut -d\| -f1 | grep -qw "$DB_NAME"; then
        log_warning "数据库 $DB_NAME 已存在，跳过创建"
    else
        log_info "创建数据库 $DB_NAME..."
        sudo -u postgres createdb "$DB_NAME" -O "$DB_USER"
        log_success "数据库创建完成"
    fi
    
    # 确保 nuotao 用户存在
    sudo -u postgres psql -c "DO \$$ DECLARE BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN CREATE ROLE $DB_USER LOGIN PASSWORD 'change_me_in_production'; END IF; END \$$;" 2>/dev/null || true
}

# ============================================
# 第 3 步：配置 staging .env
# ============================================
step3_configure_env() {
    log_info "第 3 步：配置 staging .env"
    
    local ENV_FILE="$STAGING_DIR/backend/.env"
    local PROD_ENV="/opt/nuotao/backend/.env"
    
    if [[ ! -f "$PROD_ENV" ]]; then
        log_error "生产环境 .env 文件不存在：$PROD_ENV"
        exit 1
    fi
    
    # 复制生产 .env 到 staging
    cp "$PROD_ENV" "$ENV_FILE"
    log_info "已复制生产 .env 到 staging"
    
    # 修改数据库配置
    sed -i "s|DATABASE_URL=postgresql://[^@]*@[^/]*\(.*\)|DATABASE_URL=postgresql://\${DB_USER}:\${DB_PASSWORD}\@\1|" "$ENV_FILE"
    
    # 修改端口
    sed -i "s|API_PORT=8000|API_PORT=$BACKEND_PORT|" "$ENV_FILE"
    sed -i "s|FRONTEND_PORT=8081|FRONTEND_PORT=$FRONTEND_PORT|" "$ENV_FILE"
    
    # 添加 staging 标记
    echo "" >> "$ENV_FILE"
    echo "# Staging 环境标记" >> "$ENV_FILE"
    echo "ENVIRONMENT=staging" >> "$ENV_FILE"
    
    log_success ".env 配置完成"
}

# ============================================
# 第 4 步：安装后端依赖和迁移
# ============================================
step4_setup_backend() {
    log_info "第 4 步：安装后端依赖和数据库迁移"
    
    cd "$STAGING_DIR/backend"
    
    # 创建虚拟环境
    if [[ ! -d ".venv" ]]; then
        log_info "创建 Python 虚拟环境..."
        python3 -m venv .venv
    fi
    
    # 激活虚拟环境
    source .venv/bin/activate
    
    # 安装依赖
    log_info "安装后端依赖..."
    pip install -e . --quiet 2>/dev/null || pip install -r requirements.txt --quiet
    
    # 运行数据库迁移
    log_info "运行数据库迁移..."
    if alembic upgrade head; then
        log_success "数据库迁移完成"
    else
        log_error "数据库迁移失败"
        exit 1
    fi
    
    # 确保表存在
    if [[ -f "/opt/nuotao/infra/ensure_tables.py" ]]; then
        python3 /opt/nuotao/infra/ensure_tables.py 2>&1 || log_warning "表检查脚本执行失败（非阻塞）"
    fi
}

# ============================================
# 第 5 步：种子数据初始化
# ============================================
step5_seed_data() {
    if [[ "$SKIP_SEED" == true ]]; then
        log_warning "跳过数据初始化"
        return
    fi
    
    log_info "第 5 步：种子数据初始化"
    
    cd "$STAGING_DIR/backend"
    
    # 运行 agent 配置种子
    if [[ -f "scripts/seed_agent_config.py" ]]; then
        source .venv/bin/activate
        python3 scripts/seed_agent_config.py 2>&1 || log_warning "Agent 配置种子执行失败（非阻塞）"
        log_success "Agent 配置种子完成"
    fi
    
    # 运行其他种子脚本
    if [[ -f "scripts/seed_default_data.py" ]]; then
        python3 scripts/seed_default_data.py 2>&1 || log_warning "默认数据种子执行失败（非阻塞）"
    fi
}

# ============================================
# 第 6 步：安装 systemd 服务
# ============================================
step6_install_systemd() {
    log_info "第 6 步：安装 staging systemd 服务"
    
    local SERVICE_TEMPLATE="$STAGING_DIR/infra/systemd/nuotao-backend-staging.service"
    local SERVICE_FILE="/etc/systemd/system/nuotao-backend-staging.service"
    
    if [[ ! -f "$SERVICE_TEMPLATE" ]]; then
        log_error "systemd 服务模板不存在：$SERVICE_TEMPLATE"
        exit 1
    fi
    
    # 复制服务文件
    cp "$SERVICE_TEMPLATE" "$SERVICE_FILE"
    chmod 644 "$SERVICE_FILE"
    
    # 重新加载 systemd
    systemctl daemon-reload
    
    # 启用并启动服务
    systemctl enable nuotao-backend-staging
    systemctl start nuotao-backend-staging
    
    # 检查服务状态
    sleep 2
    if systemctl is-active --quiet nuotao-backend-staging; then
        log_success "systemd 服务启动成功"
    else
        log_error "systemd 服务启动失败"
        journalctl -u nuotao-backend-staging -n 20 --no-pager
        exit 1
    fi
}

# ============================================
# 第 7 步：部署前端
# ============================================
step7_deploy_frontend() {
    if [[ "$SKIP_FRONTEND" == true ]]; then
        log_warning "跳过前端部署"
        return
    fi
    
    log_info "第 7 步：部署 staging 前端"
    
    # 创建前端目录
    mkdir -p "$FRONTEND_DIR"
    
    # 构建前端
    cd "$STAGING_DIR/frontend"
    
    # 安装依赖
    npm install --silent
    
    # 构建
    npm run build
    
    # 部署到 nginx 目录
    cp -r dist/* "$FRONTEND_DIR/"
    chown -R www-data:www-data "$FRONTEND_DIR"
    
    log_success "前端部署完成"
}

# ============================================
# 第 8 步：配置 nginx
# ============================================
step8_configure_nginx() {
    log_info "第 8 步：配置 staging nginx"
    
    local NGINX_TEMPLATE="$STAGING_DIR/infra/nginx/staging-console.conf"
    local NGINX_AVAILABLE="/etc/nginx/sites-available/nuotao-staging"
    local NGINX_ENABLED="/etc/nginx/sites-enabled/nuotao-staging"
    
    if [[ ! -f "$NGINX_TEMPLATE" ]]; then
        log_error "nginx 配置模板不存在：$NGINX_TEMPLATE"
        exit 1
    fi
    
    # 复制 nginx 配置
    cp "$NGINX_TEMPLATE" "$NGINX_AVAILABLE"
    
    # 创建符号链接
    ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
    
    # 测试 nginx 配置
    if nginx -t; then
        log_success "nginx 配置测试通过"
        
        # 重新加载 nginx
        systemctl reload nginx
        log_success "nginx 重新加载完成"
    else
        log_error "nginx 配置测试失败"
        exit 1
    fi
}

# ============================================
# 第 9 步：健康检查
# ============================================
step9_health_check() {
    log_info "第 9 步：健康检查"
    
    sleep 3
    
    # 检查后端
    local BACKEND_URL="http://127.0.0.1:$BACKEND_PORT/api/v1/readyz"
    local BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL" || echo "000")
    
    if [[ "$BACKEND_STATUS" == "200" ]]; then
        log_success "后端健康检查通过：$BACKEND_URL"
    else
        log_error "后端健康检查失败：HTTP $BACKEND_STATUS"
    fi
    
    # 检查前端
    local FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT/"
    local FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" || echo "000")
    
    if [[ "$FRONTEND_STATUS" == "200" ]]; then
        log_success "前端健康检查通过：$FRONTEND_URL"
    else
        log_warning "前端健康检查：HTTP $FRONTEND_STATUS（可能正常）"
    fi
}

# ============================================
# 主流程
# ============================================
main() {
    step1_environment_check
    step2_create_database
    step3_configure_env
    step4_setup_backend
    step5_seed_data
    step6_install_systemd
    step7_deploy_frontend
    step8_configure_nginx
    step9_health_check
    
    echo ""
    echo "============================================"
    echo "Staging 部署完成！"
    echo "============================================"
    echo ""
    echo "服务信息："
    echo "  后端：http://127.0.0.1:$BACKEND_PORT/api/v1/readyz"
    echo "  前端：http://127.0.0.1:$FRONTEND_PORT/"
    echo ""
    echo "服务管理："
    echo "  查看状态：systemctl status nuotao-backend-staging"
    echo "  查看日志：journalctl -u nuotao-backend-staging -f"
    echo "  停止服务：systemctl stop nuotao-backend-staging"
    echo ""
    echo "数据库："
    echo "  数据库名：$DB_NAME"
    echo "  用户：$DB_USER"
    echo ""
    log_success "部署完成！"
}

# 运行主流程
main