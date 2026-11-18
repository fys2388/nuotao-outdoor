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

rm -f "$TMPLOG" /tmp/bad_approvals.yaml /tmp/empty_approvals.yaml

echo "=== migration_gate negative tests: pass=$PASS fail=$FAIL ==="
[ "$FAIL" = "0" ] || exit 1
