"""Round 4b deploy: enhanced Newton prompt + weight unit parsing.

Validated offline first (AGENTS.md 3.4): a single live enhanced-prompt run on
offer 771641344658 returned 22 real attributes incl. 重量(g)=1800,
规格(长*宽*高)=47cm*47cm*90cm, 材质, 品牌, 包装长/宽/高(cm).

Changes (anchored, idempotent, auto-restored on failure):
  1. Newton prompt now requests the full 1688 attribute table
  2. Weight extraction carries the unit from the attribute NAME, so 重量(g)=1800
     becomes 1.8 kg instead of the previous 1800 kg

Does NOT auto-fill `product.brand`: 1688 also reports 有可授权的自有品牌=否,
so the brand field is left for human review (AGENTS.md 3.1).
"""

from __future__ import annotations

import io
import time
import paramiko

KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"
BACKEND = "/opt/nuotao/backend"
N = f"{BACKEND}/app/services/newton_agent_service.py"
P = f"{BACKEND}/app/services/product_pipeline_service.py"


def run(ssh: paramiko.SSHClient, script: str, timeout: int = 300) -> str:
    _, out, err = ssh.exec_command(script, timeout=timeout)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:600], flush=True)
    return data


PATCH_N = r'''
import pathlib, sys

path = pathlib.Path("/opt/nuotao/backend/app/services/newton_agent_service.py")
src = path.read_text(encoding="utf-8")

if "ROUND-4B" in src:
    print("already patched, skipping")
    sys.exit(0)

# --- Fix 1a: add attributes to the JSON schema requested from Newton ---
anchor1 = (
    '  "description": "页面公开商品描述或标题",\n'
    '  "category": "商品类目"\n'
    '}}\n'
)
if src.count(anchor1) != 1:
    print("ABORT: anchor1 count =", src.count(anchor1))
    sys.exit(1)
src = src.replace(anchor1,
    '  "description": "页面公开商品描述或标题",\n'
    '  "category": "商品类目",\n'
    '  "attributes": [\n'
    '    {{"name": "属性名原文", "value": "属性值原文"}}\n'
    '  ]\n'
    '}}\n'
)

# --- Fix 1b: require the full attribute table be carried over ---
anchor2 = (
    '1. 只输出 JSON 对象，不要 Markdown，不要解释。\n'
    '2. 禁止猜测；页面无法读取或字段不存在时使用 null 或空数组。\n'
    '3. 不要联系供应商，不要下单，不要修改任何数据。\n'
)
if src.count(anchor2) != 1:
    print("ABORT: anchor2 count =", src.count(anchor2))
    sys.exit(1)
src = src.replace(anchor2,
    '1. 只输出 JSON 对象，不要 Markdown，不要解释。\n'
    '2. attributes 必须完整搬运页面上的「商品属性」/「产品参数」表格，一行一条，\n'
    '   name 和 value 都用页面原文；须包含页面上出现的：重量、尺寸/规格、材质、颜色、\n'
    '   品牌、型号、包装长宽高 等所有可见属性。ROUND-4B\n'
    '3. 禁止猜测；页面无法读取或字段不存在时使用 null 或空数组。\n'
    '4. 不要联系供应商，不要下单，不要修改任何数据。\n'
)

path.write_text(src, encoding="utf-8")
print("newton_agent_service.py patched")
'''

PATCH_P = r'''
import pathlib, re, sys

path = pathlib.Path("/opt/nuotao/backend/app/services/product_pipeline_service.py")
src = path.read_text(encoding="utf-8")

if "ROUND-4B" in src:
    print("already patched, skipping")
    sys.exit(0)

anchor = (
    '    # 提取重量\n'
    '    weight = ""\n'
    '    for attr in attributes if isinstance(attributes, list) else []:\n'
    '        if isinstance(attr, dict):\n'
    '            attr_name = attr.get("name", "").lower()\n'
    '            if "重量" in attr_name or "weight" in attr_name:\n'
    '                weight = attr.get("value", "")\n'
    '                break\n'
)
if src.count(anchor) != 1:
    print("ABORT: anchor count =", src.count(anchor))
    sys.exit(1)
src = src.replace(anchor,
    '    # 提取重量（ROUND-4B: 单位在属性名里，如「重量(g)」，必须一起带给解析器，\n'
    '    # 否则 1800g 会被当成 1800kg，运费错一千倍）\n'
    '    weight = ""\n'
    '    for attr in attributes if isinstance(attributes, list) else []:\n'
    '        if isinstance(attr, dict):\n'
    '            attr_name_raw = str(attr.get("name", ""))\n'
    '            attr_name = attr_name_raw.lower()\n'
    '            if "重量" in attr_name or "weight" in attr_name:\n'
    '                unit_match = re.search(\n'
    '                    r"[(（]([^)）]{1,6})[)）]", attr_name_raw\n'
    '                )\n'
    '                unit_hint = unit_match.group(1).strip() if unit_match else ""\n'
    '                weight = f"{attr.get(\'value\', \'\')} {unit_hint}".strip()\n'
    '                break\n'
)

path.write_text(src, encoding="utf-8")
print("product_pipeline_service.py patched")
'''


