"""daemon_lag_histogram.py -- per-daemon staleness-fraction buckets (BE-R5-8).

Reads supervisor heartbeat files alongside each daemon's declared SLA (fresh_sec
from stack_specs ProcSpec) and produces:
  per_daemon  -- rows sorted worst-first
  buckets     -- {fresh, warn, stale} counts
  worst       -- stale daemon names (worst offenders)
  status      -- "ok" | "WARN" | "STALE" | "UNAVAILABLE"

Bucket definitions (stale-never-green):
  fresh  -- age_sec < SLA
  warn   -- SLA <= age_sec < 2*SLA
  stale  -- age_sec >= 2*SLA OR heartbeat absent/unreadable/null

INVARIANTS: no $ / roi / pnl / profit / edge field; never raises; no IO at import;
read-only on heartbeat files; stale-never-green enforced; ASCII; <=300 LOC.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

BUCKET_FRESH = "fresh"
BUCKET_WARN = "warn"
BUCKET_STALE = "stale"

STATUS_OK = "ok"
STATUS_WARN = "WARN"
STATUS_STALE = "STALE"
STATUS_UNAVAILABLE = "UNAVAILABLE"

_WARN_MULTIPLIER = 2.0

_HONEST_NOTE = (
    "BE-R5-8 daemon-lag histogram. "
    "fresh=age<SLA; warn=SLA<=age<2*SLA; stale=age>=2*SLA or absent/null. "
    "stale-never-green: missing heartbeat or null fresh -> stale bucket. "
    "CALIBRATION not edge; UNITS not $; no dollar P&L field."
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_HB_DIR = _REPO_ROOT / "data" / "cache" / "daemon_heartbeats"


# ---------------------------------------------------------------------------
# Heartbeat reading
# ---------------------------------------------------------------------------

def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_age(path: Path, now: float) -> Optional[float]:
    """Return age_sec for heartbeat at *path*, or None if absent/unreadable/corrupt.

    Handles: (1) plain ISO-8601 text, (2) JSON with updated_at epoch or as_of ISO.
    Corrupt/unrecognized content returns None (-> stale; stale-never-green).
    """
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not raw:
        return None

    stamp: Optional[float] = None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                val = data.get("updated_at")
                if isinstance(val, (int, float)):
                    stamp = float(val)
                elif isinstance(val, str):
                    dt = _parse_iso(val)
                    stamp = dt.timestamp() if dt else None
                if stamp is None:
                    ao = data.get("as_of")
                    if isinstance(ao, str):
                        dt = _parse_iso(ao)
                        stamp = dt.timestamp() if dt else None
        except (json.JSONDecodeError, ValueError):
            stamp = None
    if stamp is None:
        dt = _parse_iso(raw)
        if dt is not None:
            stamp = dt.timestamp()
    # Deliberately no mtime fallback: corrupt/unrecognized -> None -> stale.
    if stamp is None:
        return None
    return max(0.0, now - stamp)


def _assign_bucket(age: Optional[float], sla: float) -> str:
    """fresh/warn/stale. age=None -> stale (stale-never-green)."""
    if age is None:
        return BUCKET_STALE
    if age < sla:
        return BUCKET_FRESH
    if age < _WARN_MULTIPLIER * sla:
        return BUCKET_WARN
    return BUCKET_STALE


# ---------------------------------------------------------------------------
# SLA loading from supervisor.stack_specs
# ---------------------------------------------------------------------------

def _load_sla_map() -> Dict[str, Dict[str, Any]]:
    """Load {name: {sla_sec, hb_path}} from stack_specs HEARTBEAT-kind daemons only."""
    try:
        from supervisor.stack_specs import base_specs  # type: ignore
        from supervisor.manifest import HEARTBEAT  # type: ignore
        result: Dict[str, Dict[str, Any]] = {}
        for spec in base_specs():
            rd = spec.readiness
            hb = rd.heartbeat_path if rd.kind == HEARTBEAT else None
            result[spec.name] = {"sla_sec": float(rd.fresh_sec), "hb_path": hb}
        return result
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_lag_histogram(
    specs: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    heartbeat_dir: Optional[Path] = None,
    clock: Optional[Callable[[], float]] = None,
) -> Dict[str, Any]:
    """Compute per-daemon staleness-fraction histogram. Never raises.

    Parameters
    ----------
    specs:
        List of {"name", "sla_sec", "hb_path"} dicts (None -> load from stack_specs).
    heartbeat_dir:
        Override dir for hb_path=None daemons. Default: data/cache/daemon_heartbeats/.
    clock:
        Zero-arg callable -> epoch seconds. Default: time.time. Injectable for tests.

    Returns
    -------
    Dict: per_daemon, buckets, worst, status, honest_note. No $ field.
    """
    try:
        return _compute_inner(specs, heartbeat_dir=heartbeat_dir, clock=clock)
    except Exception:  # noqa: BLE001
        return _unavailable_sentinel("unexpected error")


def _unavailable_sentinel(reason: str = "unavailable") -> Dict[str, Any]:
    return {
        "per_daemon": [],
        "buckets": {BUCKET_FRESH: 0, BUCKET_WARN: 0, BUCKET_STALE: 0},
        "worst": [],
        "status": STATUS_UNAVAILABLE,
        "honest_note": _HONEST_NOTE,
        "_unavailable_reason": reason,
    }


def _compute_inner(
    specs: Optional[Sequence[Dict[str, Any]]],
    *,
    heartbeat_dir: Optional[Path],
    clock: Optional[Callable[[], float]],
) -> Dict[str, Any]:
    now = float(clock() if clock is not None else time.time())
    hb_dir = heartbeat_dir if heartbeat_dir is not None else _DEFAULT_HB_DIR

    if specs is None:
        sla_map = _load_sla_map()
        if not sla_map:
            return _unavailable_sentinel("supervisor.stack_specs not importable")
        raw_specs: List[Dict[str, Any]] = [
            {"name": n, "sla_sec": info["sla_sec"], "hb_path": info["hb_path"]}
            for n, info in sla_map.items()
            if info.get("hb_path") is not None
        ]
    else:
        raw_specs = [s for s in specs if isinstance(s, dict)]

    if not raw_specs:
        return _unavailable_sentinel("no heartbeat-kind daemons found in specs")

    per_daemon: List[Dict[str, Any]] = []
    for sp in raw_specs:
        name = str(sp.get("name") or "unknown")
        sla = float(sp.get("sla_sec") or 300.0)
        hb_raw = sp.get("hb_path")

        path: Optional[Path] = None
        if hb_raw is not None:
            p = Path(str(hb_raw))
            path = p if p.is_absolute() else _REPO_ROOT / p
        elif isinstance(hb_dir, Path):
            candidate = hb_dir / ("%s.txt" % name)
            if candidate.exists():
                path = candidate

        hb_dir_exists = (
            (path is not None and path.parent.exists())
            or (isinstance(hb_dir, Path) and hb_dir.exists())
        )
        if not hb_dir_exists:
            age: Optional[float] = None
        else:
            age = _read_age(path, now) if path is not None else None

        bucket = _assign_bucket(age, sla)
        staleness_frac = (
            round(age / sla, 4) if (age is not None and sla > 0) else None
        )
        per_daemon.append({
            "name": name,
            "sla_sec": sla,
            "age_sec": round(age, 1) if age is not None else None,
            "staleness_frac": staleness_frac,
            "bucket": bucket,
            "hb_path": str(path) if path is not None else None,
        })

    _bucket_rank = {BUCKET_STALE: 0, BUCKET_WARN: 1, BUCKET_FRESH: 2}

    def _sort_key(row: Dict[str, Any]) -> tuple:
        sf = row["staleness_frac"]
        return (_bucket_rank.get(row["bucket"], 99), -(sf if sf is not None else float("inf")))

    per_daemon.sort(key=_sort_key)

    n_fresh = sum(1 for r in per_daemon if r["bucket"] == BUCKET_FRESH)
    n_warn = sum(1 for r in per_daemon if r["bucket"] == BUCKET_WARN)
    n_stale = sum(1 for r in per_daemon if r["bucket"] == BUCKET_STALE)
    worst = [r["name"] for r in per_daemon if r["bucket"] == BUCKET_STALE]

    if n_stale > 0:
        status = STATUS_STALE
    elif n_warn > 0:
        status = STATUS_WARN
    else:
        status = STATUS_OK

    return {
        "per_daemon": per_daemon,
        "buckets": {BUCKET_FRESH: n_fresh, BUCKET_WARN: n_warn, BUCKET_STALE: n_stale},
        "worst": worst,
        "status": status,
        "honest_note": _HONEST_NOTE,
    }


__all__ = [
    "BUCKET_FRESH", "BUCKET_WARN", "BUCKET_STALE",
    "STATUS_OK", "STATUS_WARN", "STATUS_STALE", "STATUS_UNAVAILABLE",
    "compute_lag_histogram",
]
