"""Find WC store measurement unit settings (read-only)."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import json, time, requests

def p(*a):
    print(*a, flush=True)

from app.services.woocommerce_sync_service import _get_wc_auth, _get_wc_headers, WC_URL
base = str(WC_URL).rstrip("/")
h, a = _get_wc_headers(), _get_wc_auth()

p("=== 1. GET /wc/v3/settings (all) ===")
for i in range(5):
    try:
        r = requests.get(base + "/wp-json/wc/v3/settings", headers=h, auth=a, timeout=30)
        break
    except Exception as exc:
        p("  retry", i, repr(exc)[:120]); time.sleep(1.5)
p("  HTTP", r.status_code)
if r.status_code == 200:
    try:
        body = r.json()
    except Exception:
        body = []
    p("  type:", type(body).__name__, "len:", len(body) if hasattr(body, "__len__") else "?")
    if isinstance(body, list):
        hits = [s for s in body if any(k in str(s.get("id", "")).lower()
                for k in ("weight", "dimension", "unit", "measure"))]
        p("  unit-related settings:", len(hits))
        for s in hits:
            p(f"    id={s.get('id')!r:34} label={str(s.get('label'))[:32]:34} "
              f"value={s.get('value')!r}")
        if not hits:
            p("  (no unit settings in wc/v3/settings)")
    else:
        s = json.dumps(body, ensure_ascii=False, default=str)
        for needle in ("weight", "dimension"):
            idx = s.lower().find(needle)
            if idx != -1:
                p("   ...", s[max(0, idx-60):idx+100])

p()
p("=== 2. shipping class / zone units ===")
for path in ("/wp-json/wc/v3/shipping/classes", "/wp-json/wc/v3/shipping/zones"):
    try:
        rr = requests.get(base + path, headers=h, auth=a, timeout=25)
        p(f"  {path}: HTTP {rr.status_code}")
        if rr.status_code == 200:
            body = rr.json()
            s = json.dumps(body, ensure_ascii=False, default=str)
            p("   ", s[:400])
    except Exception as exc:
        p("  ", path, "ERR", repr(exc)[:120])

p()
p("DONE")
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/wc_units.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/wc_units.py", timeout=400)
    print(out.read().decode("utf-8", "replace").rstrip(), flush=True)
    et = err.read().decode("utf-8", "replace")
    if et.strip():
        print("-- stderr --", et.rstrip()[:500], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
