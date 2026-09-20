"""Is listing_data (with images/attributes) persisted anywhere, or discarded?"""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SVC = "/opt/nuotao/backend/app/services/product_pipeline_service.py"

CMDS = [
    ("A. run_pipeline: what happens to listing_data", r"""
sed -n '638,800p' %s
""" % SVC),
    ("B. the other Product creation with base_meta (around 1060-1140)", r"""
sed -n '1055,1145p' %s
""" % SVC),
    ("C. import_and_analyze_from_1688 entry", r"""
sed -n '1508,1600p' %s
""" % SVC),
    ("D. where product_info comes from (source_url/imageUrl population)", r"""
grep -n -B4 -A12 'imageUrls\|"images"' %s | head -70
""" % SVC),
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
