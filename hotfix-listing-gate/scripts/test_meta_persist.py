"""Empirically test which meta-assignment pattern actually persists.

Runs against the real product row using a throwaway key that is removed at the
end, so nothing else in the row changes.
"""

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
KEY = "_persist_test"


async def fresh_get():
    from app.core.database import async_session_factory
    from app.models.product import Product
    s = async_session_factory()
    p = await s.get(Product, TARGET)
    return s, p


async def fresh_read():
    from app.core.database import async_session_factory
    from app.models.product import Product
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        return (p.meta or {}).get(KEY)


async def main() -> None:
    # baseline
    print("baseline          :", await fresh_read())

    # variant A: mutate in place + reassign the SAME object
    s, p = await fresh_get()
    meta = p.meta if isinstance(p.meta, dict) else {}
    meta[KEY] = "A-same-object"
    p.meta = meta
    await s.commit()
    await s.close()
    print("after A (same obj):", await fresh_read())

    # variant B: assign a NEW dict object
    s, p = await fresh_get()
    meta = p.meta if isinstance(p.meta, dict) else {}
    meta[KEY] = "B-new-object"
    p.meta = dict(meta)
    await s.commit()
    await s.close()
    print("after B (new dict):", await fresh_read())

    # variant C: in-place mutation only, no reassignment
    s, p = await fresh_get()
    meta = p.meta if isinstance(p.meta, dict) else {}
    meta[KEY] = "C-inplace-only"
    await s.commit()
    await s.close()
    print("after C (in-place):", await fresh_read())

    # cleanup
    s, p = await fresh_get()
    meta = p.meta if isinstance(p.meta, dict) else {}
    meta.pop(KEY, None)
    p.meta = dict(meta)
    await s.commit()
    await s.close()
    print("after cleanup     :", await fresh_read())


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
        print("-- stderr --", et.rstrip()[:800], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
