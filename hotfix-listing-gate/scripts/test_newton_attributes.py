"""Test: does asking Newton for the attribute table unlock weight/dimensions?

Read-only experiment. Does NOT modify production code.
"""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import json, time, re

def p(*a):
    print(*a, flush=True)

from app.services.newton_agent_service import (
    create_agent_task, get_task_status, kill_task, _extract_json_object,
)

url = "https://detail.1688.com/offer/771641344658.html"
pid = "771641344658"

ENHANCED = f"""请使用你已授权的 1688 供应链能力读取下面这个公开商品页，并严格按以下英文键返回 JSON：
{{
  "title": "商品标题",
  "product_id": "商品ID",
  "price_min": 最低价格数字或null,
  "price_max": 最高价格数字或null,
  "price_range": "页面展示的原始价格区间",
  "moq": 最小起订量数字或null,
  "supplier_name": "供应商公司名称",
  "image_urls": ["主图URL", "其他图片URL"],
  "description": "页面公开商品描述或标题",
  "category": "商品类目",
  "attributes": [
    {{"name": "属性名原文", "value": "属性值原文"}}
  ]
}}

要求：
1. 只输出 JSON 对象，不要 Markdown，不要解释。
2. attributes 必须完整搬运页面上的「商品属性」/「产品参数」表格，一行一条，name 和 value 都用页面原文。
   必须包含页面上出现的：重量、尺寸/规格、材质、颜色、品牌、型号 等所有可见属性。
3. 禁止猜测；页面无法读取或字段不存在时使用 null 或空数组。
4. 不要联系供应商，不要下单，不要修改任何数据。

商品ID：{pid}
商品链接：{url}
"""

p("=== enhanced-prompt Newton run (max_wait=300) ===")
created = create_agent_task(ENHANCED, auto=True, model="qwen3.6-plus")
p("  create success:", created.get("success"), "task_id:", created.get("task_id"))
if not created.get("task_id"):
    p("  create failed:", created.get("error"))
    raise SystemExit(0)

task_id = str(created["task_id"])
t0 = time.monotonic()
last = "UNKNOWN"
while time.monotonic() - t0 < 300:
    sr = get_task_status(task_id)
    if not sr.get("success"):
        p("  status query failed:", sr.get("error"))
        break
    last = str(sr.get("status") or "UNKNOWN").upper()
    if last in {"END", "COMPLETED", "SUCCESS"}:
        raw = sr.get("raw") or {}
        content = str(raw.get("content") or "")
        p(f"  elapsed {time.monotonic()-t0:.0f}s status={last} content_len={len(content)}")
        try:
            parsed = _extract_json_object(content)
        except Exception as exc:
            p("  PARSE FAILED:", repr(exc)[:200])
            p("  raw content head:", content[:500])
            raise SystemExit(0)
        p()
        p("=== parsed Newton JSON ===")
        p("  keys:", sorted(parsed.keys()))
        for k, v in parsed.items():
            if k == "attributes":
                continue
            p(f"    {k:14s}: {str(v)[:120]}")
        attrs = parsed.get("attributes") or []
        p(f"  attributes: {len(attrs)} entries")
        for a in attrs[:40]:
            p("    -", json.dumps(a, ensure_ascii=False))
        p()
        p("=== weight / dimensions extractable? ===")
        joined = json.dumps(attrs, ensure_ascii=False)
        for probe in ("重量", "weight", "尺寸", "规格", "dimension", "材质", "material",
                      "品牌", "brand", "型号"):
            p(f"    {probe:10s}: {'FOUND' if probe in joined else '-'}")
        break
    if last in {"FAILED", "ERROR", "KILL", "KILLED"}:
        p("  task FAILED:", last)
        break
    time.sleep(3)
else:
    p("  TIMEOUT after 300s, last:", last)
    kill_task(task_id)

p()
p("EXPERIMENT_DONE")
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/attr_test.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/attr_test.py", timeout=600)
    print(out.read().decode("utf-8", "replace").rstrip(), flush=True)
    et = err.read().decode("utf-8", "replace")
    if et.strip():
        print("-- stderr --", et.rstrip()[:600], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
