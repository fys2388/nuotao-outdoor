"""Dump the exact prod weight-extraction block (file is black-formatted)."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
P = "/opt/nuotao/backend/app/services/product_pipeline_service.py"

CMDS = [
    ("A. exact region 1265,1315", f"sed -n '1265,1315p' {P}"),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=90)
        print("\n### " + label + "\n" + out.read().decode("utf-8", "replace").rstrip(), flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
