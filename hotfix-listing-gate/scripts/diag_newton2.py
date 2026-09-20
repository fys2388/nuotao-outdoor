"""Inspect extract_1688_product: task create + poll loop, timeouts, failure mode."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
N = "/opt/nuotao/backend/app/services/newton_agent_service.py"

CMDS = [
    ("A. await_result (404-500)", r"""
sed -n '404,500p' %s
""" % N),
    ("B. extract_1688_product (671,800)", r"""
sed -n '671,800p' %s
""" % N),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=90)
        data = out.read().decode("utf-8", "replace")
        print("\n### " + label + "\n" + data.rstrip()[:3000], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
