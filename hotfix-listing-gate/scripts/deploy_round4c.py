"""Round 4c deploy: weight unit + package-preferred dimensions.

Anchors corrected (prod file is black-formatted). Each patch prints PATCH_OK and
the deploy aborts + restores unless that sentinel is seen (round 4b bug: a
sub-script failure was not detected).

Changes:
  1. 重量: the unit lives in the attribute NAME (「重量(g)」), not the value.
     Value-only parsing turned 1800 g into 1800 kg. Standard is kg.
  2. 尺寸: prefer 包装长/宽/高 (shipping cartons) over the product 规格; freight
     is charged on the box, and 47x47x90 vs 92x16x16 is a ~20x difference.
"""

from __future__ import annotations

import io
import time
import paramiko

KEY = r"C:\Users\神魂之人\.ssh\id_ed25519_nuotao"
BACKEND = "/opt/nuotao/backend"
P = f"{BACKEND}/app/services/product_pipeline_service.py"

PATCH = r'''
import pathlib, sys

path = pathlib.Path("/opt/nuotao/backend/app/services/product_pipeline_service.py")
src = path.read_text(encoding="utf-8")

if "ROUND-4C" in src:
    print("already patched, skipping")
    print("PATCH_OK")
    sys.exit(0)

# --- Fix 1: dimensions prefer the shipping carton ---
anchor_dims = (
    '    # 提取尺寸\n'
    '    dimensions = ""\n'
    '    for attr in attributes if isinstance(attributes, list) else []:\n'
    '        if isinstance(attr, dict):\n'
    '            attr_name = (\n'
    '                attr.get("name") or attr.get("attributeName") or ""\n'
    '            ).lower()\n'
    '            if "尺寸" in attr_name or "dimension" in attr_name or "规格" in attr_name:\n'
    '                dimensions = attr.get("value", "")\n'
    '                break\n'
)
if src.count(anchor_dims) != 1:
    print("ABORT: anchor_dims count =", src.count(anchor_dims))
    sys.exit(1)

src = src.replace(anchor_dims,
    '    # 提取尺寸（ROUND-4C: 优先包装尺寸——运费按外包装计费；\n'
    '    # 产品规格 47x47x90 与包装 92x16x16 差约 20 倍）\n'
    '    dimensions = ""\n'
    '    pack = {}\n'
    '    for attr in attributes if isinstance(attributes, list) else []:\n'
    '        if isinstance(attr, dict):\n'
    '            attr_name_raw = str(\n'
    '                attr.get("name") or attr.get("attributeName") or ""\n'
    '            )\n'
    '            attr_name = attr_name_raw.lower()\n'
    '            for axis in ("长", "宽", "高"):\n'
    '                if attr_name.startswith("包装" + axis):\n'
    '                    pack[axis] = str(attr.get("value", "")).strip()\n'
    '    if all(pack.get(a) for a in ("长", "宽", "高")):\n'
    '        dimensions = f"{pack[\'长\']}*{pack[\'宽\']}*{pack[\'高\']}"\n'
    '    if not dimensions:\n'
    '        for attr in attributes if isinstance(attributes, list) else []:\n'
    '            if isinstance(attr, dict):\n'
    '                attr_name = (\n'
    '                    attr.get("name") or attr.get("attributeName") or ""\n'
    '                ).lower()\n'
    '                if "尺寸" in attr_name or "dimension" in attr_name or "规格" in attr_name:\n'
    '                    dimensions = attr.get("value", "")\n'
    '                    break\n'
)

# --- Fix 2: weight unit comes from the attribute name ---
anchor_wt = (
    '    # 提取重量\n'
    '    weight = ""\n'
    '    for attr in attributes if isinstance(attributes, list) else []:\n'
    '        if isinstance(attr, dict):\n'
    '            attr_name = (\n'
    '                attr.get("name") or attr.get("attributeName") or ""\n'
    '            ).lower()\n'
    '            if "重量" in attr_name or "weight" in attr_name:\n'
    '                weight = attr.get("value", "")\n'
    '                break\n'
)
if src.count(anchor_wt) != 1:
    print("ABORT: anchor_wt count =", src.count(anchor_wt))
    sys.exit(1)

src = src.replace(anchor_wt,
    '    # 提取重量（ROUND-4C: 单位在属性名里，如「重量(g)」。\n'
    '    # 只取 value 会把 1800 g 当成 1800 kg，运费错一千倍；标准统一 kg）\n'
    '    weight = ""\n'
    '    for attr in attributes if isinstance(attributes, list) else []:\n'
    '        if isinstance(attr, dict):\n'
    '            attr_name_raw = str(\n'
    '                attr.get("name") or attr.get("attributeName") or ""\n'
    '            )\n'
    '            attr_name = attr_name_raw.lower()\n'
    '            if "重量" in attr_name or "weight" in attr_name:\n'
    '                unit_match = re.search(r"[(（]([^)）]{1,6})[)）]", attr_name_raw)\n'
    '                unit_hint = unit_match.group(1).strip() if unit_match else ""\n'
    '                weight = f"{attr.get(\'value\', \'\')} {unit_hint}".strip()\n'
    '                break\n'
)

path.write_text(src, encoding="utf-8")
print("product_pipeline_service.py patched")
print("PATCH_OK")
'''


