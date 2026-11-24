"""G3 runtime-environment pre-check on the SYNTHETIC export pipeline.

NOT a production-data operation: it runs the desensitization pipeline on the
synthetic fixture (``tests/fixtures/v28_export_sample/raw/``) with the
test-only salt, into OS temp directories. It never touches production data,
never reads or receives a production salt, never creates a mapping file in the
repository, and never provisions the real Owner-controlled ``id_map_dir``.

It produces the evidence for ``docs/V2_8_EXPORT_G3_ENV_PRECHECK.md``:
  * id_map directory / file permissions (Unix mode + Windows NTFS ACL)
  * directory ownership
  * directory outside the Git worktree (rejected by the script)
  * directory independent of raw/out (rejected by the script)
  * not on a cloud-sync / public-share path (OneDrive/Dropbox/Syncthing probe)
  * salt not leaked into stdout/stderr/logs or the report
  * id-map artifact never inside the ordinary delivery package
  * existing mapping file is never overwritten (O_EXCL fail-closed)
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "tests" / "fixtures" / "v28_export_sample" / "raw"
SALT = REPO / "tests" / "fixtures" / "v28_export_sample" / "test-salt.txt"

CLOUD_SYNC_MARKERS = ("onedrive", "dropbox", "syncthing", "nextcloud", "icloud")


def _run(secure_dir: Path, out_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "v28_export_desensitize.py"),
            "--raw-dir",
            str(RAW),
            "--out-dir",
            str(out_dir),
            "--salt-file",
            str(SALT),
            "--workspace-id",
            "ws-test-1",
            "--id-map-dir",
            str(secure_dir),
            "--id-map-retention-days",
            "30",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    findings: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="v28-g3-precheck-") as tmp_root:
        secure_dir = Path(tmp_root) / "restricted-id-map"
        out_dir = Path(tmp_root) / "delivery-out"
        secure_dir.mkdir(mode=0o700)
        out_dir.mkdir()

        # 1) happy-path run
        result = _run(secure_dir, out_dir)
        findings["pipeline_run"] = {
            "returncode": result.returncode,
            "stdout": result.stdout[-1200:],
            "stderr": result.stderr[-1200:],
        }

        # 2) id-map file + dir permissions
        idmap = secure_dir / "_id_map_pseudo.json"
        st_file = idmap.stat()
        st_dir = secure_dir.stat()
        findings["file_permissions"] = {
            "path": str(idmap),
            "exists": idmap.exists(),
            "mode_octal": oct(stat.S_IMODE(st_file.st_mode)),
            "size_bytes": st_file.st_size,
        }
        findings["dir_permissions"] = {
            "path": str(secure_dir),
            "mode_octal": oct(stat.S_IMODE(st_dir.st_mode)),
        }

        # 3) Windows NTFS ACL (icacls)
        try:
            acl = subprocess.run(
                ["icacls", str(idmap)],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            findings["ntfs_acl_file"] = acl.strip().splitlines()
        except Exception as exc:  # noqa: BLE001
            findings["ntfs_acl_file"] = {"error": str(exc)}

        # 4) ownership
        findings["ownership"] = {
            "uid": st_file.st_uid,
            "gid": st_file.st_gid,
            "user_owner_expected": "current_process",
        }

        # 5) salt leakage probe
        combined = result.stdout + result.stderr
        if idmap.exists():
            combined += idmap.read_text(encoding="utf-8")
        salt_text = SALT.read_text(encoding="utf-8").strip()
        findings["salt_leakage"] = {
            "salt_present_in_logs": salt_text in combined,
            "salt_in_id_map_payload": salt_text in idmap.read_text(encoding="utf-8"),
        }

        # 6) id-map inside the delivery package? (must be absent)
        delivery_files = sorted(p.name for p in out_dir.iterdir())
        findings["delivery_package"] = {
            "files": delivery_files,
            "id_map_present_in_delivery": "_id_map_pseudo.json" in delivery_files,
        }

        # 7) no-overwrite: second run must fail (O_EXCL) on an existing map
        result2 = _run(secure_dir, out_dir)
        findings["no_overwrite"] = {
            "second_run_returncode": result2.returncode,
            "second_run_failed_closed": result2.returncode != 0,
            "stderr": result2.stderr[-400:],
        }

        # 8) inside-Git-worktree rejection is covered by
        # test_id_map_not_in_git_and_rejected_inside_worktree (in-repo probe,
        # cleaned up by the test). We only re-verify the detection predicate on
        # the repo path without creating any directory inside the worktree.
        findings["inside_git_worktree_rejected"] = {
            "covered_by_test": "test_id_map_not_in_git_and_rejected_inside_worktree",
            "repo_path_would_be_detected": _is_inside_repo(REPO),
            "note": "no directory created inside the worktree for this pre-check",
        }

        # 9) overlap-with-out rejection
        overlap = out_dir / "restricted-id-map"
        overlap.mkdir()
        try:
            result4 = _run(overlap, out_dir)
            findings["overlap_with_out_rejected"] = {
                "returncode": result4.returncode,
                "rejected": result4.returncode != 0,
                "stderr": result4.stderr[-400:],
            }
        finally:
            for f in overlap.iterdir():
                f.unlink()
            overlap.rmdir()

        # 10) cloud-sync / public-share path probe (informational)
        norm = str(secure_dir).lower()
        findings["cloud_sync_probe"] = {
            "path": str(secure_dir),
            "matched_marker": [m for m in CLOUD_SYNC_MARKERS if m in norm] or "none",
            "is_inside_repo": _is_inside_repo(secure_dir),
        }

    print(json.dumps(findings, indent=2, ensure_ascii=False))
    return 0


def _is_inside_repo(path: Path) -> bool:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
