#!/usr/bin/env bash
# M4.4-INC-001 / APR-INC-002: 生产迁移授权门禁负向测试（bash，无外部依赖）
# 验收场景（Owner 2026-11-18）：
#   目标 revision=0086 且批准清单有效        -> 允许
#   目标 revision=0087（未批）              -> 拒绝
#   目标 revision=0084（低于）              -> 拒绝（版本不一致）
#   批准清单不存在                           -> 拒绝
#   YAML 格式错误                           -> 拒绝
#   普通应用部署（无清单）                    -> 不执行迁移（无清单即不迁移）
set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
TMPLOG="$(mktemp)"

check() { # $1=desc $2=expected_rc
  local rc=$?
  if [ "$rc" = "$2" ]; then
    PASS=$((PASS + 1))
    echo "PASS: $1 (rc=$rc)"
  else
    FAIL=$((FAIL + 1))
    echo "FAIL: $1 (rc=$rc, want $2) :: $(head -1 "$TMPLOG")"
  fi
}

# 1. 目标=0086（批准，有效清单）-> 允许
bash "$ROOT/migration_gate.sh" 0086 >"$TMPLOG" 2>&1
check "target=0086 approved" 0

# 2. 目标=0087（未批）-> 拒绝
bash "$ROOT/migration_gate.sh" 0087 >"$TMPLOG" 2>&1
check "target=0087 unapproved" 1

# 3. 目标=0084（低于，版本不一致）-> 拒绝
bash "$ROOT/migration_gate.sh" 0084 >"$TMPLOG" 2>&1
check "target=0084 below (version mismatch)" 1

# 4. 批准清单不存在 -> 拒绝
MIGRATION_APPROVALS="/tmp/nonexistent-migration-approvals.yaml" \
  bash "$ROOT/migration_gate.sh" 0086 >"$TMPLOG" 2>&1
check "approvals file missing" 1

# 5. YAML 格式错误 -> 拒绝
printf 'approved_revision: [broken\n' > /tmp/bad_approvals.yaml
MIGRATION_APPROVALS="/tmp/bad_approvals.yaml" \
  bash "$ROOT/migration_gate.sh" 0086 >"$TMPLOG" 2>&1
check "malformed yaml" 1

# 6. approved_revision 为空 -> 拒绝
printf 'approved_revision: ""\napproved_list:\n  - "0086"\n' > /tmp/empty_approvals.yaml
MIGRATION_APPROVALS="/tmp/empty_approvals.yaml" \
  bash "$ROOT/migration_gate.sh" 0086 >"$TMPLOG" 2>&1
check "empty approved_revision" 1

# 7. 测试A（Owner APR-INC-002 补测）: 容器读取批准清单权限不足。
#    文件存在但运行用户无读取权限 -> gate 必须拒绝迁移，无默认版本、无 head 回退、
#    错误日志明确。先确认测试环境确实能触发权限拒绝（cat as nobody 失败）。
#    注意：runner 家目录通常为 700，nobody 无法进入；须把 gate+清单复制到
#    nobody 可访问的 /tmp 下，再以 nobody 运行，确保是"读清单权限不足"而非
#    "读不到脚本"。
mkdir -p /tmp/gate_perm_test
cp "$ROOT/migration_gate.sh" /tmp/gate_perm_test/gate.sh
chmod 755 /tmp/gate_perm_test/gate.sh
cp "$ROOT/migration_approvals.yaml" /tmp/gate_perm_test/migration_approvals.yaml
chmod 000 /tmp/gate_perm_test/migration_approvals.yaml
if command -v runuser >/dev/null 2>&1 && id nobody >/dev/null 2>&1; then
  if ! runuser -u nobody -- cat /tmp/gate_perm_test/migration_approvals.yaml >/dev/null 2>&1; then
    echo "confirmed: permission denied is reproducible (nobody cannot read chmod 000 file)"
    MIGRATION_APPROVALS=/tmp/gate_perm_test/migration_approvals.yaml \
      runuser -u nobody -- bash /tmp/gate_perm_test/gate.sh 0086 >"$TMPLOG" 2>&1
    check "container read approval list permission denied" 1
    if grep -q "FAIL-CLOSED" "$TMPLOG"; then
      PASS=$((PASS + 1)); echo "PASS: permission denied emits FAIL-CLOSED"
    else
      FAIL=$((FAIL + 1)); echo "FAIL: permission denied missing FAIL-CLOSED :: $(head -2 "$TMPLOG" | tr '\n' ' ')"
    fi
  else
    echo "SKIP: permission denied not reproducible (nobody can read chmod 000 file)"
  fi
else
  echo "SKIP: no runuser/nobody on this host"
fi
rm -rf /tmp/gate_perm_test

# 8. 测试B（Owner APR-INC-002 补测）: 容器恢复不自动迁移。
#    docker-restore 的容器启动命令不得包含任何迁移调用（alembic / migration_gate /
#    upgrade），批准清单存在也不得自动升级；容器启动只执行 uvicorn。
RESTORE_WF="$ROOT/../.github/workflows/docker-restore-api.yml"
if [ -f "$RESTORE_WF" ]; then
  if grep -qE 'alembic (upgrade|current)|migration_gate|upgrade head' "$RESTORE_WF"; then
    FAIL=$((FAIL + 1)); echo "FAIL: docker-restore contains migration call (must have none)"
  else
    PASS=$((PASS + 1)); echo "PASS: docker-restore container start has no migration call"
  fi
  if grep -qE 'sh -c "exec uvicorn' "$RESTORE_WF"; then
    PASS=$((PASS + 1)); echo "PASS: docker-restore starts only uvicorn (no alembic)"
  else
    FAIL=$((FAIL + 1)); echo "FAIL: docker-restore does not start uvicorn-only"
  fi
else
  echo "SKIP: docker-restore-api.yml not found"
fi

rm -f "$TMPLOG" /tmp/bad_approvals.yaml /tmp/empty_approvals.yaml

echo "=== migration_gate negative tests: pass=$PASS fail=$FAIL ==="
[ "$FAIL" = "0" ] || exit 1
