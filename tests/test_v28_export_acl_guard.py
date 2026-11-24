"""Tests for ``scripts/v28_export_acl_guard.py`` (G3 cross-platform ACL).

Pure evaluator/parser tests run on every platform using synthetic snapshots
(no OS calls, fully deterministic). On Windows a smoke test reads the REAL
NTFS DACL of a temporary directory to prove the live reader works; it does not
assert a strict verdict because the temp ACL varies by machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.v28_export_acl_guard import (  # noqa: E402
    AclEntry,
    AclSnapshot,
    AclVerification,
    evaluate_acl,
    parse_getfacl_output,
    parse_windows_acl_json,
    verify_restricted_dir_acl,
)

AUTH_SID = "S-1-5-21-1-2-3-1001"
AUTH_NAME = "DOMAIN\\owner"
AUTH_UID = 1000


def _entry(
    sid: str | None,
    name: str | None,
    type_: str = "Allow",
    rights: str = "FullControl",
    inherited: bool = False,
) -> AclEntry:
    return AclEntry(
        principal_sid=sid,
        principal_name=name,
        access_type=type_.lower(),
        rights=rights,
        inherited=inherited,
        inheritance_flags="ContainerInherit, ObjectInherit" if inherited else "None",
        propagation_flags="None",
    )


def _win_snap(
    entries: list[AclEntry],
    *,
    owner_sid: str | None = AUTH_SID,
    owner_name: str | None = AUTH_NAME,
    protected: bool = False,
) -> AclSnapshot:
    return AclSnapshot(
        platform="windows",
        owner_sid=owner_sid,
        owner_name=owner_name,
        protected=protected,
        entries=tuple(entries),
    )


def _linux_snap(
    mode: int,
    uid: int,
    *,
    acl_text: str | None = None,
) -> AclSnapshot:
    return AclSnapshot(
        platform="linux",
        mode_octal=mode,
        uid=uid,
        gid=uid,
        linux_acl=parse_getfacl_output(acl_text),
        raw=acl_text,
    )


# ---------------------------------------------------------------------------
# Windows evaluator — allow rules (rule 4, 5, 6)
# ---------------------------------------------------------------------------


def test_windows_owner_only_allowed() -> None:
    snap = _win_snap([_entry(AUTH_SID, AUTH_NAME)])
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert verdict.allowed


def test_windows_system_admin_owner_allowed() -> None:
    snap = _win_snap(
        [
            _entry("S-1-5-18", "NT AUTHORITY\\SYSTEM"),
            _entry("S-1-5-32-544", "BUILTIN\\Administrators"),
            _entry(AUTH_SID, AUTH_NAME),
        ]
    )
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert verdict.allowed


def test_windows_owner_only_not_inherited_allowed() -> None:
    snap = _win_snap([_entry(AUTH_SID, AUTH_NAME, inherited=False)])
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert verdict.allowed


# ---------------------------------------------------------------------------
# Windows evaluator — public principals rejected (rule 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sid", "name", "rights"),
    [
        ("S-1-1-0", "Everyone", "Read"),
        ("S-1-5-11", "NT AUTHORITY\\Authenticated Users", "Modify, Synchronize"),
        ("S-1-5-32-545", "BUILTIN\\Users", "ReadAndExecute, Synchronize"),
        ("S-1-5-4", "NT AUTHORITY\\INTERACTIVE", "ReadAndExecute"),
        ("S-1-5-32-547", "BUILTIN\\Power Users", "Modify"),
    ],
)
def test_windows_public_principal_rejected(sid: str, name: str, rights: str) -> None:
    snap = _win_snap([_entry(AUTH_SID, AUTH_NAME), _entry(sid, name, rights=rights)])
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed
    assert "public" in verdict.reason.lower()


def test_windows_everyone_allow_rejected() -> None:
    snap = _win_snap([_entry(AUTH_SID, AUTH_NAME), _entry("S-1-1-0", "Everyone")])
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed
    assert "public" in verdict.reason.lower()


# ---------------------------------------------------------------------------
# Windows evaluator — unauthorized principals (rule 5) & owner (rule 4)
# ---------------------------------------------------------------------------


def test_windows_unauthorized_user_allow_rejected() -> None:
    snap = _win_snap(
        [
            _entry(AUTH_SID, AUTH_NAME),
            _entry("S-1-5-21-9-9-9-999", "DOMAIN\\bob", rights="Modify"),
        ]
    )
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed
    assert "unauthorized" in verdict.reason.lower()


def test_windows_owner_mismatch_rejected() -> None:
    snap = _win_snap(
        [_entry("S-1-5-21-7-7-7-777", "DOMAIN\\stranger")],
        owner_sid="S-1-5-21-7-7-7-777",
        owner_name="DOMAIN\\stranger",
    )
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed
    assert "owner" in verdict.reason.lower()


def test_windows_system_owned_dir_allowed() -> None:
    # Owner = SYSTEM (controlled) is acceptable; the executing account still
    # needs a controlled/authorized allow-ACE.
    snap = _win_snap(
        [_entry("S-1-5-18", "NT AUTHORITY\\SYSTEM")],
        owner_sid="S-1-5-18",
        owner_name="NT AUTHORITY\\SYSTEM",
    )
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert verdict.allowed


def test_windows_owner_unreadable_fails_closed() -> None:
    snap = AclSnapshot(
        platform="windows",
        owner_sid=None,
        owner_name=None,
        protected=False,
        entries=(_entry(AUTH_SID, AUTH_NAME),),
    )
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed


def test_windows_no_entries_fails_closed() -> None:
    snap = _win_snap([])
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed


def test_windows_authorized_deny_rejected() -> None:
    snap = _win_snap(
        [_entry(AUTH_SID, AUTH_NAME, type_="Deny", rights="FullControl")],
        owner_sid=AUTH_SID,
    )
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID, authorized_name=AUTH_NAME)
    assert not verdict.allowed
    assert "denied" in verdict.reason.lower()


# ---------------------------------------------------------------------------
# Windows parser
# ---------------------------------------------------------------------------


def test_parse_windows_acl_json_roundtrip() -> None:
    text = (
        '{"owner":"DOMAIN\\\\owner","ownerSid":"S-1-5-21-1-2-3-1001",'
        '"protected":false,"entries":['
        '{"sid":"S-1-5-18","name":"NT AUTHORITY\\\\SYSTEM","type":"Allow",'
        '"rights":"FullControl","inherited":true,'
        '"inheritance":"ContainerInherit, ObjectInherit","propagation":"None"}]}'
    )
    snap = parse_windows_acl_json(text)
    assert snap.platform == "windows"
    assert snap.owner_sid == "S-1-5-21-1-2-3-1001"
    assert snap.owner_name == "DOMAIN\\owner"
    assert snap.protected is False
    assert len(snap.entries) == 1
    entry = snap.entries[0]
    assert entry.principal_sid == "S-1-5-18"
    assert entry.access_type == "allow"
    assert entry.rights == "FullControl"
    assert entry.inherited is True


def test_parse_windows_acl_json_empty_entries() -> None:
    snap = parse_windows_acl_json(
        '{"owner":"X","ownerSid":"S-1","protected":true,"entries":[]}'
    )
    assert snap.entries == ()
    assert snap.protected is True


def test_parse_windows_acl_json_malformed_fails_closed() -> None:
    snap = parse_windows_acl_json("not json at all")
    assert snap.entries == ()
    assert snap.owner_sid is None


# ---------------------------------------------------------------------------
# Linux evaluator — mode + owner (rule 2, 4)
# ---------------------------------------------------------------------------


def test_linux_owner_only_0700_allowed() -> None:
    verdict = evaluate_acl(
        _linux_snap(0o700, AUTH_UID), authorized_uid=AUTH_UID, kind="dir"
    )
    assert verdict.allowed


def test_linux_file_0600_allowed() -> None:
    verdict = evaluate_acl(
        _linux_snap(0o600, AUTH_UID), authorized_uid=AUTH_UID, kind="file"
    )
    assert verdict.allowed


def test_linux_0755_rejected() -> None:
    verdict = evaluate_acl(
        _linux_snap(0o755, AUTH_UID), authorized_uid=AUTH_UID, kind="dir"
    )
    assert not verdict.allowed
    assert "mode" in verdict.reason.lower()


def test_linux_file_0644_rejected() -> None:
    verdict = evaluate_acl(
        _linux_snap(0o644, AUTH_UID), authorized_uid=AUTH_UID, kind="file"
    )
    assert not verdict.allowed
    assert "mode" in verdict.reason.lower()


def test_linux_wrong_owner_rejected() -> None:
    verdict = evaluate_acl(
        _linux_snap(0o700, AUTH_UID), authorized_uid=2000, kind="dir"
    )
    assert not verdict.allowed
    assert "owner" in verdict.reason.lower()


def test_linux_mode_unreadable_fails_closed() -> None:
    snap = AclSnapshot(platform="linux", mode_octal=None, uid=None, gid=None)
    verdict = evaluate_acl(snap, authorized_uid=AUTH_UID, kind="dir")
    assert not verdict.allowed


# ---------------------------------------------------------------------------
# Linux extended ACL widening (rule 2) + getfacl parser
# ---------------------------------------------------------------------------


def test_linux_getfacl_named_user_widening_rejected() -> None:
    acl = "user::rwx\nuser:bob:r--\ngroup::---\nmask::r--\nother::---\n"
    verdict = evaluate_acl(
        _linux_snap(0o700, AUTH_UID, acl_text=acl), authorized_uid=AUTH_UID, kind="dir"
    )
    assert not verdict.allowed
    assert "widens" in verdict.reason.lower()


def test_linux_getfacl_other_widening_rejected() -> None:
    acl = "user::rwx\ngroup::---\nother::r-x\n"
    verdict = evaluate_acl(
        _linux_snap(0o705, AUTH_UID, acl_text=acl), authorized_uid=AUTH_UID, kind="dir"
    )
    assert not verdict.allowed


def test_linux_getfacl_no_widening_0700_allowed() -> None:
    acl = "user::rwx\ngroup::---\nother::---\n"
    verdict = evaluate_acl(
        _linux_snap(0o700, AUTH_UID, acl_text=acl), authorized_uid=AUTH_UID, kind="dir"
    )
    assert verdict.allowed


def test_parse_getfacl_output_named_entries() -> None:
    acl = parse_getfacl_output(
        "user::rwx\nuser:bob:r--\ngroup::---\ngroup:dev:rwx\nmask::r-x\nother::---\n"
    )
    assert acl.owner == "rwx"
    assert acl.owning_group == "---"
    assert acl.mask == "r-x"
    assert acl.other == "---"
    assert ("bob", "r--") in acl.named_users
    assert ("dev", "rwx") in acl.named_groups


def test_parse_getfacl_output_empty() -> None:
    assert parse_getfacl_output(None).named_users == ()
    assert parse_getfacl_output("").other is None


# ---------------------------------------------------------------------------
# Dispatcher — unsupported platform fails closed (rule 7)
# ---------------------------------------------------------------------------


def test_unsupported_platform_fails_closed() -> None:
    snap = AclSnapshot(platform="plan9", owner_sid="S-1")
    verdict = evaluate_acl(snap, authorized_sid=AUTH_SID)
    assert not verdict.allowed


# ---------------------------------------------------------------------------
# Live reader smoke tests (do not modify anything)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="Windows-only live DACL reader")
def test_windows_live_reader_returns_wellformed_verdict(tmp_path: Path) -> None:
    verdict = verify_restricted_dir_acl(tmp_path, kind="dir")
    assert isinstance(verdict, AclVerification)
    assert verdict.platform == "windows"
    assert isinstance(verdict.allowed, bool)
    assert verdict.owner  # owner resolved from the real DACL
    assert verdict.details.get("entry_count", 0) > 0  # real ACEs enumerated
    # The verdict value is machine-dependent (a provisioning-protected temp dir
    # is allowed; a broad inherited temp dir is rejected). The fail-closed
    # logic itself is covered by the pure tests above; here we only prove the
    # live reader produces a real, structured verdict without modifying ACLs.


@pytest.mark.skipif(os.name != "nt", reason="Windows-only live DACL reader")
def test_windows_live_reader_detects_real_dacl(tmp_path: Path) -> None:
    verdict = verify_restricted_dir_acl(tmp_path, kind="dir")
    assert verdict.details.get("entry_count", 0) > 0  # real ACEs were enumerated
