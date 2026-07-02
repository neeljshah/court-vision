"""Versioned calibration-artifact registry with an atomic CURRENT pointer.

The store the self-improvement ratchet writes to when (and only when) a
recalibration has earned a SHIP. Layout, per kind:

    data/frontend/calib/<kind>/v<N>.json     immutable versioned artifacts
    data/frontend/calib/<kind>/CURRENT.json  pointer -> {"version": N}

Invariants this module enforces:
- save_version is append-only: it never overwrites an existing v<N>.json and it
  assigns the next monotone version itself.
- promote ATOMICALLY swaps CURRENT (temp file + os.replace) and ONLY when
  integrity_ok passes -- a feature-width mismatch BLOCKS promotion. os.replace is
  atomic on POSIX and Windows, so a torn/partial swap can never leave CURRENT
  dangling; the writer either sees the old pointer or the new one, never half.
- current() degrades to None (NEVER raises) on a missing/torn/garbage pointer,
  so a half-written CURRENT can't take the live path down.
- rollback re-promotes the previous distinct version (also integrity-gated).

stdlib-only (json + os + pathlib). Sport-blind. No dollar/edge field anywhere.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import List, Optional

try:  # package import
    from improve.calib_artifact import CalibArtifact, integrity_ok
except ImportError:  # direct-script / sys.path-injected (per-file test) fallback
    from calib_artifact import CalibArtifact, integrity_ok

_REPO = pathlib.Path(__file__).resolve().parents[1]
_DEFAULT_ROOT = _REPO / "data" / "frontend" / "calib"
_VER_RE = re.compile(r"^v(\d+)\.json$")


def _kind_dir(kind: str, root: Optional[str]) -> pathlib.Path:
    if not kind or "/" in kind or "\\" in kind or kind in (".", ".."):
        raise ValueError("invalid kind: %r" % (kind,))
    base = pathlib.Path(root) if root else _DEFAULT_ROOT
    d = base / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pointer_path(kind: str, root: Optional[str]) -> pathlib.Path:
    return _kind_dir(kind, root) / "CURRENT.json"


def _version_path(kind: str, version: int, root: Optional[str]) -> pathlib.Path:
    return _kind_dir(kind, root) / ("v%d.json" % version)


def list_versions(kind: str, root: Optional[str] = None) -> List[int]:
    """Ascending list of version ints that have a v<N>.json on disk."""
    out: List[int] = []
    for p in _kind_dir(kind, root).iterdir():
        m = _VER_RE.match(p.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def _next_version(kind: str, root: Optional[str]) -> int:
    versions = list_versions(kind, root)
    return (versions[-1] + 1) if versions else 1


def _atomic_write_json(path: pathlib.Path, payload: str) -> None:
    """Write payload to path via temp + fsync + os.replace (never torn)."""
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)  # atomic on POSIX + Windows


def save_version(artifact: CalibArtifact,
                 root: Optional[str] = None) -> pathlib.Path:
    """Append-only write of a versioned artifact.

    The registry assigns the next monotone version (the caller's
    artifact.version is informational); refuses to clobber an existing v<N>.json.
    Does NOT touch CURRENT -- saving and promoting are separate steps so a freshly
    fitted candidate can be inspected before it ever goes live.
    """
    if not isinstance(artifact, CalibArtifact):
        raise TypeError("save_version expects a CalibArtifact")
    version = _next_version(artifact.kind, root)
    stamped = CalibArtifact(
        version=version,
        created_at=artifact.created_at or datetime.now(timezone.utc).isoformat(),
        kind=artifact.kind,
        n_features_in=artifact.n_features_in,
        params=artifact.params,
        meta=artifact.meta,
        schema_version=artifact.schema_version,
    )
    path = _version_path(artifact.kind, version, root)
    if path.exists():  # paranoia: never overwrite history
        raise FileExistsError("version already exists: %s" % path)
    _atomic_write_json(path, stamped.to_json())
    return path


def load_version(kind: str, version: int,
                 root: Optional[str] = None) -> Optional[CalibArtifact]:
    """Load one versioned artifact, or None if absent/corrupt."""
    path = _version_path(kind, version, root)
    if not path.exists():
        return None
    try:
        return CalibArtifact.from_json(path.read_text(encoding="ascii"))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _read_pointer(kind: str, root: Optional[str]) -> Optional[int]:
    """Return the version int the CURRENT pointer names, or None if unreadable.

    Tolerant by design: a missing, torn, or non-JSON pointer yields None rather
    than raising, so the live path degrades gracefully past a half-written swap.
    """
    path = _pointer_path(kind, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="ascii"))
        return int(data["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current(kind: str, root: Optional[str] = None) -> Optional[CalibArtifact]:
    """The CURRENT artifact for kind, or None. NEVER raises.

    A torn pointer, a pointer to a deleted/corrupt version, or an integrity
    failure all collapse to None -- the live reader sees "no current calibrator"
    and falls back, rather than crashing on a half-applied swap.
    """
    version = _read_pointer(kind, root)
    if version is None:
        return None
    art = load_version(kind, version, root)
    if art is None or not integrity_ok(art):
        return None
    return art


def promote(kind: str, version: int,
            root: Optional[str] = None) -> bool:
    """Atomically swap CURRENT to ``version`` iff that artifact is integrity-ok.

    Returns True on a successful swap, False if the version is missing or FAILS
    the integrity check (n_features_in mismatch is the canonical block). The swap
    is temp+os.replace, so an interrupted promote leaves the prior CURRENT intact.
    """
    art = load_version(kind, version, root)
    if art is None:
        return False
    if not integrity_ok(art):
        return False
    payload = json.dumps({"version": version}, sort_keys=True)
    _atomic_write_json(_pointer_path(kind, root), payload)
    return True


def rollback(kind: str, root: Optional[str] = None) -> Optional[int]:
    """Re-promote the previous distinct version below CURRENT.

    Returns the version now live, or None if there is no earlier valid version to
    fall back to (CURRENT is left untouched in that case). The target must also
    pass integrity_ok, so rollback can never make a parity-broken artifact live.
    """
    cur = _read_pointer(kind, root)
    versions = list_versions(kind, root)
    candidates = [v for v in versions if cur is None or v < cur]
    for v in reversed(candidates):
        if promote(kind, v, root):
            return v
    return None
