"""Dump exact prod anchors needed for the round-4 patch."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
N = "/opt/nuotao/backend/app/services/newton_agent_service.py"
P = "/opt/nuotao/backend/app/services/product_pipeline_service.py"

CMDS = [
    ("A2. extract_1688_product tail (745,790)", f"sed -n '745,790p' {N}"),
    ("C2. convert return dict (1332,1380)", f"sed -n '1332,1380p' {P}"),
    ("D. _normalize_extracted_product attrs mapping (585,671)", f"sed -n '585,671p' {N}"),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=90)
        print("\n" + "=" * 74, "\n### " + label, "\n" + "=" * 74, flush=True)
        print(out.read().decode("utf-8", "replace").rstrip(), flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
