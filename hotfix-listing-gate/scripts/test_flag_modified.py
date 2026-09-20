"""Compare flag_modified vs reassignment vs bulk update for the JSON meta column."""

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
KEY = "_persist_test3"


async def read():
    from app.core.database import async_session_factory
    from app.models.product import Product
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        return dict(p.meta or {})


async def main() -> None:
    from sqlalchemy import update
    from sqlalchemy.orm.attributes import flag_modified
    from app.core.database import async_session_factory
    from app.models.product import Product

    print("baseline      :", (await read()).get(KEY))

    # D: flag_modified after in-place mutation
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        meta = dict(p.meta or {})
        meta[KEY] = "D-flag-modified"
        p.meta = meta
        flag_modified(p, "meta")
        await s.commit()
    print("after D       :", (await read()).get(KEY))

    # E: bulk UPDATE statement
    new_meta = dict((await read()))
    new_meta[KEY] = "E-bulk-update"
    async with async_session_factory() as s:
        await s.execute(
            update(Product).where(Product.id == TARGET).values(meta=new_meta)
        )
        await s.commit()
    print("after E       :", (await read()).get(KEY))

    # F: ORM reassignment + flag_modified, no explicit flag on a fresh dict
    meta2 = dict((await read()))
    meta2[KEY] = "F-copy-plus-flag"
    async with async_session_factory() as s:
        p = await s.get(Product, TARGET)
        p.meta = meta2
        flag_modified(p, "meta")
        await s.commit()
    print("after F       :", (await read()).get(KEY))

    # cleanup
    meta3 = dict((await read()))
    meta3.pop(KEY, None)
    async with async_session_factory() as s:
        await s.execute(update(Product).where(Product.id == TARGET).values(meta=meta3))
        await s.commit()
    print("after cleanup :", (await read()).get(KEY))


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
        print("-- stderr --", et.rstrip()[:900], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
