"""Show the full _fetch_1688_product return dict and _generate_listing_data keys."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SVC = "/opt/nuotao/backend/app/services/product_pipeline_service.py"

CMDS = [
    ("A. 1688 extraction + return dict (1220-1330)", r"""
sed -n '1220,1330p' %s
""" % SVC),
    ("B. _generate_listing_data full body (162-272)", r"""
sed -n '162,272p' %s
""" % SVC),
    ("C. Product model columns", r"""
sed -n '1,90p' /opt/nuotao/backend/app/models/product.py
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
        print(data.rstrip()[:7000], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:300], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
