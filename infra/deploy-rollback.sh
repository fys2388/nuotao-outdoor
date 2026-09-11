#!/bin/bash
# ============================================================
# Nuotao AI OS - 部署回滚脚本
# 用途: 部署失败后自动回滚到上一版本（代码+数据库+服务）
# 用法: ./deploy-rollback.sh [backup_dir]
# ============================================================

set -euo pipefail

APP_DIR="/opt/nuotao"
BACKUP_ROOT="/opt/nuotao/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/opt/nuotao/logs/rollback_${TIMESTAMP}.log"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    log "${RED}[ERROR] $1${NC}"
}

success() {
    log "${GREEN}[SUCCESS] $1${NC}"
}

warn() {
    log "${YELLOW}[WARN] $1${NC}"
}

# ------------------------------------------------------------
# 1. 创建部署前备份（在 deploy.yml 中部署前调用）
# ------------------------------------------------------------
create_backup() {
    local backup_dir="${BACKUP_ROOT}/pre_deploy_${TIMESTAMP}"
    mkdir -p "$backup_dir"

    log "=== 创建部署前备份: $backup_dir ==="

    # 1.1 代码备份（git stash + 当前 commit）
    cd "$APP_DIR"
    local current_commit
    current_commit=$(git rev-parse HEAD)
    echo "$current_commit" > "$backup_dir/git_commit.txt"
    log "当前 commit: $current_commit"

    # 1.2 数据库备份
    log "备份数据库..."
    if [ -f "$APP_DIR/backend/.env" ]; then
        DB_URL=$(grep '^DATABASE_URL=' "$APP_DIR/backend/.env" | cut -d'=' -f2-)
        if [ -n "$DB_URL" ]; then
            # 从 URL 提取连接信息
            DB_HOST=$(echo "$DB_URL" | sed -n 's#.*@\([^:/]*\).*#\1#p')
            DB_PORT=$(echo "$DB_URL" | sed -n 's#.*@[^:]*:\([0-9]*\)/.*#\1#p')
            DB_NAME=$(echo "$DB_URL" | sed -n 's#.*/\([^?]*\).*#\1#p')
            DB_USER=$(echo "$DB_URL" | sed -n 's#.*//\([^:]*\):.*#\1#p')

            if [ -n "$DB_NAME" ]; then
                pg_dump -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "${DB_USER:-nuotao}" "$DB_NAME" > "$backup_dir/database.sql" 2>>"$LOG_FILE" || {
                    warn "数据库备份失败，继续（可能需要手动备份）"
                }
                if [ -f "$backup_dir/database.sql" ]; then
                    local db_size
                    db_size=$(du -h "$backup_dir/database.sql" | cut -f1)
                    success "数据库备份完成: $db_size"
                fi
            fi
        fi
    fi

    # 1.3 前端构建产物备份
    if [ -d "/var/www/nuotao" ]; then
        tar czf "$backup_dir/frontend.tar.gz" -C /var/www nuotao 2>>"$LOG_FILE" || warn "前端备份失败"
        success "前端备份完成"
    fi

    # 1.4 环境变量备份
    cp "$APP_DIR/backend/.env" "$backup_dir/backend.env" 2>/dev/null || true
    cp "$APP_DIR/frontend/.env" "$backup_dir/frontend.env" 2>/dev/null || true

    # 1.5 记录备份信息
    cat > "$backup_dir/backup_info.json" <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "git_commit": "$current_commit",
  "backup_dir": "$backup_dir",
  "database_backed_up": $([ -f "$backup_dir/database.sql" ] && echo true || echo false),
  "frontend_backed_up": $([ -f "$backup_dir/frontend.tar.gz" ] && echo true || echo false)
}
EOF

    echo "$backup_dir" > "$BACKUP_ROOT/LATEST_BACKUP"
    success "=== 备份完成: $backup_dir ==="
    echo "$backup_dir"
}

