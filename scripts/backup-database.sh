#!/bin/bash
# ============================================
# Nuotao AI OS - PostgreSQL 数据库自动备份脚本 (Linux)
# ============================================
# 功能：每日自动备份、压缩、清理、验证、飞书通知
# 安装：crontab -e 添加 "0 3 * * * /opt/nuotao-ai-os/scripts/backup-database.sh"
# ============================================

set -euo pipefail

# ========== 配置 ==========
PG_HOST="localhost"
PG_PORT="5432"
PG_USER="nuotao"
PG_DB="nuotao"
PG_PASSWORD="${PG_PASSWORD:-}"  # 从环境变量或 .pgpass 读取

BACKUP_DIR="/opt/nuotao-ai-os/backups/database"
LOG_DIR="/opt/nuotao-ai-os/backups/logs"
RETENTION_DAYS=30
MAX_BACKUPS=30

# 飞书通知
FEISHU_WEBHOOK="${FEISHU_WEBHOOK:-}"
ENABLE_FEISHU_NOTIFY=${ENABLE_FEISHU_NOTIFY:-true}

# ========== 初始化 ==========
timestamp=$(date +"%Y%m%d_%H%M%S")
date=$(date +"%Y-%m-%d")
backup_file="${BACKUP_DIR}/nuotao_${timestamp}.sql"
backup_file_gz="${backup_file}.gz"
log_file="${LOG_DIR}/backup_${date}.log"

mkdir -p "${BACKUP_DIR}" "${LOG_DIR}"

# 日志函数
log() {
    local level="$1"
    local message="$2"
    local log_message="[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] ${message}"
    echo "${log_message}" | tee -a "${log_file}"
}

# 飞书通知
send_feishu() {
    local title="$1"
    local message="$2"
    local color="$3"
    if [ "${ENABLE_FEISHU_NOTIFY}" != "true" ] || [ -z "${FEISHU_WEBHOOK}" ]; then
        return
    fi
    curl -s -X POST "${FEISHU_WEBHOOK}" \
        -H "Content-Type: application/json" \
        -d "{
            \"msg_type\": \"interactive\",
            \"card\": {
                \"header\": {
                    \"title\": {\"tag\": \"plain_text\", \"content\": \"${title}\"},
                    \"template\": \"${color}\"
                },
                \"elements\": [{
                    \"tag\": \"div\",
                    \"text\": {\"tag\": \"plain_text\", \"content\": \"${message}\"}
                }]
            }
        }" > /dev/null 2>&1 || true
}

# ========== 开始备份 ==========
log "INFO" "========== 数据库备份开始 =========="
log "INFO" "数据库: ${PG_USER}@${PG_HOST}:${PG_PORT}/${PG_DB}"
log "INFO" "备份目录: ${BACKUP_DIR}"

export PGPASSWORD="${PG_PASSWORD}"

# 1. 执行 pg_dump
log "INFO" "正在执行 pg_dump..."
if ! pg_dump -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -F p -c -C -f "${backup_file}"; then
    log "ERROR" "pg_dump 执行失败"
    send_feishu "❌ 数据库备份失败" "pg_dump 执行失败\n数据库: ${PG_DB}\n时间: $(date)" "red"
    exit 1
fi

backup_size=$(stat -c%s "${backup_file}" 2>/dev/null || stat -f%z "${backup_file}")
backup_size_mb=$(echo "scale=2; ${backup_size} / 1048576" | bc)
log "INFO" "备份文件生成成功: ${backup_size_mb} MB"

# 2. 压缩
log "INFO" "正在压缩备份文件..."
gzip -f "${backup_file}"
compressed_size=$(stat -c%s "${backup_file_gz}" 2>/dev/null || stat -f%z "${backup_file_gz}")
compressed_size_mb=$(echo "scale=2; ${compressed_size} / 1048576" | bc)
compression_ratio=$(echo "scale=1; ${compressed_size} * 100 / ${backup_size}" | bc)
log "INFO" "压缩完成: ${compressed_size_mb} MB (压缩率: ${compression_ratio}%)"

# 3. 验证完整性
log "INFO" "正在验证备份文件完整性..."
if ! gzip -t "${backup_file_gz}"; then
    log "ERROR" "备份文件完整性验证失败"
    send_feishu "❌ 数据库备份失败" "备份文件完整性验证失败\n数据库: ${PG_DB}" "red"
    exit 1
fi
log "INFO" "备份文件完整性验证通过"

# 4. 清理旧备份
log "INFO" "正在清理超过 ${RETENTION_DAYS} 天的旧备份..."
find "${BACKUP_DIR}" -name "*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete -print | while read f; do
    log "INFO" "已删除旧备份: $(basename "${f}")"
done

# 5. 保留最近 N 个
backup_count=$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f | wc -l)
if [ "${backup_count}" -gt "${MAX_BACKUPS}" ]; then
    find "${BACKUP_DIR}" -name "*.sql.gz" -type f -printf '%T@ %p\n' | sort -n | head -n -${MAX_BACKUPS} | cut -d' ' -f2- | xargs rm -f
fi

# 6. 统计
current_count=$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f | wc -l)
total_size=$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f -exec du -ch {} + | tail -1 | cut -f1)

log "INFO" "========== 数据库备份完成 =========="
log "INFO" "备份文件: $(basename "${backup_file_gz}")"
log "INFO" "原始大小: ${backup_size_mb} MB"
log "INFO" "压缩大小: ${compressed_size_mb} MB"
log "INFO" "当前备份数: ${current_count}"
log "INFO" "备份总大小: ${total_size}"

send_feishu "✅ 数据库备份成功" "
数据库: ${PG_DB}
备份时间: $(date +'%Y-%m-%d %H:%M:%S')
备份文件: $(basename "${backup_file_gz}")
原始大小: ${backup_size_mb} MB
压缩大小: ${compressed_size_mb} MB
当前备份数: ${current_count}
备份总大小: ${total_size}
" "green"

unset PGPASSWORD
log "INFO" "备份脚本执行完毕"
exit 0