def run(ssh, script, timeout=300):
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
        run(ssh, f"mkdir -p {backup} && cp {P} {backup}/ && ls {backup}")

        print("\n" + "=" * 78, "\n### 1. patch", "\n" + "=" * 78, flush=True)
        sftp.putfo(io.BytesIO(PATCH.encode("utf-8")), "/tmp/patch_p4c.py")
        out = run(ssh, "cd /opt/nuotao/backend && .venv/bin/python /tmp/patch_p4c.py")
        if "PATCH_OK" not in out:
            raise RuntimeError("patch did not report PATCH_OK -> restoring")

        print("\n" + "=" * 78, "\n### 2. grep confirm", "\n" + "=" * 78, flush=True)
        run(ssh, f"grep -n -B2 -A20 'ROUND-4C' {P}")

        print("\n" + "=" * 78, "\n### 3. compile + behavioural test", "\n" + "=" * 78, flush=True)
        out = run(ssh, "cd /opt/nuotao/backend && .venv/bin/python -m compileall -q "
                       "app/services/product_pipeline_service.py && echo COMPILE_OK")
        if "COMPILE_OK" not in out:
            raise RuntimeError("compile failed -> restoring")

        test = r'''
import json
from app.services.product_pipeline_service import convert_1688_to_pipeline_input, _parse_weight_kg

newton = {
    "success": True,
    "product": {
        "subject": "严选户外高靠背月亮椅便携式垂钓凳子美术生写生椅野外露营折叠椅",
        "description": "600D牛津布耐磨抗撕更耐用，碳钢支架承重240斤稳如磐石",
        "price": "19",
        "price_range": [{"startQuantity": 1, "price": 19}],
        "images": ["https://cbu01.alicdn.com/img/ibank/a.jpg"],
        "company_name": "固安悦步自由户外用品有限公司",
        "supplier": {"company_name": "固安悦步自由户外用品有限公司"},
        "category_name": "户外/露营/折叠椅",
        "sku_list": [],
        "attributes": [
            {"name": "材质", "value": "牛津布,碳钢"},
            {"name": "规格(长*宽*高)", "value": "47cm*47cm*90cm"},
            {"name": "品牌", "value": "怡佳文嫣"},
            {"name": "颜色", "value": "绿色,白色,卡其色,黑色"},
            {"name": "产地", "value": "河北廊坊"},
            {"name": "包装长(cm)", "value": "92"},
            {"name": "包装宽(cm)", "value": "16"},
            {"name": "包装高(cm)", "value": "16"},
            {"name": "重量(g)", "value": "1800"},
        ],
    },
}

info = convert_1688_to_pipeline_input(newton, source_url="u", source_id="771641344658")
print("  name       :", info["name"][:40])
print("  category   :", info["category"])
print("  price      :", info["price"])
print("  weight raw :", repr(info["weight"]), "-> kg =", _parse_weight_kg(info["weight"]))
print("  dimensions :", repr(info["dimensions"]))
print("  materials  :", info["materials"])
print("  attributes :", len(info["attributes"]), "entries")
print("  images     :", len(info["images"]))

import app.services.listing_gate as g
dims = g.parse_dimensions(info["dimensions"])
attrs = g.collect_attributes(info)
print()
print("  parse_dimensions :", dims)
print("  collect_attrs    :", json.dumps(attrs, ensure_ascii=False)[:240])
print()

fails = []
def chk(label, got, want):
    flag = "ok " if got == want else "BAD"
    if got != want:
        fails.append(label)
    print(f"  {flag} {label}: {got!r} (want {want!r})")

chk("weight is 1.8 kg not 1800 kg", str(_parse_weight_kg(info["weight"])), "1.800")
chk("dimensions use carton", info["dimensions"], "92*16*16")
chk("carton parsed", dims, {"length": 92.0, "width": 16.0, "height": 16.0})
chk("attributes carried", len(info["attributes"]), 9)
chk("material extracted", info["materials"], ["牛津布,碳钢"])
chk("category from 1688", info["category"], "户外/露营/折叠椅")
print()
print("TEST_OK" if not fails else "TEST_FAIL: " + ", ".join(fails))
'''
        sftp.putfo(io.BytesIO(test.encode("utf-8")), "/tmp/test4c.py")
        out = run(ssh, "cd /opt/nuotao/backend && .venv/bin/python -u /tmp/test4c.py")
        if "TEST_OK" not in out:
            raise RuntimeError("behavioural test failed -> restoring")

        print("\n" + "=" * 78, "\n### 4. restart + wait readyz", "\n" + "=" * 78, flush=True)
        run(ssh, "systemctl restart nuotao-backend && systemctl is-active nuotao-backend")
        for attempt in range(1, 25):
            code = run(ssh, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/readyz")
            print(f"  attempt {attempt} readyz={code}", flush=True)
            if code.strip() == "200":
                break
            time.sleep(3)
        else:
            raise RuntimeError("backend not ready -> restoring")

        print("\nDEPLOY ROUND 4c OK, backup:", backup, flush=True)
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
            "for f in product_pipeline_service.py newton_agent_service.py; do "
            "src=$(ls -t /opt/nuotao/backups/listing-gate-*/$f | head -1); "
            "[ -n \"$src\" ] && cp \"$src\" /opt/nuotao/backend/app/services/$f; done; "
            "systemctl restart nuotao-backend; systemctl is-active nuotao-backend", timeout=300)
        print(out.read().decode("utf-8", "replace"), flush=True)
        ssh.close()
        raise SystemExit(1)
