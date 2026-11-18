#!/usr/bin/env bash
# 生产迁移授权门禁（M4.4-INC-001 整改，M440-15）
#
# 硬性原则：
#   - 生产迁移目标 revision 必须出现在 infra/migration_approvals.yaml 的
#     approved_list；否则 fail-closed（退出非 0，不执行任何迁移）。
#   - 未批准 revision（如 PII 0087）一律拒绝。
#   - 普通应用部署不自动迁移数据库；迁移只能由显式批准的目标执行。
#
# 用法（各生产迁移入口统一调用）：
#   infra/migration_gate.sh <target_revision>
#   # 成功 -> 打印 OK；失败 -> 打印 FAIL-CLOSED 并 exit 1（调用方必须中止）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPROVALS="${MIGRATION_APPROVALS:-$SCRIPT_DIR/migration_approvals.yaml}"
TARGET="${1:?usage: migration_gate.sh <target_revision>}"

if [ ! -f "$APPROVALS" ]; then
  echo "[migration-gate] FAIL-CLOSED: approval file missing: $APPROVALS"
  exit 1
fi

APPROVED_REV=$(grep -E '^approved_revision:' "$APPROVALS" | awk '{print $2}' | tr -d '"' || true)
APPROVED_LIST=$(grep -E '^\s+-\s+"[0-9]+"' "$APPROVALS" | grep -oE '[0-9]+' || true)

if [ -z "$APPROVED_REV" ]; then
  echo "[migration-gate] FAIL-CLOSED: approved_revision missing in $APPROVALS"
  exit 1
fi

if ! echo "$APPROVED_LIST" | grep -qx "$TARGET"; then
  echo "[migration-gate] FAIL-CLOSED: revision '$TARGET' is NOT in approved_list"
  echo "[migration-gate]   allowed=$(echo "$APPROVED_LIST" | tr '\n' ' ')"
  echo "[migration-gate]   approved_revision=$APPROVED_REV"
  echo "[migration-gate] 未批准迁移禁止执行；先获 Owner 授权并更新 migration_approvals.yaml"
  exit 1
fi

echo "[migration-gate] OK: revision '$TARGET' approved (approved_revision=$APPROVED_REV)"
