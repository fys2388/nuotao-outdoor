"""Snapshot the LIVE selection -> listing -> WC-sync flow for an accurate answer."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
B = "/opt/nuotao/backend"

CMDS = [
    ("1. pipeline stage declarations (选品)", r"""
grep -n -A3 'STAGES\|{"id": "main_image"\|"id": "listing_data"\|"id": "v3_gate"\|"id": "input"' %s/app/services/product_pipeline_service.py | head -40
""" % B),
    ("2. run_pipeline step sequence", r"""
grep -n 'Step [0-9]' %s/app/services/product_pipeline_service.py | head -20
""" % B),
    ("3. V3.0 veto dimensions", r"""
grep -n 'V[0-9][0-9]\|def evaluate_v3_gate\|VETO' %s/app/services/nuotao_selection_service.py 2>/dev/null | head -25
"""),
    ("4. gate reasons in listing_gate (上架闸门)", r"""
grep -n 'HARD_BLOCK\|REVIEW_REQUIRED\|"code": "' %s/app/services/listing_gate.py | head -25
""" % B),
    ("5. WC push endpoint contract", r"""
grep -n 'def push_woocommerce\|@router.post\|force\|_PUSH_BUDGET_SECONDS\|_WC_MAX_ATTEMPTS' %s/app/api/v1/endpoints/listing_publish.py | head -20
""" % B),
    ("6. deployed versions", r"""
cd %s && echo "-- pipeline BUG-13:" && grep -c 'BUG-13' app/services/product_pipeline_service.py \
 && echo "-- gate helpers:" && grep -c 'def normalise_listing_images' app/services/listing_gate.py \
 && echo "-- publish budget:" && grep '^\_PUSH_BUDGET_SECONDS' app/api/v1/endpoints/listing_publish.py
""" % B),
    ("7. frontend menu / listing page route", r"""
grep -rn '渠道与上架\|ProductPublish' /opt/nuotao/frontend/src/pages/ProductPublish.tsx 2>/dev/null | head -5
"""),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=90)
        data = out.read().decode("utf-8", "replace")
        print("\n" + "=" * 74, "\n### " + label, "\n" + "=" * 74, flush=True)
        print(data.rstrip()[:2500], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
