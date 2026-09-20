"""Find out why meta writes are not persisting at all."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

SETUP = """set -a
. /opt/nuotao/backend/.env 2>/dev/null
set +a
cd /opt/nuotao/backend
"""

CMDS = [
    ("A. AI_JSON definition", r"""
grep -rn 'AI_JSON' /opt/nuotao/backend/app/models/*.py /opt/nuotao/backend/app/core/*.py 2>/dev/null | grep -iE 'class|=|import' | head -10
echo '---'
grep -rn -A12 'class AI_JSON' /opt/nuotao/backend/app/ 2>/dev/null | head -25
"""),
    ("B. direct SQL write test + db sanity", SETUP + r""".venv/bin/python - <<'PYEOF'
import asyncio

TARGET = "f865672b-2d98-4233-90cc-03b97aa743f6"


async def main() -> None:
    from sqlalchemy import text
    from app.core.database import async_session_factory

    async with async_session_factory() as s:
        info = (await s.execute(text(
            "SELECT current_database(), current_user, transaction_read_only, "
            "pg_is_in_recovery(), inet_server_addr(), inet_server_port()"
        ))).one()
        print("db=%s user=%s read_only=%s recovery=%s host=%s:%s" % info)

    # ORM write of an unrelated, definitely-nullable column
    async with async_session_factory() as s:
        from app.models.product import Product
        p = await s.get(Product, TARGET)
        old = p.source_url
        p.source_url = (old or "") + "|PERSIST_PROBE"
        await s.commit()
    async with async_session_factory() as s:
        from app.models.product import Product
        p = await s.get(Product, TARGET)
        print("source_url after ORM write :", repr((p.source_url or "")[-20:]))

    # raw SQL write
    async with async_session_factory() as s:
        res = await s.execute(text(
            "UPDATE products SET source_url = :v WHERE id = :i RETURNING id, source_url"
        ), {"v": "RAW_SQL_PROBE", "i": TARGET})
        await s.commit()
        print("raw SQL update             :", res.all())
    async with async_session_factory() as s:
        row = (await s.execute(text(
            "SELECT source_url FROM products WHERE id = :i"), {"i": TARGET})).one()
        print("source_url after raw SQL   :", repr(row[0]))

    # is 'meta' maybe a generated/computed column?
    async with async_session_factory() as s:
        row = (await s.execute(text(
            "SELECT column_name, data_type, is_generated, generation_expression "
            "FROM information_schema.columns "
            "WHERE table_name='products' AND column_name IN ('meta','source_url')"
        ))).all()
        print("column meta/source_url     :", [tuple(r) for r in row])


asyncio.run(main())
PYEOF
"""),
]


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    for label, cmd in CMDS:
        _, out, err = ssh.exec_command(cmd, timeout=240)
        data = out.read().decode("utf-8", "replace")
        et = err.read().decode("utf-8", "replace")
        print("\n" + "=" * 78, "\n### " + label, "\n" + "=" * 78, flush=True)
        print(data.rstrip()[:3500], flush=True)
        if et.strip():
            print("-- stderr --", et.rstrip()[:600], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
