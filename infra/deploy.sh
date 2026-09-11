#!/bin/bash
# ============================================================
# Nuotao AI OS - 一键部署管理工具
# 用法: ./deploy.sh [命令]
# 命令:
#   deploy    - 部署最新版本
#   rollback  - 回滚到上一个版本
#   status    - 查看服务状态
#   logs      - 查看日志
#   restart   - 重启服务
#   stop      - 停止服务
#   backup    - 备份数据库
#   restore   - 恢复数据库
#   health    - 健康检查
# ============================================================

set -e

# 配置
APP_DIR="/opt/nuotao-ai-os"
BACKUP_DIR="${APP_DIR}/backups"
LOG_DIR="${APP_DIR}/logs"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查环境
check_env() {
    if [ ! -f "${APP_DIR}/${ENV_FILE}" ]; then
        log_error "未找到 .env 文件，请先复制 .env.production.example 并填写配置"
        exit 1
    fi
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先运行 setup-server.sh"
        exit 1
    fi
}

# 部署
deploy() {
    log_info "开始部署 Nuotao AI OS..."

    check_env
    cd "${APP_DIR}"

    # 1. 备份当前版本
    log_info "备份当前版本..."
    backup_database
    cp -r backend "backups/backend_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

    # 2. 拉取最新代码 (如果是 Git 仓库)
    if [ -d ".git" ]; then
        log_info "拉取最新代码..."
        git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || log_warn "Git 拉取失败，使用当前代码"
    fi

    # 3. 构建镜像
    log_info "构建 Docker 镜像..."
    docker compose -f "${COMPOSE_FILE}" build --no-cache

    # 4. 停止旧服务
    log_info "停止旧服务..."
    docker compose -f "${COMPOSE_FILE}" down

    # 5. 启动新服务
    log_info "启动新服务..."
    docker compose -f "${COMPOSE_FILE}" up -d

    # 6. 等待服务启动
    log_info "等待服务启动..."
    sleep 10

    # 7. 运行数据库迁移
    log_info "运行数据库迁移..."
    docker compose -f "${COMPOSE_FILE}" exec -T backend alembic upgrade head 2>/dev/null || log_warn "数据库迁移失败，请手动运行"

    # 8. 健康检查
    log_info "健康检查..."
    sleep 5
    if curl -s http://localhost:8000/api/v1/healthz | grep -q "ok"; then
        log_success "后端服务健康"
    else
        log_warn "后端服务健康检查失败，请检查日志"
    fi

    log_success "部署完成！"
    echo ""
    echo "访问地址:"
    echo "  - 前端: https://your-domain.com"
    echo "  - API: https://your-domain.com/api/v1"
    echo "  - Swagger: https://your-domain.com/docs"
    echo "  - Grafana: https://your-domain.com/grafana"
    echo "  - Prometheus: https://your-domain.com/prometheus"
}

# 回滚
rollback() {
    log_info "回滚到上一个版本..."
    cd "${APP_DIR}"

    # 找到最近的备份
    LATEST_BACKUP=$(ls -td backups/backend_* 2>/dev/null | head -1)
    if [ -z "${LATEST_BACKUP}" ]; then
        log_error "未找到备份，无法回滚"
        exit 1
    fi

    log_info "使用备份: ${LATEST_BACKUP}"

    # 停止服务
    docker compose -f "${COMPOSE_FILE}" down

    # 恢复代码
    rm -rf backend
    cp -r "${LATEST_BACKUP}" backend

    # 恢复数据库
    LATEST_DB=$(ls -t backups/nuotao_*.sql.gz 2>/dev/null | head -1)
    if [ -n "${LATEST_DB}" ]; then
        log_info "恢复数据库: ${LATEST_DB}"
        gunzip -c "${LATEST_DB}" | docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U nuotao -d nuotao
    fi

    # 重新构建并启动
    docker compose -f "${COMPOSE_FILE}" build
    docker compose -f "${COMPOSE_FILE}" up -d

    log_success "回滚完成！"
}

# 状态
status() {
    cd "${APP_DIR}"
    echo "============================================================"
    echo "Nuotao AI OS 服务状态"
    echo "============================================================"
    echo ""
    docker compose -f "${COMPOSE_FILE}" ps
    echo ""
    echo "============================================================"
    echo "资源使用情况"
    echo "============================================================"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
}

# 日志
logs() {
    cd "${APP_DIR}"
    SERVICE=${1:-backend}
    docker compose -f "${COMPOSE_FILE}" logs -f --tail=100 "${SERVICE}"
}

# 重启
restart() {
    cd "${APP_DIR}"
    SERVICE=${1:-all}
    if [ "${SERVICE}" = "all" ]; then
        docker compose -f "${COMPOSE_FILE}" restart
    else
        docker compose -f "${COMPOSE_FILE}" restart "${SERVICE}"
    fi
    log_success "重启完成"
}

