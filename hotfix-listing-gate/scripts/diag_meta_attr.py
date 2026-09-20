"""Introspect Product.meta: is it a real mapped column or shadowed?"""

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
from app.models.product import Product

# What does the class attribute look like?
for attr in ("meta", "source_url"):
    obj = getattr(Product, attr, None)
    print(f"Product.{attr} type      : {type(obj).__name__}")
    print(f"  in mapper.columns      : {attr in Product.__mapper__.columns.keys()}")
    cls_attr = Product.__dict__.get(attr, "<not in __dict__>")
    print(f"  in Product.__dict__    : {type(cls_attr).__name__}")

print()
m = Product.__mapper__.get_property("meta") if "meta" in Product.__mapper__.columns.keys() else None
if m is not None:
    print("mapper property 'meta'   :", type(m).__name__, "|", m.columns[0].name, "|", m.columns[0].type)
    print("  uselist:", getattr(m, "uselist", None))

# base.py hooks that could intercept attribute assignment
import app.models.base as base
print()
print("base module members with 'meta' in name:")
for name in dir(base):
    if "meta" in name.lower():
        print("  ", name, "->", type(getattr(base, name)).__name__)
print()
print("Base has __setattr__:", "__setattr__" in type(base.Base).__dict__)
print("Base has __init_subclass__:", "__init_subclass__" in type(base.Base).__dict__)
PYEOF
"""


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    _, out, err = ssh.exec_command(PY, timeout=120)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:800], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
