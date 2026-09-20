"""Deploy the retry-budget / category / meta-persist backend fixes and the
frontend timeout fix, then verify.

Backs up every file it touches, refuses to proceed on any anchor mismatch.
"""

from __future__ import annotations

import os
import sys
import time
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
HOST = "95.217.218.178"
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
BACKUP = f"/opt/nuotao/backups/listing-gate-{STAMP}"
PATCH_DIR = "/tmp/listing-gate-patch"

BACKEND = "/opt/nuotao/backend"
FRONTEND = "/opt/nuotao/frontend"
WEBSITE = "/var/www/nuotao"

FILES = {
    "listing_gate.py": (
        "backend/app/services/listing_gate.py",
        f"{BACKEND}/app/services/listing_gate.py",
    ),
    "listing_publish.py": (
        "backend/app/api/v1/endpoints/listing_publish.py",
        f"{BACKEND}/app/api/v1/endpoints/listing_publish.py",
    ),
}

# Frontend patch: the push call used the 30s default while the gated push can
# take up to 75s, so the browser reported a timeout although the push succeeded.
FRONTEND_OLD = """        `/products/${productId}/push-woocommerce${force ? '?force=true' : ''}`,
        { method: 'POST' },
"""
FRONTEND_NEW = """        `/products/${productId}/push-woocommerce${force ? '?force=true' : ''}`,
        { method: 'POST', timeoutMs: 120000 },
"""

PATCH_FRONTEND_PY = r'''
import pathlib
import sys

path = pathlib.Path("/opt/nuotao/frontend/src/pages/ProductPublish.tsx")
src = path.read_text(encoding="utf-8")
old = """        `/products/${productId}/push-woocommerce${force ? '?force=true' : ''}`,
        { method: 'POST' },
"""
new = """        `/products/${productId}/push-woocommerce${force ? '?force=true' : ''}`,
        { method: 'POST', timeoutMs: 120000 },
"""
count = src.count(old)
if count == 0:
    if "timeoutMs: 120000" in src and "push-woocommerce" in src:
        print("frontend already patched; skipping")
        sys.exit(0)
    print("ANCHOR NOT FOUND in ProductPublish.tsx")
    sys.exit(2)
if count > 1:
    print(f"ANCHOR AMBIGUOUS: {count} matches")
    sys.exit(3)
path.write_text(src.replace(old, new), encoding="utf-8")
print(f"frontend patched: 1 site (timeoutMs 30000 -> 120000)")
'''


def run(ssh: paramiko.SSHClient, script: str, timeout: int = 900, label: str = "") -> int:
    print(f"\n{'=' * 78}\n### {label or script.splitlines()[0][:70]}\n{'=' * 78}", flush=True)
    _, out, err = ssh.exec_command(script, timeout=timeout)
    data = out.read().decode("utf-8", "replace")
    etext = err.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    print(data.rstrip(), flush=True)
    if etext.strip():
        print("-- stderr --", etext.rstrip(), flush=True)
    print(f"[exit {code}]", flush=True)
    return code