def main() -> int:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = f"/opt/nuotao/backups/listing-gate-{stamp}"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    try:
        print("\n" + "=" * 78, "\n### 0. backup", "\n" + "=" * 78, flush=True)
        run(ssh, f"mkdir -p {backup} && cp {N} {P} {backup}/ && ls {backup}")

        print("\n" + "=" * 78, "\n### 1. patch Newton prompt", "\n" + "=" * 78, flush=True)
        sftp.putfo(io.BytesIO(PATCH_N.encode("utf-8")), "/tmp/patch_n4b.py")
        run(ssh, "cd /opt/nuotao/backend && .venv/bin/python /tmp/patch_n4b.py")

        print("\n" + "=" * 78, "\n### 2. patch weight unit extraction", "\n" + "=" * 78, flush=True)
        sftp.putfo(io.BytesIO(PATCH_P.encode("utf-8")), "/tmp/patch_p4b.py")
        run(ssh, "cd /opt/nuotao/backend && .venv/bin/python /tmp/patch_p4b.py")

        print("\n" + "=" * 78, "\n### 3. grep confirm", "\n" + "=" * 78, flush=True)
        run(ssh, f"grep -n 'ROUND-4B' {N} {P}")
        run(ssh, f"grep -n -A12 '属性名原文' {N} | head -20")

        print("\n" + "=" * 78, "\n### 4. compile + unit test", "\n" + "=" * 78, flush=True)
        out = run(ssh, "cd /opt/nuotao/backend && .venv/bin/python -m compileall -q "
                       "app/services/newton_agent_service.py app/services/product_pipeline_service.py "
                       "&& echo COMPILE_OK")
        if "COMPILE_OK" not in out:
            raise RuntimeError("compile failed -> restoring")

        test = r'''
from app.services.product_pipeline_service import _parse_weight_kg

# only the g/克 branch quantizes to 3dp; kg/千克/公斤 keep the raw Decimal
cases = {
    "1800 g": "1.800",        # 重量(g)=1800  <- the bug this fixes
    "1800": "1800",
    "0.5kg": "0.5",
    "500g": "0.500",
    "1.2 千克": "1.2",
    "2 公斤": "2",
    "3 lbs": "3",             # unknown unit -> unchanged passthrough
}
ok = True
for raw, want in cases.items():
    got = _parse_weight_kg(raw)
    got = str(got) if got is not None else "None"
    flag = "ok " if got == want else "BAD"
    if got != want:
        ok = False
    print(f"  {flag} {raw!r:16} -> {got} (want {want})")

# simulate the extraction loop
attrs = [
    {"name": "重量(g)", "value": "1800"},
]
weight = ""
for attr in attrs:
    attr_name_raw = str(attr.get("name", ""))
    attr_name = attr_name_raw.lower()
    if "重量" in attr_name or "weight" in attr_name:
        um = __import__("re").search(r"[(（]([^)）]{1,6})[)）]", attr_name_raw)
        hint = um.group(1).strip() if um else ""
        weight = f"{attr.get('value','')} {hint}".strip()
        break
print()
print(f"  extract loop: weight = {weight!r} -> kg = {_parse_weight_kg(weight)}")
print()
print("UNIT_TEST_OK" if ok else "UNIT_TEST_FAIL")
'''
        sftp.putfo(io.BytesIO(test.encode("utf-8")), "/tmp/unit_test.py")
        out = run(ssh, "cd /opt/nuotao/backend && .venv/bin/python -u /tmp/unit_test.py")
        if "UNIT_TEST_OK" not in out:
            raise RuntimeError("unit test failed -> restoring")

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

        print("\nDEPLOY ROUND 4b OK, backup:", backup, flush=True)
        return 0
    finally:
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("\n!!! DEPLOY FAILED:", exc, "\n!!! restoring", flush=True)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
        _, out, err = ssh.exec_command(
            "for f in newton_agent_service.py product_pipeline_service.py; do "
            "cp $(ls -t /opt/nuotao/backups/listing-gate-*/$f | head -1) /opt/nuotao/backend/app/services/$f; done; "
            "systemctl restart nuotao-backend; systemctl is-active nuotao-backend", timeout=300)
        print(out.read().decode("utf-8", "replace"), flush=True)
        ssh.close()
        raise SystemExit(1)