# ------------------------------------------------------------
# 2. 回滚到指定备份（部署失败后调用）
# ------------------------------------------------------------
rollback() {
    local backup_dir="${1:-}"

    if [ -z "$backup_dir" ]; then
        if [ -f "$BACKUP_ROOT/LATEST_BACKUP" ]; then
            backup_dir=$(cat "$BACKUP_ROOT/LATEST_BACKUP")
            log "使用最新备份: $backup_dir"
        else
            error "未指定备份目录且无 LATEST_BACKUP 记录"
            exit 1
        fi
    fi

    if [ ! -d "$backup_dir" ]; then
        error "备份目录不存在: $backup_dir"
        exit 1
    fi

    log "========================================"
    log "=== 开始回滚: $backup_dir ==="
    log "========================================"

    # 2.1 停止服务
    log "停止后端服务..."
    systemctl stop nuotao-backend 2>>"$LOG_FILE" || warn "停止后端服务失败（可能未运行）"

    # 2.2 代码回滚
    if [ -f "$backup_dir/git_commit.txt" ]; then
        local target_commit
        target_commit=$(cat "$backup_dir/git_commit.txt")
        log "回滚代码到 commit: $target_commit"
        cd "$APP_DIR"
        git fetch --all 2>>"$LOG_FILE" || true
        git reset --hard "$target_commit" 2>>"$LOG_FILE" || {
            error "代码回滚失败"
            exit 1
        }
        success "代码回滚完成"
    else
        warn "备份中无 git commit 记录，跳过代码回滚"
    fi

    # 2.3 数据库回滚（如果有备份）
    if [ -f "$backup_dir/database.sql" ]; then
        warn "数据库回滚需要人工确认（可能丢失部署期间的数据）"
        warn "如需回滚数据库，请手动执行: psql < $backup_dir/database.sql"
        # 自动回滚数据库（谨慎！默认注释掉）
        # if [ -f "$APP_DIR/backend/.env" ]; then
        #     DB_URL=$(grep '^DATABASE_URL=' "$APP_DIR/backend/.env" | cut -d'=' -f2-)
        #     DB_NAME=$(echo "$DB_URL" | sed -n 's#.*/\([^?]*\).*#\1#p')
        #     DB_USER=$(echo "$DB_URL" | sed -n 's#.*//\([^:]*\):.*#\1#p')
        #     psql -U "${DB_USER:-nuotao}" "$DB_NAME" < "$backup_dir/database.sql"
        #     success "数据库回滚完成"
        # fi
    else
        log "无数据库备份，跳过数据库回滚"
    fi

    # 2.4 前端回滚
    if [ -f "$backup_dir/frontend.tar.gz" ]; then
        log "回滚前端..."
        rm -rf /var/www/nuotao/*
        tar xzf "$backup_dir/frontend.tar.gz" -C /var/www 2>>"$LOG_FILE"
        chown -R www-data:www-data /var/www/nuotao
        success "前端回滚完成"
    else
        warn "无前端备份，跳过前端回滚（需要重新构建）"
        cd "$APP_DIR/frontend"
        npm install --silent 2>>"$LOG_FILE" || true
        npm run build 2>>"$LOG_FILE" || warn "前端重新构建失败"
        rm -rf /var/www/nuotao/*
        cp -r dist/* /var/www/nuotao/ 2>>"$LOG_FILE" || true
        chown -R www-data:www-data /var/www/nuotao
    fi

    # 2.5 恢复环境变量
    cp "$backup_dir/backend.env" "$APP_DIR/backend/.env" 2>/dev/null || true

    # 2.6 重新安装依赖并启动服务
    log "重新安装后端依赖..."
    cd "$APP_DIR/backend"
    source .venv/bin/activate 2>/dev/null || true
    pip install -e . --quiet 2>>"$LOG_FILE" || pip install -r requirements.txt --quiet 2>>"$LOG_FILE" || warn "依赖安装失败"

    log "启动后端服务..."
    systemctl start nuotao-backend 2>>"$LOG_FILE" || error "启动后端服务失败"
    sleep 3

    # 2.7 健康检查
    log "健康检查..."
    BACKEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs || true)
    FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/ || true)
    log "Backend: $BACKEND_CODE, Frontend: $FRONTEND_CODE"

    if [ "$BACKEND_CODE" = "200" ] && [ "$FRONTEND_CODE" = "200" ]; then
        success "=== 回滚成功！服务已恢复 ==="
    else
        error "回滚后健康检查失败，请人工排查"
        error "Backend: $BACKEND_CODE, Frontend: $FRONTEND_CODE"
        systemctl status nuotao-backend --no-pager | head -20 || true
        exit 1
    fi

    # 2.8 发送告警
    log "发送回滚告警..."
    # TODO: 调用飞书 webhook 发送告警
    # curl -X POST "$FEISHU_WEBHOOK" -H "Content-Type: application/json" -d "{...}"

    echo ""
    log "回滚完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
    log "回滚日志: $LOG_FILE"
}

# ------------------------------------------------------------
# 3. 清理旧备份（保留最近10个）
# ------------------------------------------------------------
cleanup_old_backups() {
    log "清理旧备份（保留最近10个）..."
    cd "$BACKUP_ROOT"
    ls -dt pre_deploy_* 2>/dev/null | tail -n +11 | while read -r dir; do
        rm -rf "$dir"
        log "已删除旧备份: $dir"
    done
    success "备份清理完成"
}

# ------------------------------------------------------------
# 主入口
# ------------------------------------------------------------
case "${1:-}" in
    backup)
        mkdir -p "$BACKUP_ROOT" "$(dirname "$LOG_FILE")"
        create_backup
        ;;
    rollback)
        mkdir -p "$(dirname "$LOG_FILE")"
        rollback "${2:-}"
        ;;
    cleanup)
        cleanup_old_backups
        ;;
    *)
        echo "用法: $0 {backup|rollback [backup_dir]|cleanup}"
        echo ""
        echo "  backup   - 创建部署前备份"
        echo "  rollback - 回滚到最近备份（或指定备份目录）"
        echo "  cleanup  - 清理旧备份（保留最近10个）"
        exit 1
        ;;
esac
