#!/bin/bash
# ============================================================
# Nuotao AI OS - Backup Restore Verification
# Usage: ./verify_backup_restore.sh
# Restores the latest backup to a temp DB and verifies tables.
# ============================================================

set -euo pipefail

BACKUP_DIR="/opt/nuotao/backups"
TEST_DB="nuotao_restore_test"

if [ -f /opt/nuotao/.env ]; then
    set -a
    source /opt/nuotao/.env
    set +a
fi

DB_USER="${POSTGRES_USER:-nuotao}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"

echo "=== Backup Restore Verification: $(date) ==="

# 1. Find latest backup
LATEST=$(ls -t "${BACKUP_DIR}"/nuotao_*.sql.gz 2>/dev/null | head -1 || true)
if [ -z "${LATEST}" ] || [ ! -f "${LATEST}" ]; then
    echo "ERROR: No backup files found in ${BACKUP_DIR}"
    exit 1
fi
echo "Latest backup: ${LATEST} ($(du -h "${LATEST}" | cut -f1))"

# 2. Clean up old test DB
dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" --if-exists "${TEST_DB}" 2>/dev/null || true

# 3. Create test DB
createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${TEST_DB}"
echo "Created temp DB: ${TEST_DB}"

# 4. Restore
echo "Restoring backup..."
gunzip -c "${LATEST}" | psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${TEST_DB}" -q -o /dev/null 2>/tmp/restore_err.log || {
    echo "ERROR: Restore failed:"
    cat /tmp/restore_err.log | head -20
    dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" --if-exists "${TEST_DB}" 2>/dev/null || true
    exit 1
}
echo "Restore completed"

# 5. Verify key tables exist and have data
TABLES="orders settlements agent_suggestions growth_memories strategy_versions weekly_reports"
ALL_OK=1
MISSING=0
for tbl in ${TABLES}; do
    COUNT=$(psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${TEST_DB}" -t -c "SELECT COUNT(*) FROM ${tbl};" 2>/dev/null | tr -d ' ' || true)
    if [ -z "${COUNT}" ]; then
        echo "  [MISSING] ${tbl}: table not found in backup"
        MISSING=$((MISSING+1))
        ALL_OK=0
    else
        echo "  [OK] ${tbl}: ${COUNT} rows"
    fi
done

# 6. Clean up
dropdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${TEST_DB}"
echo "Cleaned up temp DB"

# 7. Result
echo ""
if [ "${ALL_OK}" -eq 1 ]; then
    echo "=== SUCCESS: Backup restore verification passed ==="
    exit 0
else
    echo "=== FAILURE: ${MISSING} table(s) missing from backup — backup may be corrupted ==="
    exit 1
fi
