"""ops.liveness -- heartbeat write/read + liveness snapshot.

Tracks process liveness via lightweight heartbeat files. Compatible with the
existing daemon_registry.json heartbeat conventions (plain ISO timestamp text
for daemon_heartbeats/*.txt; JSON for predict_service and ingame).

Public API
----------
heartbeat(component, *, path=None)
    Write a fresh UTC ISO timestamp to the component's heartbeat file.
    Path defaults to data/cache/daemon_heartbeats/<component>.txt.
    Atomic (tmp + os.replace). Never raises.

is_live(component, *, max_age_sec, now=None, path=None) -> bool
    True iff the heartbeat file exists and its mtime (or embedded ts) is
    within max_age_sec of now.  Never raises (returns False on any error).

liveness_snapshot(*, now=None) -> dict[str, dict]
    Returns {component: {live, age_sec}} for every known component,
    using the heartbeat paths declared in daemon_registry.json plus the
    two well-known frontend heartbeats.  Never raises.

Per-file test:
    python -m pytest tests/ops/test_liveness.py -q
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

# ---------------------------------------------------------------------------
# Repo root + well-known paths
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[2]


_REPO_ROOT: Path = _find_repo_root()
_DAEMON_HB_DIR: Path = _REPO_ROOT / "data" / "cache" / "daemon_heartbeats"
_REGISTRY_PATH: Path = _REPO_ROOT / "scripts" / "daemon_registry.json"

# Well-known frontend heartbeats (written by predict_service.scheduler and
# scripts.platformkit.ingame.live_loop respectively).
_FRONTEND_HEARTBEATS: Dict[str, Path] = {
    "predict_service_scheduler": _REPO_ROOT / "data" / "frontend" / "predict_service" / "_heartbeat.json",
    "ingame_live_loop": _REPO_ROOT / "data" / "frontend" / "ingame" / "_heartbeat.json",
}

# These JSON heartbeats store a "ts" key (epoch float) in addition to mtime.
_JSON_HB_NAMES = frozenset(_FRONTEND_HEARTBEATS.keys())

# Per-component liveness windows (seconds) for the frontend heartbeats. These
# must be wider than the daemon's own IDLE poll cadence so an honestly-idle loop
# (e.g. NBA offseason: live_loop beats every IDLE_INTERVAL_SEC=120s; the
# predict_service scheduler's slowest enabled cadence is soccer=1200s) is not
# read as a false DOWN. They stay finite, so a genuinely CRASHED daemon whose
# beat ages well past the window still reads NOT live -> DOWN downstream.
_FRONTEND_LIVE_WINDOW: Dict[str, float] = {
    "predict_service_scheduler": 2700.0,  # ~45 min -- >2x slowest scheduler cadence
    "ingame_live_loop": 300.0,            #  5 min -- >2x live_loop IDLE cadence
}
_FRONTEND_LIVE_WINDOW_DEFAULT: float = 300.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_hb_path(component: str) -> Path:
    return _DAEMON_HB_DIR / f"{component}.txt"


def _parse_ts_from_text(text: str) -> Optional[float]:
    """Parse an ISO-8601 UTC timestamp string to epoch float. Returns None on failure."""
    s = text.strip()
    if not s:
        return None
    try:
        return float(s)  # plain numeric epoch
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _age_of_path(path: Path, now: float) -> Optional[float]:
    """Return age in seconds from path mtime, or None if path missing/error."""
    try:
        mtime = os.path.getmtime(str(path))
        return now - mtime
    except OSError:
        return None


def _age_from_text_hb(path: Path, now: float) -> Optional[float]:
    """Read a plain-text ISO heartbeat and compute age from the embedded ts.

    Falls back to mtime if the text cannot be parsed (e.g. empty file).
    This is required so injected fake clocks work correctly in tests --
    mtime is always real wall-clock time even if the content was written
    with a fake timestamp.
    """
    try:
        raw = path.read_text(encoding="ascii", errors="replace").strip()
        ts = _parse_ts_from_text(raw)
        if ts is not None:
            return now - ts
    except OSError:
        return None
    except Exception:  # noqa: BLE001
        pass
    return _age_of_path(path, now)


def _age_from_json_hb(path: Path, now: float) -> Optional[float]:
    """Try to read a JSON heartbeat's ts field; fall back to mtime."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and "ts" in data:
            return now - float(data["ts"])
    except Exception:  # noqa: BLE001
        pass
    return _age_of_path(path, now)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def heartbeat(
    component: str,
    *,
    path: Optional[Union[str, Path]] = None,
    _now: Optional[float] = None,
) -> None:
    """Write a fresh UTC ISO timestamp to the component heartbeat file.

    Uses an atomic tmp+replace so readers never see a partial write.
    Never raises.
    """
    try:
        hb_path = Path(path) if path is not None else _default_hb_path(component)
        hb_path.parent.mkdir(parents=True, exist_ok=True)
        ts = _now if _now is not None else time.time()
        content = _utc_iso(ts)
        tmp = hb_path.with_suffix(hb_path.suffix + ".tmp")
        tmp.write_text(content, encoding="ascii")
        os.replace(str(tmp), str(hb_path))
    except Exception:  # noqa: BLE001 -- heartbeat write must not crash callers
        pass


