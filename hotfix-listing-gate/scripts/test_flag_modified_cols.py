"""Verify flag_modified persists on every JSON column the patch will touch."""

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


async def read_row():
    from app.core.database import async_session_factory
    from app.models.product import Product
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        return {"tags": p.tags, "attributes": p.attributes, "dimensions": p.dimensions,
                "meta_probe": (p.meta or {}).get("_probe")}


async def main() -> None:
    from sqlalchemy.orm.attributes import flag_modified
    from app.core.database import async_session_factory
    from app.models.product import Product

    print("baseline:", await read_row())

    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        p.tags = ["t1", "t2"]
        p.attributes = {"材质": ["铝合金"], "折叠尺寸": ["60*40*115"]}
        p.dimensions = {"length": 60.0, "width": 40.0, "height": 115.0}
        meta = dict(p.meta or {})
        meta["_probe"] = "ok"
        p.meta = meta
        flag_modified(p, "tags")
        flag_modified(p, "attributes")
        flag_modified(p, "dimensions")
        flag_modified(p, "meta")
        await s.commit()
    print("after   :", await read_row())

    # now try WITHOUT flag_modified to confirm the difference still holds
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        p.tags = ["t3"]
        p.attributes = {"x": ["y"]}
        p.dimensions = {"length": 1.0}
        meta = dict(p.meta or {})
        meta["_probe"] = "nobody"
        p.meta = meta
        await s.commit()
    print("no-flag :", await read_row())

    # restore
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        p.tags = []
        p.attributes = {}
        p.dimensions = None
        meta = dict(p.meta or {})
        meta.pop("_probe", None)
        p.meta = meta
        flag_modified(p, "tags")
        flag_modified(p, "attributes")
        flag_modified(p, "dimensions")
        flag_modified(p, "meta")
        await s.commit()
    print("restored:", await read_row())


asyncio.run(main())
PYEOF
"""


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    _, out, err = ssh.exec_command(PY, timeout=300)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:800], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
