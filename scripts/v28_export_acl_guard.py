"""G3 cross-platform ACL guard (read + verify only, fail-closed).

Implements the Owner-authorized G3 security hardening (2026-11-24,
「Nuotao V2.8 EXPORT G3 运行环境验收决定」). This module provides the real
ACL verification that the export pipeline needs before it may trust (and
write to) an Owner-controlled restricted directory:

* Windows: reads the REAL NTFS DACL via ``Get-Acl`` (SIDs, access type,
  rights, inheritance) — it never infers protection from the POSIX mode bit
  or from a successful ``os.chmod`` call.
* Linux: verifies the REAL mode + owner (``lstat``) and checks for extended
  ACLs (``getfacl``) that would widen access beyond the owner.
* Unsafe inherited permissions are rejected (rule 3).
* The executing account must be an authorized account — the directory owner
  or a controlled system/admin principal (rule 4 + rule 6).
* Broad public principals (Everyone, Users, Authenticated Users,
  INTERACTIVE, Network, Power Users) with ANY access are rejected (rule 5).
* Controlled principals (SYSTEM, BUILTIN\\Administrators, Creator Owner,
  Owner Rights) are recognized and are NOT misjudged as public access (rule 6).
* Any failure to read or confirm the effective ACL fails closed:
  ``AclVerification.allowed`` is ``False`` (rule 7).

This module NEVER modifies filesystem permissions: it performs no chmod,
chown, setfacl or icacls. The Owner / system administrator provisions the
restricted directory and its ACL beforehand; this module only READS and
VERIFIES the actual DACL/ACL. The pipeline decides whether to act on the
verdict (fail-closed when ``allowed`` is ``False``).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Well-known principals
# ---------------------------------------------------------------------------
#: Broad / public principals. An ALLOW access ACE for any of these on the
#: restricted path is a hard rejection (Owner rule 5).
PUBLIC_SIDS: frozenset[str] = frozenset(
    {
        "S-1-1-0",  # Everyone
        "S-1-5-11",  # Authenticated Users
        "S-1-5-32-545",  # BUILTIN\Users
        "S-1-5-4",  # INTERACTIVE
        "S-1-5-2",  # NETWORK
        "S-1-5-32-547",  # Power Users (legacy broad)
    }
)
PUBLIC_NAMES: frozenset[str] = frozenset(
    {
        "everyone",
        "authenticated users",
        "users",
        "power users",
        "nt authority\\everyone",
        "nt authority\\authenticated users",
        "nt authority\\interactive",
        "nt authority\\network",
        "builtin\\users",
        "builtin\\power users",
    }
)

#: Controlled principals (Owner rule 6): recognized as authorized system /
#: admin / owner-scoped subjects. NOT public. SYSTEM, Administrators,
#: Creator Owner (child objects) and Owner Rights (object owner).
CONTROLLED_SIDS: frozenset[str] = frozenset(
    {
        "S-1-5-18",  # NT AUTHORITY\SYSTEM
        "S-1-5-32-544",  # BUILTIN\Administrators
        "S-1-3-0",  # Creator Owner
        "S-1-3-4",  # Owner Rights
    }
)
CONTROLLED_NAMES: frozenset[str] = frozenset(
    {
        "nt authority\\system",
        "builtin\\administrators",
        "system",
        "administrators",
        "creator owner",
        "owner rights",
        "nt authority\\owner rights",
    }
)


@dataclass(frozen=True)
class AclEntry:
    """A single Windows NTFS access-control entry (ACE)."""

    principal_sid: str | None
    principal_name: str | None
    access_type: str  # "allow" | "deny"
    rights: str = ""
    inherited: bool = False
    inheritance_flags: str | None = None
    propagation_flags: str | None = None


@dataclass(frozen=True)
class LinuxAcl:
    """Parsed ``getfacl`` output for a POSIX object."""

    owner: str | None = None  # "rwx" etc. (owner base entry)
    named_users: tuple[tuple[str, str], ...] = ()
    owning_group: str | None = None
    named_groups: tuple[tuple[str, str], ...] = ()
    mask: str | None = None
    other: str | None = None


@dataclass(frozen=True)
class AclSnapshot:
    """A read-only snapshot of a path's effective ACL/权限."""

    platform: str  # "windows" | "linux"
    owner_sid: str | None = None
    owner_name: str | None = None
    protected: bool | None = None  # Windows: DACL is not inherited
    entries: tuple[AclEntry, ...] = ()
    mode_octal: int | None = None  # Linux only
    uid: int | None = None
    gid: int | None = None
    linux_acl: LinuxAcl | None = None
    raw: str | None = None  # raw source text for evidence


