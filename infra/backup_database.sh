#!/bin/bash
# PostgreSQL 数据库自动备份脚本
# 用法: ./backup_database.sh [保留天数]
# 默认保留 7 天的备份

set -euo pipefail

# 配置
BACKUP_DIR="/opt/nuotao/backups"
RETENTION_DAYS="${1:-7}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ENV_FILE="/opt/nuotao/backend/.env"

# 加载环境变量（正确路径）
# Extract DATABASE_URL from .env (do NOT source entire .env - values with spaces break bash)
if [ -f "$ENV_FILE" ]; then
    DATABASE_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
    export DATABASE_URL
fi

# 从 DATABASE_URL 解析连接参数（优先）
if [ -n "${DATABASE_URL:-}" ]; then
    DB_USER=$(echo "$DATABASE_URL" | sed -E 's|.*://([^:]+):.*|\1|')
    DB_PASSWORD=$(echo "$DATABASE_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
    DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):.*|\1|')
    DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*@[^:]+:([^/]+)/.*|\1|')
    DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|.*/([^?]+).*|\1|')
else
    DB_NAME="${POSTGRES_DB:-nuotao}"
    DB_USER="${POSTGRES_USER:-nuotao}"
    DB_HOST="${POSTGRES_HOST:-localhost}"
    DB_PORT="${POSTGRES_PORT:-5432}"
    DB_PASSWORD="${POSTGRES_PASSWORD:-}"
fi

export PGPASSWORD="$DB_PASSWORD"

echo "=== 数据库备份开始: $(date) ==="
echo "数据库: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo "备份目录: ${BACKUP_DIR}"
echo "保留天数: ${RETENTION_DAYS}"

# 创建备份目录
mkdir -p "${BACKUP_DIR}"

# 执行备份
BACKUP_FILE="${BACKUP_DIR}/nuotao_${TIMESTAMP}.sql.gz"
echo "正在备份到: ${BACKUP_FILE}"

pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "${BACKUP_FILE}"

# 检查备份是否成功
BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
if [ -f "${BACKUP_FILE}" ] && [ "$(stat -c%s "${BACKUP_FILE}")" -gt 100 ]; then
    echo "备份成功: ${BACKUP_FILE} (${BACKUP_SIZE})"
else
    echo "备份失败: 文件过小或不存在"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# 清理过期备份
echo "清理 ${RETENTION_DAYS} 天前的备份..."
find "${BACKUP_DIR}" -name "nuotao_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete -print

# 列出当前备份
echo ""
echo "=== 当前备份列表 ==="
ls -lh "${BACKUP_DIR}"/nuotao_*.sql.gz 2>/dev/null || echo "无备份文件"

echo ""
echo "=== 数据库备份完成: $(date) ==="
