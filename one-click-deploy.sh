#!/bin/bash
# ============================================================
# Nuotao AI OS - 一键部署脚本
# 用法: ./one-click-deploy.sh
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查是否为 root
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 用户运行此脚本"
    exit 1
fi

# 检查是否在正确的目录
if [ ! -f "docker-compose.prod.yml" ]; then
    log_error "请在项目根目录运行此脚本（需要 docker-compose.prod.yml）"
    exit 1
fi

echo ""
echo "============================================================"
echo "  Nuotao AI OS 一键部署脚本"
echo "============================================================"
echo ""

# ============================================================
# 步骤 1: 系统初始化
# ============================================================
log_info "步骤 1/6: 系统初始化..."

if [ -f "infra/setup-server.sh" ]; then
    bash infra/setup-server.sh
    log_success "系统初始化完成"
else
    log_warn "未找到 setup-server.sh，跳过系统初始化"
fi

# ============================================================
# 步骤 2: 配置环境变量
# ============================================================
log_info "步骤 2/6: 配置环境变量..."

if [ ! -f ".env" ]; then
    log_warn "未找到 .env 文件，正在从模板创建..."
    cp .env.production.example .env

    # 生成随机密钥
    SECRET_KEY=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 16)
    REDIS_PASSWORD=$(openssl rand -hex 16)

    # 替换配置
    sed -i "s/your-secret-key/$SECRET_KEY/g" .env
    sed -i "s/your-db-password/$DB_PASSWORD/g" .env
    sed -i "s/your-redis-password/$REDIS_PASSWORD/g" .env

    log_success "环境变量已创建"
    log_warn "请编辑 .env 文件，填写以下必要配置："
    echo "  - DEEPSEEK_API_KEY: LLM API 密钥"
    echo "  - WOOCOMMERCE_BASE_URL: WooCommerce 店铺 URL"
    echo "  - WOOCOMMERCE_CONSUMER_KEY: WooCommerce Consumer Key"
    echo "  - WOOCOMMERCE_CONSUMER_SECRET: WooCommerce Consumer Secret"
    echo "  - DOMAIN: 你的域名"
    echo "  - SSL_EMAIL: SSL 证书邮箱"
    echo ""
    read -p "编辑完成后按回车键继续..."
else
    log_success ".env 文件已存在"
fi

# ============================================================
# 步骤 3: 构建 Docker 镜像
# ============================================================
log_info "步骤 3/6: 构建 Docker 镜像..."

docker compose -f docker-compose.prod.yml build
log_success "Docker 镜像构建完成"

# ============================================================
# 步骤 4: 启动服务
# ============================================================
log_info "步骤 4/6: 启动服务..."

docker compose -f docker-compose.prod.yml up -d
log_success "服务已启动"

# 等待服务启动
log_info "等待服务启动（10 秒）..."
sleep 10

# ============================================================
# 步骤 5: 运行数据库迁移
# ============================================================
log_info "步骤 5/6: 运行数据库迁移..."

docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head || log_warn "数据库迁移失败，请手动运行"
log_success "数据库迁移完成"

# ============================================================
# 步骤 6: 健康检查
# ============================================================
log_info "步骤 6/6: 健康检查..."

sleep 5

# 检查后端
if curl -s http://localhost:8000/api/v1/healthz | grep -q "ok"; then
    log_success "后端服务健康"
else
    log_error "后端服务健康检查失败"
fi

# 检查前端
if curl -s -o /dev/null -w "%{http_code}" http://localhost:80 | grep -q "200\|301\|302"; then
    log_success "前端服务健康"
else
    log_warn "前端服务健康检查失败（可能需要配置 Nginx）"
fi

# 检查 PostgreSQL
if docker compose -f docker-compose.prod.yml exec -T postgres pg_isready -U nuotao 2>/dev/null | grep -q "accepting"; then
    log_success "PostgreSQL 健康"
else
    log_error "PostgreSQL 健康检查失败"
fi

# 检查 Redis
if docker compose -f docker-compose.prod.yml exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    log_success "Redis 健康"
else
    log_error "Redis 健康检查失败"
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "============================================================"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "============================================================"
echo ""
echo "访问地址："
echo "  - 前端: http://your-domain.com（配置域名后）"
echo "  - API: http://your-domain.com/api/v1"
echo "  - Swagger: http://your-domain.com/docs"
echo "  - Grafana: http://your-domain.com/grafana（默认账号: admin/admin）"
echo "  - Prometheus: http://your-domain.com/prometheus"
echo ""
echo "本地访问地址："
echo "  - 前端: http://localhost"
echo "  - API: http://localhost:8000"
echo "  - Swagger: http://localhost:8000/docs"
echo "  - Grafana: http://localhost:3000"
echo "  - Prometheus: http://localhost:9090"
echo ""
echo "常用命令："
echo "  - 查看状态: ./infra/deploy.sh status"
echo "  - 查看日志: ./infra/deploy.sh logs"
echo "  - 重启服务: ./infra/deploy.sh restart"
echo "  - 备份数据: ./infra/deploy.sh backup"
echo "  - 停止服务: ./infra/deploy.sh stop"
echo ""
echo "下一步："
echo "  1. 配置域名 DNS 解析"
echo "  2. 配置 SSL 证书（HTTPS）"
echo "  3. 导入 Grafana 仪表盘"
echo "  4. 配置 Alertmanager 通知"
echo "  5. 修改默认密码（Grafana、数据库等）"
echo ""
echo "详细文档: docs/cloud_deployment_guide.md"
echo "============================================================"
