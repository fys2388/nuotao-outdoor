"""Dump the pipeline sections that decide what lands in product.meta."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SVC = "/opt/nuotao/backend/app/services/product_pipeline_service.py"

CMDS = [
    ("A. meta assembly (around :591)", r"""
sed -n '555,640p' %s
""" % SVC),
    ("B. function entry points / 1688 url handling", r"""
grep -n 'def \|url_or_id\|offer_id\|1688\|1688\.com\|source_url\|source_id\|image' %s | head -50
""" % SVC),
    ("C. how Product rows are constructed", r"""
grep -n -A30 'Product(' %s | head -80
""" % SVC),
    ("D. what the 1688 scraper/analysis returns", r"""
grep -rn 'def import_and_analyze_from_1688' /opt/nuotao/backend/app/ 2>/dev/null | grep -v __pycache__
echo '---'
grep -n 'images\|gallery\|mainPic\|offerDetail\|attributes\|specs' %s | head -30
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
        print(data.rstrip()[:6000], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:300], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
