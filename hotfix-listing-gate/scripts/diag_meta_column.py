"""Check how Product.meta is mapped (MutableDict or plain JSON?)."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

CMDS = [
    ("A. Product model meta column", r"""
grep -n 'meta' /opt/nuotao/backend/app/models/product.py | head -20
echo '--- context ---'
grep -n -B3 -A3 'meta' /opt/nuotao/backend/app/models/product.py | head -40
"""),
    ("B. is MutableDict used anywhere", r"""
grep -rn 'MutableDict\|MutableList' /opt/nuotao/backend/app/models/ 2>/dev/null | head -10
echo '--- none above means plain JSON columns ---'
"""),
    ("C. how the legacy code persists meta", r"""
grep -n -A4 'product.meta = ' /opt/nuotao/backend/app/services/woocommerce_sync_service.py 2>/dev/null | head -30
"""),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=90)
        data = out.read().decode("utf-8", "replace")
        et = err.read().decode("utf-8", "replace")
        print("\n" + "=" * 78, "\n### " + label, "\n" + "=" * 78, flush=True)
        print(data.rstrip()[:3000], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:400], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