# 停止
stop() {
    cd "${APP_DIR}"
    docker compose -f "${COMPOSE_FILE}" down
    log_success "服务已停止"
}

# 备份数据库
backup_database() {
    cd "${APP_DIR}"
    mkdir -p "${BACKUP_DIR}"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/nuotao_${TIMESTAMP}.sql.gz"

    log_info "备份数据库到 ${BACKUP_FILE}..."
    docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_dump -U nuotao nuotao | gzip > "${BACKUP_FILE}"

    # 清理 7 天前的备份
    find "${BACKUP_DIR}" -name "nuotao_*.sql.gz" -mtime +7 -delete

    log_success "数据库备份完成: ${BACKUP_FILE}"
}

# 恢复数据库
restore_database() {
    cd "${APP_DIR}"
    BACKUP_FILE=${1}
    if [ -z "${BACKUP_FILE}" ]; then
        BACKUP_FILE=$(ls -t backups/nuotao_*.sql.gz 2>/dev/null | head -1)
    fi
    if [ -z "${BACKUP_FILE}" ] || [ ! -f "${BACKUP_FILE}" ]; then
        log_error "未找到备份文件"
        exit 1
    fi

    log_warn "即将恢复数据库: ${BACKUP_FILE}"
    read -p "确认恢复？(y/N): " confirm
    if [ "${confirm}" != "y" ] && [ "${confirm}" != "Y" ]; then
        log_info "已取消"
        exit 0
    fi

    gunzip -c "${BACKUP_FILE}" | docker compose -f "${COMPOSE_FILE}" exec -T postgres psql -U nuotao -d nuotao
    log_success "数据库恢复完成"
}

# 健康检查
health() {
    echo "============================================================"
    echo "Nuotao AI OS 健康检查"
    echo "============================================================"
    echo ""

    # 后端
    if curl -s http://localhost:8000/api/v1/healthz | grep -q "ok"; then
        echo -e "${GREEN}✅ 后端服务: 正常${NC}"
    else
        echo -e "${RED}❌ 后端服务: 异常${NC}"
    fi

    # PostgreSQL
    if docker compose -f "${APP_DIR}/${COMPOSE_FILE}" exec -T postgres pg_isready -U nuotao 2>/dev/null | grep -q "accepting"; then
        echo -e "${GREEN}✅ PostgreSQL: 正常${NC}"
    else
        echo -e "${RED}❌ PostgreSQL: 异常${NC}"
    fi

    # Redis
    if docker compose -f "${APP_DIR}/${COMPOSE_FILE}" exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo -e "${GREEN}✅ Redis: 正常${NC}"
    else
        echo -e "${RED}❌ Redis: 异常${NC}"
    fi

    # Nginx
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:80 | grep -q "200\|301\|302"; then
        echo -e "${GREEN}✅ Nginx: 正常${NC}"
    else
        echo -e "${RED}❌ Nginx: 异常${NC}"
    fi

    # Prometheus
    if curl -s http://localhost:9090/-/ready 2>/dev/null | grep -q "Ready"; then
        echo -e "${GREEN}✅ Prometheus: 正常${NC}"
    else
        echo -e "${YELLOW}⚠️  Prometheus: 未运行或未配置${NC}"
    fi

    # Grafana
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null | grep -q "200\|302"; then
        echo -e "${GREEN}✅ Grafana: 正常${NC}"
    else
        echo -e "${YELLOW}⚠️  Grafana: 未运行或未配置${NC}"
    fi

    echo ""
    echo "============================================================"
}

# 主函数
main() {
    COMMAND=${1:-help}

    case ${COMMAND} in
        deploy)
            deploy
            ;;
        rollback)
            rollback
            ;;
        status)
            status
            ;;
        logs)
            logs ${2}
            ;;
        restart)
            restart ${2}
            ;;
        stop)
            stop
            ;;
        backup)
            backup_database
            ;;
        restore)
            restore_database ${2}
            ;;
        health)
            health
            ;;
        help|*)
            echo "用法: ./deploy.sh [命令]"
            echo ""
            echo "命令:"
            echo "  deploy    - 部署最新版本"
            echo "  rollback  - 回滚到上一个版本"
            echo "  status    - 查看服务状态"
            echo "  logs [服务] - 查看日志 (默认: backend)"
            echo "  restart [服务] - 重启服务 (默认: all)"
            echo "  stop      - 停止服务"
            echo "  backup    - 备份数据库"
            echo "  restore [文件] - 恢复数据库"
            echo "  health    - 健康检查"
            echo "  help      - 显示帮助"
            ;;
    esac
}

main "$@"
