"""Newton timeout experiment: is max_wait=90 the failure cause?

Run in background - a single extract can take up to ~300s.
"""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")
SETUP = "set -a\n. /opt/nuotao/backend/.env 2>/dev/null\nset +a\ncd /opt/nuotao/backend\n"

REMOTE = r'''import asyncio, json, time

def p(*a):
    print(*a, flush=True)

def main():
    from app.services.newton_agent_service import (
        list_models, query_points, extract_1688_product, is_configured,
    )

    p("=== 0. preflight ===")
    p("  configured:", is_configured())
    try:
        pts = query_points()
        p("  points:", json.dumps({k: v for k, v in pts.items() if k != "raw"},
                                  ensure_ascii=False, default=str)[:400])
    except Exception as exc:
        p("  points call failed:", repr(exc)[:200])
    try:
        models = list_models()
        p("  models:", json.dumps(models.get("raw") or models,
                                 ensure_ascii=False, default=str)[:600])
    except Exception as exc:
        p("  list_models failed:", repr(exc)[:200])

    url = "https://detail.1688.com/offer/771641344658.html"
    pid = "771641344658"

    for wait in (90, 300):
        p()
        p(f"=== extract_1688_product max_wait={wait} ===")
        t0 = time.time()
        try:
            r = extract_1688_product(url, pid, max_wait=wait)
        except Exception as exc:
            p(f"  EXC after {time.time()-t0:.0f}s:", repr(exc)[:200])
            continue
        p(f"  elapsed {time.time()-t0:.0f}s success={r.get('success')} "
          f"status={r.get('status')} task_id={str(r.get('task_id'))[:36]}")
        p(f"  error={str(r.get('error'))[:200]}")
        if r.get("success"):
            p("  --- RAW RETURN KEYS:", sorted(r.keys()))
            for k in ("title", "product_id", "price_min", "price_max", "price_range",
                      "moq", "supplier_name", "image_urls", "description", "category"):
                p(f"    {k:14s}: {str(r.get(k))[:160]}")
            if r.get("image_urls"):
                p("    IMAGE URLS:")
                for u in (r.get("image_urls") or [])[:6]:
                    p("      -", str(u)[:150])
        raw = r.get("raw") or {}
        if isinstance(raw, dict) and raw:
            p("  raw.status:", raw.get("status"),
              "content_len:", len(str(raw.get("content") or "")))

    p()
    p("EXPERIMENT_DONE")


main()
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/newton_exp.py", "w") as fh:
        fh.write(REMOTE.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command(SETUP + ".venv/bin/python -u /tmp/newton_exp.py",
                                   timeout=900)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:800], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
