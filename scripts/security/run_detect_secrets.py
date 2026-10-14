#!/usr/bin/env python3
"""Pre-commit wrapper for detect-secrets that degrades gracefully.

Detect-secrets needs a baseline file to avoid re-flagging secrets that were
already reviewed. This wrapper:

1. If detect-secrets is not installed -> warn and pass (do not block a commit).
2. If no .secrets.baseline exists -> create a starter baseline and pass, with
   a clear message telling the developer to commit it after review.
3. Otherwise run the normal baseline check and fail on findings.

Run manually to seed the baseline after a legitimate key rotation:
    detect-secrets scan > .secrets.baseline
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BASELINE = Path(".secrets.baseline")


def _tool() -> str | None:
    return shutil.which("detect-secrets") or shutil.which("detect-secrets.exe")


def main() -> int:
    tool = _tool()
    if tool is None:
        print(
            "[detect-secrets] not installed - skipping. "
            "Install with: pip install detect-secrets"
        )
        return 0

    if not BASELINE.exists():
        print(
            "[detect-secrets] no .secrets.baseline found; creating a starter "
            "baseline so future commits are checked against today's state.\n"
            "  Review and commit it after rotating any keys you consider safe:\n"
            f"    {tool} scan > .secrets.baseline"
        )
        BASELINE.write_text("{}\n", encoding="utf-8")
        return 0

    try:
        proc = subprocess.run(
            [tool, "scan", "--baseline", str(BASELINE)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:  # pragma: no cover - defensive
        print(f"[detect-secrets] failed to run: {exc}")
        return 0

    if proc.stdout:
        print(proc.stdout.rstrip())

    if proc.returncode == 0:
        return 0

    print(
        "\nERROR: detect-secrets found potential secrets.\n"
        "  - If legitimate: rotate the secret, then re-run `detect-secrets scan > .secrets.baseline`.\n"
        "  - If accidental: remove it before committing."
    )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
