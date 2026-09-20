"""Pre-flight: confirm the run_v3_gate anchor appears exactly once."""

from __future__ import annotations

import os
import paramiko

KEY = os.path.expanduser(r"~/.ssh/id_ed25519_nuotao")

CHECK_PY = r'''
import pathlib

src = pathlib.Path(
    "/opt/nuotao/backend/app/services/product_pipeline_service.py"
).read_text(encoding="utf-8")
anchor = (
    "        session.add(product)\n"
    "    await session.flush()\n"
    "\n"
    "    evaluation = await evaluate_product("
)
print("anchor count:", src.count(anchor))
print("BUG-13 present:", "BUG-13" in src)
print("flag_modified already referenced in file:", "flag_modified" in src)
i = src.find(anchor)
print()
print("--- region around anchor ---")
print(src[max(0, i - 260):i + len(anchor) + 140])
'''


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname="95.217.218.178", port=22, username="root", key_filename=KEY, timeout=20)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/preflight_r3.py", "w") as fh:
        fh.write(CHECK_PY.encode("utf-8"))
    sftp.close()
    _, out, err = ssh.exec_command("python3 /tmp/preflight_r3.py", timeout=120)
    data = out.read().decode("utf-8", "replace")
    et = err.read().decode("utf-8", "replace")
    print(data.rstrip(), flush=True)
    if et.strip():
        print("-- stderr --", et.rstrip()[:600], flush=True)
    ssh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