@dataclass
class AclVerification:
    """Fail-closed verdict from ``verify_restricted_dir_acl``."""

    allowed: bool
    platform: str
    reason: str
    owner: str | None
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "platform": self.platform,
            "reason": self.reason,
            "owner": self.owner,
            "details": self.details,
        }


def _verdict(
    allowed: bool,
    platform: str,
    snap: AclSnapshot | None,
    reason: str,
) -> AclVerification:
    return AclVerification(
        allowed=allowed,
        platform=platform,
        reason=reason,
        owner=(snap.owner_sid or snap.owner_name) if snap else None,
        details={
            "mode_octal": oct(snap.mode_octal)
            if snap and snap.mode_octal is not None
            else None,
            "entry_count": len(snap.entries) if snap else 0,
            "protected": snap.protected if snap else None,
            "uid": snap.uid if snap else None,
            "gid": snap.gid if snap else None,
        },
    )


def _name_matches(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    norm_a = a.strip().lower()
    norm_b = b.strip().lower()
    return norm_a == norm_b or norm_a.split("\\")[-1] == norm_b.split("\\")[-1]


# ---------------------------------------------------------------------------
# Pure parsers (fully unit-testable without a live OS)
# ---------------------------------------------------------------------------


def parse_windows_acl_json(text: str) -> AclSnapshot:
    """Parse the JSON emitted by the PowerShell ``Get-Acl`` reader.

    Returns an ``AclSnapshot`` with parsed ACEs. Any malformed input yields an
    empty snapshot (fail-closed downstream), never a raised exception.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return AclSnapshot(platform="windows", raw=text)
    entries: list[AclEntry] = []
    for e in data.get("entries") or []:
        if not isinstance(e, dict):
            continue
        entries.append(
            AclEntry(
                principal_sid=e.get("sid"),
                principal_name=e.get("name"),
                access_type=str(e.get("type") or "allow").lower(),
                rights=str(e.get("rights") or ""),
                inherited=bool(e.get("inherited")),
                inheritance_flags=e.get("inheritance"),
                propagation_flags=e.get("propagation"),
            )
        )
    return AclSnapshot(
        platform="windows",
        owner_sid=data.get("ownerSid"),
        owner_name=data.get("owner"),
        protected=data.get("protected"),
        entries=tuple(entries),
        raw=text,
    )


def parse_getfacl_output(text: str | None) -> LinuxAcl:
    """Parse ``getfacl`` output into a ``LinuxAcl`` (named entries, mask, other)."""
    if not text:
        return LinuxAcl()
    owner: str | None = None
    owning_group: str | None = None
    mask: str | None = None
    other: str | None = None
    named_users: list[tuple[str, str]] = []
    named_groups: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 3:
            continue
        kind, name, rights = parts[0], parts[1], parts[2]
        if kind == "user" and name == "":
            owner = rights
        elif kind == "user":
            named_users.append((name, rights))
        elif kind == "group" and name == "":
            owning_group = rights
        elif kind == "group":
            named_groups.append((name, rights))
        elif kind == "mask":
            mask = rights
        elif kind == "other":
            other = rights
    return LinuxAcl(
        owner=owner,
        named_users=tuple(named_users),
        owning_group=owning_group,
        named_groups=tuple(named_groups),
        mask=mask,
        other=other,
    )


# ---------------------------------------------------------------------------
# Pure evaluator (fail-closed rules 3-7)
# ---------------------------------------------------------------------------


def _linux_widening(snap: AclSnapshot) -> list[str]:
    """Named / mask / other ACL entries that could widen access.

    ``snap.linux_acl`` must be non-``None`` here: the caller
    (``_evaluate_linux``) rejects a ``None`` ACL (getfacl unavailable or
    unparseable) before widening is considered (Owner G3 final security gate
    directive V1.0, rule 5). When the ACL is present, any named user/group
    entry or a non-empty ``mask``/``other`` is reported as widening; the POSIX
    mode group/other bits are enforced separately (``0700``/``0600``).
    """
    acl = snap.linux_acl
    if acl is None:
        return ["getfacl-unavailable"]
    hits: list[str] = []
    if acl.other and acl.other != "---":
        hits.append(f"other::{acl.other}")
    if acl.mask and acl.mask != "---":
        hits.append(f"mask::{acl.mask}")
    for name, rights in acl.named_users:
        if rights != "---":
            hits.append(f"user:{name}:{rights}")
    for name, rights in acl.named_groups:
        if rights != "---":
            hits.append(f"group:{name}:{rights}")
    return hits


def _evaluate_windows(
    snap: AclSnapshot,
    *,
    authorized_sid: str | None,
    authorized_name: str | None,
) -> AclVerification:
    if not snap.owner_sid and not snap.owner_name:
        return _verdict(
            False, "windows", snap, "directory owner could not be read (fail-closed)"
        )
    owner_ok = False
    if snap.owner_sid:
        owner_ok = authorized_sid is not None and snap.owner_sid == authorized_sid
        if not owner_ok and snap.owner_sid in CONTROLLED_SIDS:
            owner_ok = True
    if not owner_ok and snap.owner_name:
        owner_ok = _name_matches(snap.owner_name, authorized_name)
    if not owner_ok:
        return _verdict(
            False,
            "windows",
            snap,
            f"directory owner {snap.owner_sid or snap.owner_name} is not an authorized account",
        )
    if not snap.entries:
        return _verdict(
            False, "windows", snap, "no readable DACL entries (fail-closed)"
        )
    public_hits: list[tuple[str | None, str]] = []
    unauthorized_hits: list[tuple[str | None, str]] = []
    unsafe_inherited: list[tuple[str | None, str]] = []
    deny_hits: list[tuple[str | None, str]] = []
    for e in snap.entries:
        sid = (e.principal_sid or "").lower()
        name = (e.principal_name or "").lower()
        is_public = sid in PUBLIC_SIDS or name in PUBLIC_NAMES
        is_controlled = sid in CONTROLLED_SIDS or name in CONTROLLED_NAMES
        is_authorized = bool(
            (authorized_sid and sid == authorized_sid)
            or (authorized_name and _name_matches(e.principal_name, authorized_name))
        )
        if e.access_type == "deny":
            # A deny ACE for the authorized account / a public group blocks it.
            if is_authorized or is_public:
                deny_hits.append((e.principal_name or e.principal_sid, e.rights))
            continue
        if is_public:
            public_hits.append((e.principal_name or e.principal_sid, e.rights))
        elif not (is_controlled or is_authorized):
            unauthorized_hits.append((e.principal_name or e.principal_sid, e.rights))
        if e.inherited and not (is_controlled or is_authorized):
            unsafe_inherited.append((e.principal_name or e.principal_sid, e.rights))
    if deny_hits:
        return _verdict(
            False, "windows", snap, f"authorized account is denied access: {deny_hits}"
        )
    if public_hits:
        return _verdict(
            False, "windows", snap, f"public principals have access: {public_hits}"
        )
    if unauthorized_hits:
        return _verdict(
            False,
            "windows",
            snap,
            f"unauthorized principals have access: {unauthorized_hits}",
        )
    if unsafe_inherited:
        return _verdict(
            False, "windows", snap, f"unsafe inherited permissions: {unsafe_inherited}"
        )
    return _verdict(True, "windows", snap, "ok")


def _evaluate_linux(
    snap: AclSnapshot,
    *,
    authorized_uid: int | None,
    expected_mode_octal: int | None,
    kind: str,
) -> AclVerification:
    if snap.mode_octal is None:
        return _verdict(
            False, "linux", snap, "POSIX mode could not be read (fail-closed)"
        )
    if snap.uid is None:
        return _verdict(
            False, "linux", snap, "owner uid could not be read (fail-closed)"
        )
    if authorized_uid is not None and snap.uid != authorized_uid:
        return _verdict(
            False,
            "linux",
            snap,
            f"owner uid {snap.uid} is not the authorized uid {authorized_uid}",
        )
    expected = (
        expected_mode_octal
        if expected_mode_octal is not None
        else (0o700 if kind == "dir" else 0o600)
    )
    if snap.mode_octal != expected:
        return _verdict(
            False,
            "linux",
            snap,
            f"mode {oct(snap.mode_octal)} is not the required {oct(expected)}",
        )
    # Owner G3 final security gate directive V1.0 (rule 5): if ``getfacl`` was
    # unavailable or its output could not be parsed, the presence of an
    # extended ACL cannot be confirmed -> fail closed. The POSIX mode alone is
    # not sufficient evidence that no named ACL/mask widens access.
    if snap.linux_acl is None:
        return _verdict(
            False,
            "linux",
            snap,
            "getfacl unavailable or ACL parse failed (fail-closed)",
        )
    widening = _linux_widening(snap)
    if widening:
        return _verdict(False, "linux", snap, f"extended ACL widens access: {widening}")
    return _verdict(True, "linux", snap, "ok")


def evaluate_acl(
    snapshot: AclSnapshot,
    *,
    kind: str = "dir",
    authorized_sid: str | None = None,
    authorized_name: str | None = None,
    authorized_uid: int | None = None,
    expected_mode_octal: int | None = None,
) -> AclVerification:
    """Evaluate a snapshot against the fail-closed G3 rules (pure)."""
    if snapshot.platform == "windows":
        return _evaluate_windows(
            snapshot,
            authorized_sid=authorized_sid,
            authorized_name=authorized_name,
        )
    if snapshot.platform == "linux":
        return _evaluate_linux(
            snapshot,
            authorized_uid=authorized_uid,
            expected_mode_octal=expected_mode_octal,
            kind=kind,
        )
    return _verdict(
        False,
        snapshot.platform or "unknown",
        snapshot,
        "unsupported platform (fail-closed)",
    )


# ---------------------------------------------------------------------------
# Live readers (thin; never modify permissions)
# ---------------------------------------------------------------------------


def _find_powershell() -> str | None:
    for name in ("powershell", "pwsh"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _current_identity() -> tuple[str | None, str | None]:
    """Return (sid, name) of the executing account, or (None, None)."""
    if os.name != "nt":
        return None, os.environ.get("USER") or os.environ.get("USERNAME")
    ps = _find_powershell()
    if not ps:
        return None, os.environ.get("USERNAME") or os.environ.get("USER")
    script = (
        "[pscustomobject]@{"
        "sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value;"
        "name=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name"
        "} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            return data.get("sid"), data.get("name")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None
    return None, None


def _read_windows_acl(path: Path) -> AclSnapshot:
    ps = _find_powershell()
    if not ps:
        return AclSnapshot(platform="windows", raw="no PowerShell available")
    quoted = str(path).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$acl = Get-Acl -LiteralPath '{quoted}';"
        "$ownerSid=$null;"
        "try { $ownerSid = ([System.Security.Principal.NTAccount]$acl.Owner)"
        ".Translate([System.Security.Principal.SecurityIdentifier]).Value } catch { $ownerSid=$null };"
        "$acc=@();"
        "foreach ($r in $acl.Access) {"
        "$sid=$null;"
        "try { $sid=$r.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }"
        "catch { $sid=$r.IdentityReference.Value };"
        "$acc += [pscustomobject]@{"
        "sid=$sid; name=$r.IdentityReference.Value; type=$r.AccessControlType.ToString();"
        "rights=$r.FileSystemRights.ToString(); inherited=[bool]$r.IsInherited;"
        "inheritance=$r.InheritanceFlags.ToString(); propagation=$r.PropagationFlags.ToString()"
        "} };"
        "[pscustomobject]@{ owner=$acl.Owner; ownerSid=$ownerSid;"
        "protected=[bool]$acl.AreAccessRulesProtected; entries=$acc }"
        "| ConvertTo-Json -Depth 5 -Compress"
    )
    try:
        result = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return AclSnapshot(platform="windows", raw=str(exc))
    if result.returncode == 0 and result.stdout.strip():
        return parse_windows_acl_json(result.stdout)
    return AclSnapshot(platform="windows", raw=result.stderr or result.stdout)


def _read_linux_acl(path: Path) -> AclSnapshot:
    try:
        st = os.lstat(str(path))
    except OSError as exc:
        return AclSnapshot(platform="linux", raw=str(exc))
    mode = stat.S_IMODE(st.st_mode)
    acl_text: str | None = None
    getfacl = shutil.which("getfacl")
    if getfacl:
        try:
            result = subprocess.run(
                [getfacl, "-p", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                acl_text = result.stdout
        except (OSError, subprocess.SubprocessError):
            acl_text = None
    return AclSnapshot(
        platform="linux",
        mode_octal=mode,
        uid=st.st_uid,
        gid=st.st_gid,
        linux_acl=parse_getfacl_output(acl_text) if acl_text else None,
        raw=acl_text,
    )


def verify_restricted_dir_acl(
    path: str | os.PathLike[str],
    *,
    kind: str = "dir",
    authorized_sid: str | None = None,
    authorized_name: str | None = None,
    authorized_uid: int | None = None,
    expected_mode_octal: int | None = None,
) -> AclVerification:
    """Read and verify the real ACL of ``path``; never modifies anything.

    Defaults the authorized account to the current executing account. Any
    read/parse failure yields ``allowed=False`` (fail-closed).
    """
    target = Path(path)
    if os.name == "nt":
        if authorized_sid is None or authorized_name is None:
            cur_sid, cur_name = _current_identity()
            authorized_sid = authorized_sid if authorized_sid is not None else cur_sid
            authorized_name = (
                authorized_name if authorized_name is not None else cur_name
            )
        snapshot = _read_windows_acl(target)
        return evaluate_acl(
            snapshot,
            kind=kind,
            authorized_sid=authorized_sid,
            authorized_name=authorized_name,
            expected_mode_octal=expected_mode_octal,
        )
    if os.name == "posix":
        if authorized_uid is None:
            try:
                authorized_uid = os.getuid()
            except (AttributeError, OSError):
                authorized_uid = None
        snapshot = _read_linux_acl(target)
        return evaluate_acl(
            snapshot,
            kind=kind,
            authorized_uid=authorized_uid,
            expected_mode_octal=expected_mode_octal,
        )
    return AclVerification(
        allowed=False,
        platform=os.name or "unknown",
        reason="unsupported platform (fail-closed)",
        owner=None,
    )


def __main__() -> int:
    """CLI smoke entry: verify one path and print the verdict (no changes)."""
    if len(sys.argv) < 2:
        print(
            "usage: python -m scripts.v28_export_acl_guard <path> [dir|file]",
            file=sys.stderr,
        )
        return 2
    kind = sys.argv[2] if len(sys.argv) > 2 else "dir"
    verdict = verify_restricted_dir_acl(sys.argv[1], kind=kind)
    print(json.dumps(verdict.to_json(), indent=2, ensure_ascii=False))
    return 0 if verdict.allowed else 1


if __name__ == "__main__":
    raise SystemExit(__main__())