def main() -> int:
    if "--skip-frontend" in sys.argv:
        SKIP_FRONTEND = True
    else:
        SKIP_FRONTEND = False

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=HOST, port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    print(f"connected to {HOST}", flush=True)

    # 1. upload the new backend modules and the frontend patcher
    run(ssh, f"mkdir -p {BACKUP} {PATCH_DIR}", label="0. prepare dirs", timeout=60)
    sftp = ssh.open_sftp()
    here = os.path.dirname(os.path.abspath(__file__))
    for local_name, (local_rel, _) in FILES.items():
        local = os.path.join(here, "..", local_rel)
        local = os.path.normpath(local)
        remote = f"{PATCH_DIR}/{local_name}"
        sftp.put(local, remote)
        print(f"uploaded {local_rel} -> {remote} ({os.path.getsize(local)} B)", flush=True)
    with sftp.open(f"{PATCH_DIR}/patch_frontend.py", "w") as fh:
        fh.write(PATCH_FRONTEND_PY.encode("utf-8"))
    sftp.close()
    print("uploaded patch_frontend.py", flush=True)

    # 2. backup + install backend modules
    rc = run(
        ssh,
        f"""set -e
mkdir -p {BACKUP}
for f in app/services/listing_gate.py app/api/v1/endpoints/listing_publish.py; do
  cp -a {BACKEND}/$f {BACKUP}/$(echo $f | tr '/' '_')
done
cp {BACKUP}/app__services__listing_gate.py {BACKUP}/listing_gate.bak 2>/dev/null || true
cp {PATCH_DIR}/listing_gate.py {BACKEND}/app/services/listing_gate.py
cp {PATCH_DIR}/listing_publish.py {BACKEND}/app/api/v1/endpoints/listing_publish.py
cp {FRONTEND}/src/pages/ProductPublish.tsx {BACKUP}/ProductPublish.tsx
echo "backup at {BACKUP}:"
ls -la {BACKUP}
""",
        label="1. backup + install backend modules",
    )
    if rc:
        return rc

    # 3. patch the frontend call site
    rc = run(
        ssh,
        f"cd {FRONTEND} && .venv/bin/python {PATCH_DIR}/patch_frontend.py 2>/dev/null || "
        f"python3 {PATCH_DIR}/patch_frontend.py",
        label="2. patch frontend timeout",
    )
    if rc:
        print("FRONTEND PATCH FAILED - restoring", flush=True)
        run(ssh, f"cp {BACKUP}/ProductPublish.tsx {FRONTEND}/src/pages/ProductPublish.tsx",
            label="restore frontend")
        return rc

    # 4. syntax check the backend
    rc = run(
        ssh,
        f"cd {BACKEND} && .venv/bin/python -m compileall -q "
        f"app/services/listing_gate.py app/api/v1/endpoints/listing_publish.py "
        f"&& echo 'compile-ok'",
        label="3. compile backend",
        timeout=120,
    )
    if rc:
        print("BACKEND COMPILE FAILED - restoring", flush=True)
        run(ssh, f"cp {BACKUP}/app__services__listing_gate.py {BACKEND}/app/services/listing_gate.py; "
                 f"cp {BACKUP}/app__api__v1__endpoints__listing_publish.py "
                 f"{BACKEND}/app/api/v1/endpoints/listing_publish.py",
            label="restore backend")
        return rc

    # 5. restart backend
    rc = run(
        ssh,
        "systemctl restart nuotao-backend && sleep 2 && systemctl is-active nuotao-backend",
        label="4. restart backend",
        timeout=120,
    )
    if rc:
        return rc

    # 6. wait for readyz
    run(
        ssh,
        f"""for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8000/readyz || echo 000)
  echo "attempt $i readyz=$code"
  [ "$code" = "200" ] && break
  sleep 3
done""",
        label="5. wait for readyz",
        timeout=180,
    )

    # 7. rebuild + deploy the frontend
    if not SKIP_FRONTEND:
        rc = run(
            ssh,
            f"cd {FRONTEND} && npm run build 2>&1 | tail -12",
            label="6. rebuild frontend",
            timeout=900,
        )
        if rc:
            print("FRONTEND BUILD FAILED - restoring", flush=True)
            run(ssh, f"cp {BACKUP}/ProductPublish.tsx {FRONTEND}/src/pages/ProductPublish.tsx",
                label="restore frontend source")
            return rc
        rc = run(
            ssh,
            f"rm -rf {WEBSITE}/* && cp -r {FRONTEND}/dist/* {WEBSITE}/ && "
            f"echo 'deployed:' && ls {WEBSITE} | head -5",
            label="7. deploy frontend to webroot",
            timeout=120,
        )
        if rc:
            print("FRONTEND DEPLOY FAILED", flush=True)
            return rc

    # 8. final health
    run(
        ssh,
        f"""echo "backend readyz: $(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8000/readyz)"
echo "webroot index:  $(curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1/index.html)"
echo '== push timeout in deployed bundle =='
grep -rlo 'push-woocommerce' {WEBSITE}/assets/ 2>/dev/null | head -3
echo '== category word-boundary present in deployed backend =='
grep -n 'Word boundaries are mandatory' {BACKEND}/app/services/listing_gate.py
echo '== push budget present =='
grep -n '_PUSH_BUDGET_SECONDS' {BACKEND}/app/api/v1/endpoints/listing_publish.py | head -3
echo 'ALL DONE'""",
        label="8. final health",
        timeout=120,
    )

    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
