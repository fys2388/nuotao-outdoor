#!/bin/bash
# ============================================================
# Nuotao AI OS - Backup Restore Verification
# Usage: ./verify_backup_restore.sh
# Restores the latest backup to a temp DB and verifies tables.
# ============================================================

set -euo pipefail

BACKUP_DIR="/opt/nuotao/backups"
TEST_DB="nuotao_restore_test"
ENV_FILE="/opt/nuotao/backend/.env"

# Extract DATABASE_URL from .env (do NOT source entire .env - values with spaces break bash)
if [ -f "$ENV_FILE" ]; then
    DATABASE_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
    export DATABASE_URL
fi

# Parse DATABASE_URL if available
if [ -n "${DATABASE_URL:-}" ]; then
    # Extract from postgresql+asyncpg://user:pass@host:port/dbname
    DB_USER=$(echo "$DATABASE_URL" | sed -E 's|.*://([^:]+):.*|\1|')
    DB_PASSWORD=$(echo "$DATABASE_URL" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
    DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):.*|\1|')
    DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*@[^:]+:([^/]+)/.*|\1|')
else
    DB_USER="${POSTGRES_USER:-nuotao}"
    DB_HOST="${POSTGRES_HOST:-localhost}"
    DB_PORT="${POSTGRES_PORT:-5432}"
    DB_PASSWORD="${POSTGRES_PASSWORD:-}"
fi

export PGPASSWORD="$DB_PASSWORD"

echo "=== Backup Restore Verification: $(date) ==="
echo "DB: $DB_USER@$DB_HOST:$DB_PORT"

# 1. Find latest backup
LATEST=$(ls -t "${BACKUP_DIR}"/nuotao_*.sql.gz 2>/dev/null | head -1 || true)
if [ -z "${LATEST}" ] || [ ! -f "${LATEST}" ]; then
    echo "ERROR: No backup files found in ${BACKUP_DIR}"
    exit 1
fi
echo "Latest backup: ${LATEST} ($(du -h "${LATEST}" | cut -f1))"

# 2. Clean up old test DB
sudo -u postgres dropdb --if-exists "${TEST_DB}" 2>/dev/null || true

# 3. Create test DB
sudo -u postgres createdb -O nuotao "${TEST_DB}"
echo "Created temp DB: ${TEST_DB}"

# 4. Restore (with timeout to prevent hanging)
echo "Restoring backup..."
if ! gunzip -c "${LATEST}" | timeout 120 psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${TEST_DB}" -q -o /dev/null 2>/tmp/restore_err.log; then
    echo "ERROR: Restore failed or timed out:"
    cat /tmp/restore_err.log | head -20
    sudo -u postgres dropdb --if-exists "${TEST_DB}" 2>/dev/null || true
    exit 1
fi
echo "Restore completed"

# 5. Verify key tables exist and have data
TABLES="orders settlements agent_suggestions growth_memories strategy_versions alembic_version"
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
sudo -u postgres dropdb "${TEST_DB}"
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
