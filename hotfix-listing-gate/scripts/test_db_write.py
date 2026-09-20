"""Minimal: can this session write to the products table at all?"""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

SETUP = """set -a
. /opt/nuotao/backend/.env 2>/dev/null
set +a
cd /opt/nuotao/backend
"""

PY = SETUP + r""".venv/bin/python - <<'PYEOF'
import asyncio

TARGET = "f865672b-2d98-4233-90cc-03b97aa743f6"


async def main() -> None:
    from app.core.database import async_session_factory
    from app.models.product import Product

    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        print("1. before      source_url:", repr((p.source_url or "")[-24:]))
        p.source_url = "ORM_PROBE_1"
        await s.commit()
        print("2. commit rc:", "ok")

    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        print("3. reread     source_url:", repr(p.source_url))

    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        p.source_url = "ORM_PROBE_2"
        await s.commit()
        await s.refresh(p)
        print("4. same sess after refresh:", repr(p.source_url))

    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        print("5. final reread           :", repr(p.source_url))

    # restore
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        p.source_url = None
        await s.commit()
        print("6. restored to None")


asyncio.run(main())
PYEOF
"""


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    _, out, err = ssh.exec_command(PY, timeout=240)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:1000], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
