"""Find where products are created from the 1688/product_pipeline path and why
source_id / source_url are never populated."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

CMDS = [
    ("A. who writes meta.source = product_pipeline", r"""
grep -rn 'product_pipeline' /opt/nuotao/backend/app/ 2>/dev/null | grep -v __pycache__ | head -20
"""),
    ("B. who sets source_id / source_url", r"""
grep -rn 'source_id\|source_url' /opt/nuotao/backend/app/ 2>/dev/null | grep -v __pycache__ | grep -vE '\.pyc' | head -40
"""),
    ("C. the 1688 integration files", r"""
ls -la /opt/nuotao/backend/app/integrations/ 2>/dev/null
echo '--- product pipeline endpoint files ---'
ls -la /opt/nuotao/backend/app/api/v1/endpoints/ 2>/dev/null | grep -iE 'pipeline|product|import' 
"""),
    ("D. how meta is assembled on create", r"""
grep -rn -B5 -A20 'source_id' /opt/nuotao/backend/app/services/*.py 2>/dev/null | grep -v __pycache__ | head -60
"""),
    ("E. any image capture from 1688 already present", r"""
grep -rn 'image' /opt/nuotao/backend/app/integrations/ 2>/dev/null | grep -v __pycache__ | grep -iE '1688|ali|src|url' | head -25
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
        print(data.rstrip()[:4000], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:300], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
