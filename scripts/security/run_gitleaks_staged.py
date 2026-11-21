#!/usr/bin/env python3
"""Pre-commit gitleaks wrapper that scans ONLY the staged diff.

Why this exists (Issue #22): the previous local hook ran
`gitleaks detect --source . --no-git`, which scanned the ENTIRE worktree on
every commit. The repo carries ~605 pre-existing findings (legacy CI test keys
in docs/tests), so that gate blocked every commit regardless of content once
gitleaks 8.30.1 stopped honouring the old `.gitleaksignore` value format.
Meanwhile CI (`secret-scanning.yml`) scans only the diff via
`gitleaks-action@v2 target: diff` and passes. The local gate therefore
disagreed with CI and became pure noise + a hard blocker.

This wrapper aligns the local gate with CI without lowering the security bar:

1. gitleaks not installed -> warn and pass (never block on a missing tool).
2. No staged changes -> pass (nothing new to scan).
3. Otherwise pipe `git diff --staged` into `gitleaks stdin` and FAIL on any
   finding, so a genuinely new secret is still blocked before it lands.

The ~605 historical findings stay out of the way because they are not in the
staged diff - exactly like CI treats them. They are NOT waved through: a
full-history scan is still available manually, and CI's diff scan still catches
any newly added secret.

Manual full scan (unchanged semantics, new 8.30.1 command names):
    gitleaks git . --redact --no-banner      # scan commit history
    gitleaks dir . --redact --no-banner      # scan working tree files
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _gitleaks() -> str | None:
    return shutil.which("gitleaks") or shutil.which("gitleaks.exe")


def _staged_diff() -> bytes | None:
    """Return the staged diff, or None if git is unavailable / errored."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--staged"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:  # pragma: no cover - defensive
        print(f"[gitleaks] failed to run git: {exc}")
        return None
    if proc.returncode != 0:
        # Not a git repo or git blew up - don't block the commit here.
        return None
    return proc.stdout


def main() -> int:
    tool = _gitleaks()
    if tool is None:
        print(
            "[gitleaks] not installed - skipping staged secret scan. "
            "Install with: winget install Gitleaks.Gitleaks"
        )
        return 0

    diff = _staged_diff()
    if diff is None:
        return 0
    if not diff.strip():
        # Nothing staged -> nothing new to scan. Pass.
        return 0

    try:
        proc = subprocess.run(
            [tool, "stdin", "--redact", "--no-banner"],
            input=diff,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:  # pragma: no cover - defensive
        print(f"[gitleaks] failed to run: {exc}")
        return 0

    if proc.stdout:
        print(proc.stdout.decode("utf-8", errors="replace").rstrip())

    if proc.returncode == 0:
        return 0

    print(
        "\nERROR: gitleaks found a potential secret in the STAGED changes.\n"
        "  - If accidental: remove it before committing.\n"
        "  - If legitimate (e.g. a documented test value): rotate/remove it, or\n"
        "    add a narrowly-scoped entry to .gitleaks.toml [allowlist] - never a\n"
        "    whole-file or global exemption.\n"
        "  - Full-history scan (manual): gitleaks git . --redact --no-banner"
    )
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
