"""Find and test the Newton (牛顿) 1688 path - the 1688 open API was ACL-declined."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

CMDS = [
    ("A. Newton references in backend", r"""
grep -rniE 'newton|牛顿' /opt/nuotao/backend/app/ 2>/dev/null | grep -v __pycache__ | grep -v '\.bak' | head -30
"""),
    ("B. files naming newton", r"""
find /opt/nuotao/backend/app -iname '*newton*' -o -iname '*1688*' 2>/dev/null | grep -v __pycache__ | grep -v '\.bak'
"""),
    ("C. how _fetch_1688_product chooses its backend", r"""
grep -n -B4 -A18 'def _fetch_1688_product\|1688_open_api\|data_source' /opt/nuotao/backend/app/services/product_pipeline_service.py | head -80
"""),
    ("D. Newton credentials in .env", r"""
grep -niE 'newton|1688|alibaba|ALI_' /opt/nuotao/backend/.env 2>/dev/null | sed -E 's/(=.{0,8}).*/\1.../' | head -20
"""),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=120)
        data = out.read().decode("utf-8", "replace")
        et = err.read().decode("utf-8", "replace")
        print("\n" + "=" * 78, "\n### " + label, "\n" + "=" * 78, flush=True)
        print(data.rstrip()[:5000], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:400], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
