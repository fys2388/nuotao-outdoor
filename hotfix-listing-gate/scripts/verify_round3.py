"""Post-round-3 verification: code landed + modules import."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
BACKEND = "/opt/nuotao/backend"
GATE = f"{BACKEND}/app/services/listing_gate.py"
PIPELINE = f"{BACKEND}/app/services/product_pipeline_service.py"

VERIFY_PY = r'''
import app.services.listing_gate as g
import app.api.v1.endpoints.listing_publish as lp
import app.services.product_pipeline_service as pp

print("gate helpers:", all(callable(getattr(g, n)) for n in
    ["normalise_listing_images", "normalise_listing_tags",
     "parse_dimensions", "collect_attributes"]))
print("pipeline.run_v3_gate callable:", callable(pp.run_v3_gate))
print("publish budget secs:", lp._PUSH_BUDGET_SECONDS)
print("publish attempts:", lp._WC_MAX_ATTEMPTS)
P = type("P", (), {"category": None})()
print("chair ->", g.category_for_product(P, "Moon Chair: Lightweight for Camping"))
print("lantern ->", g.category_for_product(P, "LED Camping Lantern 1000lm"))
print()
print("payload single-value attributes emitted:",
      "attributes" in g.build_wc_payload(
          type("Q", (), {
              "sku": "X", "name": "Chair", "description": "d",
              "status": "draft", "meta": {}, "tags": [],
              "attributes": {"Material": ["Aluminium"]},
              "weight_kg": None, "dimensions": None, "brand": None,
          })(),
          {"regular_price": 15.8},
          {"title": "Chair", "description": "d", "short_description": "s"}))
print()
print("payload images emitted:",
      "images" in g.build_wc_payload(
          type("R", (), {
              "sku": "X", "name": "Chair", "description": "d",
              "status": "draft", "tags": [], "attributes": {},
              "weight_kg": None, "dimensions": None, "brand": None,
              "meta": {"main_images": [{"src": "https://x/1.jpg"}, "https://x/2.jpg"]},
          })(),
          {"regular_price": 15.8},
          {"title": "Chair", "description": "d", "short_description": "s"}))
'''

CMDS = [
    ("health", f"""
echo "readyz(/api/v1) : $(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8000/api/v1/readyz)"
echo "service         : $(systemctl is-active nuotao-backend)"
"""),
    ("code confirmation", f"""
echo '== helpers in deployed gate =='
grep -n 'def normalise_listing_images\|def normalise_listing_tags\|def parse_dimensions\|def collect_attributes' {GATE}
echo
echo '== limits =='
grep -n '_MAX_ATTRIBUTES\|_MAX_ATTRIBUTE_OPTIONS\|_MAX_IMAGES' {GATE} | head -5
echo
echo '== run_v3_gate patch in deployed pipeline =='
grep -n 'BUG-13\|listing_media\|flag_modified' {PIPELINE} | head -14
echo
echo '== round-2 fixes still present =='
grep -n '_PUSH_BUDGET_SECONDS' {BACKEND}/app/api/v1/endpoints/listing_publish.py | head -3
grep -n 'light(?!weight' {GATE} | head -2
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
        print(data.rstrip()[:3500], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:400], flush=True)

    sftp = ssh.open_sftp()
    with sftp.open("/tmp/verify_r3.py", "w") as fh:
        fh.write(VERIFY_PY.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(f"cd {BACKEND} && .venv/bin/python /tmp/verify_r3.py",
                                   timeout=180)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print("\n### import + payload smoke test", flush=True)
    print(data.rstrip()[:3000], flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:700], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
