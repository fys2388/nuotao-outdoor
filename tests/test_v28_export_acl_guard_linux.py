"""Owner G3 final security gate directive V1.0 §四: REAL Linux ACL runtime
verification.

These tests run ONLY on a real Linux host (``posix``); they are skipped on
every other platform. They exercise the production reader
(``verify_restricted_dir_acl``) against real directories/files with real
modes, owners and (optionally) extended ACLs — never against mocked data.

The six Owner-required runtime checks:

1. protected dir (``0700``, owner-only, no extended ACL) -> allowed
2. broad other/group mode (``0755``) -> rejected
3. named ACL / restrictive mask -> rejected (widening)
4. dir owned by a different uid -> rejected
5. getfacl unavailable / parse failure -> rejected (fail-closed)
6. file created in the protected dir re-read -> allowed (post-write re-verify)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.v28_export_acl_guard import verify_restricted_dir_acl  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="Linux host required (Owner directive V1.0 §四)"
)


def _current_uid() -> int:
    return os.getuid()


def _make_dir(base: Path, name: str, mode: int) -> Path:
    d = base / name
    d.mkdir()
    os.chmod(d, mode)
    return d


def _dump_evidence(path: Path, label: str) -> None:
    """Write stat + getfacl evidence for ``path`` to the evidence dir when
    ``V28_G3_EVIDENCE_DIR`` is set (Owner directive V1.0 §三)."""
    ev_dir = os.environ.get("V28_G3_EVIDENCE_DIR")
    if not ev_dir:
        return
    ev = Path(ev_dir)
    ev.mkdir(parents=True, exist_ok=True)
    out = ev / f"{label}.txt"
    parts = [
        f"# path: {path}",
        f"# stat: {os.stat(path).st_mode:o} uid={os.stat(path).st_uid}",
    ]
    gf = subprocess.run(["getfacl", "-p", str(path)], capture_output=True, text=True)
    parts.append(f"# getfacl_exit: {gf.returncode}")
    parts.append(gf.stdout.strip())
    if gf.stderr.strip():
        parts.append(f"# getfacl_stderr: {gf.stderr.strip()}")
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")


def test_1_protected_dir_allowed(tmp_path: Path) -> None:
    d = _make_dir(tmp_path, "protected", 0o700)
    verdict = verify_restricted_dir_acl(d, kind="dir", authorized_uid=_current_uid())
    assert verdict.allowed, verdict.reason
    _dump_evidence(d, "1_protected_dir")


def test_2_broad_mode_rejected(tmp_path: Path) -> None:
    d = _make_dir(tmp_path, "broad", 0o755)
    verdict = verify_restricted_dir_acl(d, kind="dir", authorized_uid=_current_uid())
    assert not verdict.allowed
    assert "mode" in verdict.reason.lower()


@pytest.mark.skipif(shutil.which("setfacl") is None, reason="setfacl not installed")
def test_3_named_acl_rejected(tmp_path: Path) -> None:
    """A named ACL entry is evidence of an extended ACL that the POSIX mode
    alone cannot exclude -> the guard must reject. We reset the ACL mask to
    ``---`` so the POSIX mode stays ``0700`` and the ACL-widening path (not
    the mode check) is what fires."""
    d = _make_dir(tmp_path, "named", 0o700)
    res = subprocess.run(
        ["setfacl", "-m", f"u:{_current_uid()}:rx", "-m", "m:---", str(d)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        pytest.skip(f"setfacl cannot add named entry: {res.stderr.strip()}")
    try:
        # Premise: the mask reset keeps the POSIX mode at 0700, so the ACL
        # widening check (not the mode check) is what must reject.
        mode = os.stat(d).st_mode & 0o777
        assert (
            mode == 0o700
        ), f"premise: mode should stay 0o700 after mask reset, got {oct(mode)}"
        verdict = verify_restricted_dir_acl(
            d, kind="dir", authorized_uid=_current_uid()
        )
        assert not verdict.allowed
        assert "widening" in verdict.reason.lower() or "acl" in verdict.reason.lower()
    finally:
        subprocess.run(["setfacl", "-b", str(d)], check=False)


@pytest.mark.skipif(
    getattr(os, "geteuid", lambda: -1)() != 0,
    reason="root required to chown to another uid",
)
def test_4_wrong_owner_rejected(tmp_path: Path) -> None:
    d = _make_dir(tmp_path, "other-owner", 0o700)
    nobody = 65534  # the conventional "nobody" uid
    os.chown(d, nobody, nobody)
    verdict = verify_restricted_dir_acl(d, kind="dir", authorized_uid=_current_uid())
    assert not verdict.allowed
    assert "owner" in verdict.reason.lower()


def test_5_getfacl_unavailable_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = _make_dir(tmp_path, "no-getfacl", 0o700)
    real_which = shutil.which

    def fake_which(name: str) -> str | None:
        if name == "getfacl":
            return None
        return real_which(name)

    monkeypatch.setattr(shutil, "which", fake_which)
    verdict = verify_restricted_dir_acl(d, kind="dir", authorized_uid=_current_uid())
    assert not verdict.allowed
    assert "getfacl" in verdict.reason.lower()


def test_6_file_reverified_allowed(tmp_path: Path) -> None:
    d = _make_dir(tmp_path, "file", 0o700)
    f = d / "_id_map_pseudo.json"
    f.write_text('{"schema_version":"v28-id-map-v1"}', encoding="utf-8")
    os.chmod(f, 0o600)
    verdict = verify_restricted_dir_acl(f, kind="file", authorized_uid=_current_uid())
    assert verdict.allowed, verdict.reason
    _dump_evidence(d, "6_protected_dir")
    _dump_evidence(f, "6_post_write_file")
