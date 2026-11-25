#!/usr/bin/env bash
# Nuotao V2.8 EXPORT — G3 Linux Runtime Verification 最终验证指令 V1.0 (Owner)
#
# 在 Owner/管理员提供的隔离 Linux 测试环境执行：
#   - 收集环境证据（OS/内核/FS/Python/pytest/getfacl/setfacl/id）
#   - 运行 tests/test_v28_export_acl_guard_linux.py 的 6 项真实 ACL 验证
#   - 收集临时目录/写入文件的 stat/getfacl 证据
#   - 输出单一证据文件（默认 /tmp/v28-g3-linux-evidence.txt）
#
# 用法：  bash scripts/verify_v28_g3_linux_runtime.sh [evidence-out-path]
# 要求：  python3 + pytest + acl(getfacl/setfacl)；第 4 项 Owner mismatch 需 root
# 红线：  只使用合成数据与临时目录；不连生产、不执行真实导出、不接收真实 Salt。

set -uo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-/tmp/v28-g3-linux-evidence.txt}"
EV_DIR="${V28_G3_EVIDENCE_DIR:-/tmp/v28-g3-evidence}"

mkdir -p "$EV_DIR"
export V28_G3_EVIDENCE_DIR="$EV_DIR"

echo "===== V28 G3 LINUX RUNTIME VERIFICATION EVIDENCE ($(date -Is)) =====" | tee "$OUT"

{
  echo "--- ENVIRONMENT ---"
  echo "hostname: $(hostname)"
  echo "date:     $(date -Is)"
  echo "uname:    $(uname -a)"
  echo "os_release: $(tr '\n' ' ' < /etc/os-release 2>/dev/null)"
  echo "fs_type(cwd): $(stat -f -c %T . 2>/dev/null || stat -f -c '%T' . 2>/dev/null)"
  echo "python3:  $(python3 --version 2>&1)"
  echo "pytest:   $(python3 -m pytest --version 2>&1 | tr '\n' ' ')"
  echo "getfacl:  $(getfacl --version 2>&1 | head -1)"
  echo "setfacl:  $(setfacl --version 2>&1 | head -1)"
  echo "id:       uid=$(id -u) $(id -un) gid=$(id -g) $(id -gn)"
  echo "euid:     $(id -u)"
  echo ""
  echo "--- RUN 6 LINUX ACL TESTS (pytest -v) ---"
  python3 -m pytest tests/test_v28_export_acl_guard_linux.py -v
  echo "pytest_exit: $?"
  echo ""
  echo "--- EVIDENCE FILES (stat/getfacl per test) ---"
  if [ -d "$EV_DIR" ]; then
    for f in "$EV_DIR"/*.txt; do
      [ -e "$f" ] || continue
      echo "### $(basename "$f") ###"
      cat "$f"
      echo ""
    done
  else
    echo "(no evidence dir)"
  fi
} 2>&1 | tee -a "$OUT"

echo ""
echo "===== DONE. Evidence saved to: $OUT =====" | tee -a "$OUT"
echo "Pytest was run above; inspect 'pytest_exit' and 6 test lines for PASS/FAIL."
