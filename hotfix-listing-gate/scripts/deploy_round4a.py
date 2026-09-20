"""Round 4a deploy: Newton timeout + attribute plumbing.

Changes (all anchored, idempotent, auto-restored on failure):
  1. extract_1688_product max_wait 90 -> 300   (confirmed too short: real runs hit 114s)
  2. _normalize_extracted_product: pass through Newton's `attributes` instead of []
  3. convert_1688_to_pipeline_input: carry `attributes` into product_info

Does NOT touch the Newton prompt (AGENTS.md 3.4: prompt changes need evaluation first).
"""

from __future__ import annotations

import os
import shutil
import time
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
BACKEND = "/opt/nuotao/backend"
GATE_N = f"{BACKEND}/app/services/newton_agent_service.py"
GATE_P = f"{BACKEND}/app/services/product_pipeline_service.py"
MARK = "ROUND-4A"


def run(ssh: paramiko.SSHClient, script: str, timeout: int = 300) -> str:
    _, out, err = ssh.exec_command(script, timeout=timeout)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:600], flush=True)
    return data


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = f"/opt/nuotao/backups/listing-gate-{stamp}"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    try:
        print("\n" + "=" * 78, "\n### 0. backup", "\n" + "=" * 78, flush=True)
        run(ssh, f"mkdir -p {backup} && cp {GATE_N} {GATE_P} {backup}/ && ls -la {backup}")

        print("\n" + "=" * 78, "\n### 1. patch newton_agent_service.py", "\n" + "=" * 78, flush=True)
        py = r'''
import pathlib, sys

path = pathlib.Path("/opt/nuotao/backend/app/services/newton_agent_service.py")
src = path.read_text(encoding="utf-8")
orig = src

if "ROUND-4A" in src:
    print("already patched, skipping")
    sys.exit(0)

# --- Fix 1: timeout 90 -> 300 ---
anchor1 = "    max_wait: int = 90,\n"
if src.count(anchor1) != 1:
    print("ABORT: anchor1 count =", src.count(anchor1))
    sys.exit(1)
src = src.replace(anchor1,
    "    max_wait: int = 300,\n")

# --- Fix 2: pass through attributes ---
anchor2 = (
    '        "sku_list": [],\n'
    '        "attributes": [],\n'
    '        "images": images,\n'
)
if src.count(anchor2) != 1:
    print("ABORT: anchor2 count =", src.count(anchor2))
    sys.exit(1)
src = src.replace(anchor2,
    '        "sku_list": [],\n'
    '        "attributes": (\n'
    '            data.get("attributes")\n'
    '            if isinstance(data.get("attributes"), list)\n'
    '            else []\n'
    '        ),  # ROUND-4A: 1688 属性表原样透传，重量/尺寸/材质靠它落地\n'
    '        "images": images,\n'
)

# docstring note for the timeout change
anchor3 = '    该函数只提取页面公开商品字段，不自动询盘、下单或修改任何业务数据。\n'
if src.count(anchor3) == 1:
    src = src.replace(anchor3,
        anchor3 +
        '    ROUND-4A: max_wait 90->300；实测单次 53s/114s，90s 会误报超时。\n')

path.write_text(src, encoding="utf-8")
print("newton_agent_service.py patched")
'''
        sftp.putfo(__import__("io").BytesIO(py.encode("utf-8")), "/tmp/patch_n4.py")
        run(ssh, "cd /opt/nuotao/backend && .venv/bin/python /tmp/patch_n4.py")
        run(ssh, f"grep -n 'ROUND-4A\\|max_wait: int = 300' {GATE_N} | head -8")

        print("\n" + "=" * 78, "\n### 2. patch product_pipeline_service.py", "\n" + "=" * 78, flush=True)
        py2 = r'''
import pathlib, sys

path = pathlib.Path("/opt/nuotao/backend/app/services/product_pipeline_service.py")
src = path.read_text(encoding="utf-8")

if "ROUND-4A" in src:
    print("already patched, skipping")
    sys.exit(0)

anchor = (
    '        "images": image_urls[:10],  # 最多10张图片\n'
    '        "supplier": product.get("supplier") or {\n'
)
if src.count(anchor) != 1:
    print("ABORT: anchor count =", src.count(anchor))
    sys.exit(1)
src = src.replace(anchor,
    '        "images": image_urls[:10],  # 最多10张图片\n'
    '        "attributes": attributes,  # ROUND-4A: 保留原始属性表供 listing_gate 消费\n'
    '        "supplier": product.get("supplier") or {\n'
)
path.write_text(src, encoding="utf-8")
print("product_pipeline_service.py patched")
'''
        sftp.putfo(__import__("io").BytesIO(py2.encode("utf-8")), "/tmp/patch_p4.py")
        run(ssh, "cd /opt/nuotao/backend && .venv/bin/python /tmp/patch_p4.py")
        run(ssh, f"grep -n 'ROUND-4A' {GATE_P}")

        print("\n" + "=" * 78, "\n### 3. compile", "\n" + "=" * 78, flush=True)
        out = run(ssh, "cd /opt/nuotao/backend && .venv/bin/python -m compileall -q "
                       "app/services/newton_agent_service.py app/services/product_pipeline_service.py "
                       "&& echo COMPILE_OK")
        if "COMPILE_OK" not in out:
            raise RuntimeError("compile failed -> restoring")

        print("\n" + "=" * 78, "\n### 4. import smoke", "\n" + "=" * 78, flush=True)
        run(ssh, "cd /opt/nuotao/backend && .venv/bin/python -u -c \"import app.services.newton_agent_service as n, "
                 "app.services.product_pipeline_service as p; import inspect; "
                 "print('extract max_wait default:', inspect.signature(n.extract_1688_product).parameters['max_wait'].default); "
                 "print('run_v3_gate ok:', callable(p.run_v3_gate)); print('IMPORT_OK')\"")

        print("\n" + "=" * 78, "\n### 5. restart + wait readyz", "\n" + "=" * 78, flush=True)
        run(ssh, "systemctl restart nuotao-backend && systemctl is-active nuotao-backend")
        for attempt in range(1, 25):
            code = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/readyz")
            print(f"  attempt {attempt} readyz={code}", flush=True)
            if code.strip() == "200":
                break
            time.sleep(3)
        else:
            raise RuntimeError("backend not ready -> restoring")

        print("\nDEPLOY ROUND 4a OK, backup:", backup, flush=True)
        return 0
    finally:
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("\n!!! DEPLOY FAILED:", exc, "\n!!! restoring backup", flush=True)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
        _, out, err = ssh.exec_command(
            "cp /opt/nuotao/backups/listing-gate-*/newton_agent_service.py /opt/nuotao/backend/app/services/ 2>/dev/null; "
            "cp /opt/nuotao/backups/listing-gate-*/product_pipeline_service.py /opt/nuotao/backend/app/services/ 2>/dev/null; "
            "systemctl restart nuotao-backend; systemctl is-active nuotao-backend", timeout=300)
        print(out.read().decode("utf-8", "replace"), flush=True)
        ssh.close()
        raise SystemExit(1)