def is_live(
    component: str,
    *,
    max_age_sec: float,
    now: Optional[float] = None,
    path: Optional[Union[str, Path]] = None,
) -> bool:
    """Return True iff the component's heartbeat is fresh within max_age_sec.

    Resolves path from: explicit path arg -> well-known frontend map ->
    default daemon_heartbeats/<component>.txt.  Never raises (returns False
    on any error or missing file).
    """
    try:
        _now = float(now) if now is not None else time.time()
        if path is not None:
            hb_path = Path(path)
        elif component in _FRONTEND_HEARTBEATS:
            hb_path = _FRONTEND_HEARTBEATS[component]
        else:
            hb_path = _default_hb_path(component)
        if not hb_path.exists():
            return False
        if component in _JSON_HB_NAMES or hb_path.suffix == ".json":
            age = _age_from_json_hb(hb_path, _now)
        else:
            age = _age_from_text_hb(hb_path, _now)
        if age is None:
            return False
        return age <= max_age_sec
    except Exception:  # noqa: BLE001
        return False


def liveness_snapshot(
    *,
    now: Optional[float] = None,
    _registry_path: Optional[Union[str, Path]] = None,
    _hb_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Return {component: {live, age_sec}} for every known component.

    Sources (in order, merged):
    1. Well-known frontend heartbeats (predict_service_scheduler, ingame_live_loop).
    2. Daemon registry heartbeat_file paths from daemon_registry.json.

    age_sec is None when the file is absent or unreadable.
    Never raises.
    """
    _now = float(now) if now is not None else time.time()
    reg_path = Path(_registry_path) if _registry_path is not None else _REGISTRY_PATH
    hb_base = Path(_hb_dir) if _hb_dir is not None else _DAEMON_HB_DIR

    result: Dict[str, Any] = {}

    # 1. Frontend heartbeats. Each uses a per-component window wide enough to
    # cover the daemon's own IDLE poll cadence (so an idle loop is not a false
    # DOWN) yet finite (so a crashed daemon still ages out to NOT live).
    for comp, hb_path in _FRONTEND_HEARTBEATS.items():
        age = _age_from_json_hb(hb_path, _now) if hb_path.exists() else None
        window = _FRONTEND_LIVE_WINDOW.get(comp, _FRONTEND_LIVE_WINDOW_DEFAULT)
        result[comp] = {
            "live": (age is not None and age <= window),
            "age_sec": round(age, 1) if age is not None else None,
            "path": str(hb_path),
        }

    # 2. Daemon registry
    try:
        raw = reg_path.read_text(encoding="utf-8")
        registry = json.loads(raw)
        daemons = registry.get("daemons", []) if isinstance(registry, dict) else []
        for entry in daemons:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "")
            hb_file = entry.get("heartbeat_file", "")
            expected = entry.get("expected_interval_sec", 60)
            if not name or not hb_file:
                continue
            hb_path = (
                hb_base / Path(hb_file).name
                if not Path(hb_file).is_absolute()
                else Path(hb_file)
            )
            # Prefer paths relative to repo root if they don't start with data/cache/daemon
            repo_rel = _REPO_ROOT / hb_file
            if repo_rel.exists():
                hb_path = repo_rel
            suffix = hb_path.suffix
            if suffix == ".json":
                age = _age_from_json_hb(hb_path, _now) if hb_path.exists() else None
            else:
                age = _age_from_text_hb(hb_path, _now) if hb_path.exists() else None
            max_age = float(expected) * 3.0
            # For the well-known frontend loops the registry's expected_interval
            # is the BUSY (live-game) cadence; an honestly-idle loop beats far
            # slower. Floor the window at the per-component idle window so an
            # idle loop is not a false DOWN. Still finite -> a crashed loop ages
            # out past the window and reads NOT live -> DOWN.
            if name in _FRONTEND_LIVE_WINDOW:
                max_age = max(max_age, _FRONTEND_LIVE_WINDOW[name])
            result[name] = {
                "live": (age is not None and age <= max_age),
                "age_sec": round(age, 1) if age is not None else None,
                "path": str(hb_path),
            }
    except Exception:  # noqa: BLE001 -- a bad registry must not crash the snapshot
        pass

    return result


__all__ = ["heartbeat", "is_live", "liveness_snapshot"]
