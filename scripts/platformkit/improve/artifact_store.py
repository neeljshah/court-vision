"""scripts.platformkit.improve.artifact_store -- versioned artifact store with an
atomically-swapped `current` pointer, prev-N retention, rollback + auto-rollback.

The daemon stages a freshly-recalibrated candidate as an immutable version, then
ATOMICALLY swaps the live `current` pointer to it (temp file + os.replace, which is
atomic on POSIX and Windows -- a reader sees the old or the new pointer, never half).
If the new version later REGRESSES a held-out check, auto_rollback re-promotes the
previous version and logs the event, so a bad artifact can never stay live.

Layout, per artifact name:
    <root>/<name>/v0001.json , v0002.json , ...   immutable versioned artifacts
    <root>/<name>/current.json                     pointer -> {"version": N}
    <root>/<name>/rollback_log.jsonl               append-only rollback audit

Default root: data/cache/improve/artifacts/ . NEVER data/registry/ . stdlib only,
sport-blind, no dollar/edge field anywhere. ASCII only; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_REPO = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_ROOT = _REPO / "data" / "cache" / "improve" / "artifacts"
_VER_RE = re.compile(r"^v(\d+)\.json$")
_KEEP_PREV = 10  # retain this many trailing versions; older ones are pruned


def _name_dir(name: str, root: Optional[str]) -> pathlib.Path:
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("invalid artifact name: %r" % (name,))
    base = pathlib.Path(root) if root else DEFAULT_ROOT
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: pathlib.Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp.%d" % os.getpid())
    with open(tmp, "w", encoding="ascii") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)  # atomic on POSIX + Windows


def list_versions(name: str, root: Optional[str] = None) -> List[int]:
    """Ascending list of version ints present on disk for `name`."""
    out: List[int] = []
    for p in _name_dir(name, root).iterdir():
        m = _VER_RE.match(p.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def _next_version(name: str, root: Optional[str]) -> int:
    vs = list_versions(name, root)
    return (vs[-1] + 1) if vs else 1


def _version_path(name: str, version: int, root: Optional[str]) -> pathlib.Path:
    return _name_dir(name, root) / ("v%04d.json" % version)


def _pointer_path(name: str, root: Optional[str]) -> pathlib.Path:
    return _name_dir(name, root) / "current.json"


def _prune(name: str, root: Optional[str], keep: int) -> None:
    """Drop the oldest versions beyond `keep`, never the live one."""
    vs = list_versions(name, root)
    if len(vs) <= keep:
        return
    live = read_pointer(name, root)
    for v in vs[:-keep]:
        if v == live:
            continue
        try:
            _version_path(name, v, root).unlink()
        except OSError:
            pass


def stage_version(name: str, payload: Dict[str, Any],
                  root: Optional[str] = None, keep: int = _KEEP_PREV) -> int:
    """Append-only write of a new immutable version; returns its version int.

    Does NOT touch `current` -- staging and swapping are separate so a candidate
    can be inspected before going live. The registry assigns the monotone version.
    """
    version = _next_version(name, root)
    record = {
        "version": version,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    path = _version_path(name, version, root)
    if path.exists():  # never clobber history
        raise FileExistsError("version already exists: %s" % path)
    _atomic_write(path, json.dumps(record, sort_keys=True, indent=2))
    _prune(name, root, keep)
    return version


def load_version(name: str, version: int,
                 root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load one versioned record, or None if absent/corrupt."""
    path = _version_path(name, version, root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None


def read_pointer(name: str, root: Optional[str] = None) -> Optional[int]:
    """Version int the `current` pointer names, or None (NEVER raises)."""
    path = _pointer_path(name, root)
    if not path.exists():
        return None
    try:
        return int(json.loads(path.read_text(encoding="ascii"))["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def current(name: str, root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The live record for `name`, or None on a torn/dangling pointer."""
    v = read_pointer(name, root)
    if v is None:
        return None
    return load_version(name, v, root)


def swap_current(name: str, version: int, root: Optional[str] = None) -> bool:
    """Atomically swap `current` to `version` iff that version exists on disk.

    temp+os.replace, so an interrupted swap leaves the prior `current` intact.
    """
    if load_version(name, version, root) is None:
        return False
    _atomic_write(_pointer_path(name, root),
                  json.dumps({"version": version}, sort_keys=True))
    return True


def _log_rollback(name: str, root: Optional[str], rec: Dict[str, Any]) -> None:
    path = _name_dir(name, root) / "rollback_log.jsonl"
    with open(path, "a", encoding="ascii") as fh:
        fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")


def rollback(name: str, root: Optional[str] = None,
             reason: str = "manual") -> Optional[int]:
    """Re-promote the previous distinct version below `current`; log it.

    Returns the version now live, or None if there is no earlier version (current
    is then left untouched). Append-only audit row written either way.
    """
    cur = read_pointer(name, root)
    vs = list_versions(name, root)
    candidates = [v for v in vs if cur is None or v < cur]
    target = candidates[-1] if candidates else None
    if target is None:
        _log_rollback(name, root, {"ts": time.time(), "from": cur, "to": None,
                                   "reason": reason, "ok": False})
        return None
    swap_current(name, target, root)
    _log_rollback(name, root, {"ts": time.time(), "from": cur, "to": target,
                               "reason": reason, "ok": True})
    return target


def auto_rollback_if_regressed(name: str, check_fn, root: Optional[str] = None,
                               ) -> Dict[str, Any]:
    """Run `check_fn(current_record) -> bool` (True == regressed) on the live
    artifact; if it regressed, roll back to the previous version and log it.

    check_fn must not raise; if it does we treat it as a regression (fail-safe to
    the prior version). Returns {regressed, rolled_to, live_version}.
    """
    live = read_pointer(name, root)
    rec = current(name, root)
    try:
        regressed = bool(check_fn(rec))
    except Exception as exc:  # noqa: BLE001 -- fail safe: treat as regression
        regressed = True
        _log_rollback(name, root, {"ts": time.time(), "from": live,
                                   "reason": "check_fn raised: %s" % exc,
                                   "ok": False})
    if not regressed:
        return {"regressed": False, "rolled_to": None, "live_version": live}
    rolled_to = rollback(name, root, reason="auto: held-out regression")
    return {"regressed": True, "rolled_to": rolled_to, "live_version": rolled_to}


__all__ = [
    "DEFAULT_ROOT", "list_versions", "stage_version", "load_version",
    "read_pointer", "current", "swap_current", "rollback",
    "auto_rollback_if_regressed",
]
