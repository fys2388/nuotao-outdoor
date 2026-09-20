"""Post-deploy confirmation: health, flag_modified present, service generation."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

CMDS = [
    ("health + code confirmation", r"""
echo "readyz(/api/v1) : $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/readyz)"
echo "service         : $(systemctl is-active nuotao-backend)"
echo "workers         : $(systemctl show nuotao-backend -p ExecMainPID --value)"
echo
echo '== flag_modified wired in deployed endpoint =='
grep -n 'flag_modified' /opt/nuotao/backend/app/api/v1/endpoints/listing_publish.py
echo
echo '== category regex deployed =='
grep -n 'light(?!weight' /opt/nuotao/backend/app/services/listing_gate.py
echo
echo '== frontend timeout deployed in source =='
grep -n 'timeoutMs: 120000' /opt/nuotao/frontend/src/pages/ProductPublish.tsx
echo
echo '== import smoke of both modules =='
cd /opt/nuotao/backend && .venv/bin/python -c "
import app.api.v1.endpoints.listing_publish as lp
import app.services.listing_gate as g
print('  ok:', lp._PUSH_BUDGET_SECONDS, lp._WC_MAX_ATTEMPTS, lp._REQUEST_TIMEOUT)
print('  chair ->', g.category_for_product(type('P',(),{'category':None})(), 'Moon Chair: Lightweight Foldable for Camping'))
"
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
        print("\n### " + label, flush=True)
        print(data.rstrip()[:3000], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:400], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
