"""scripts.platformkit.sla.sla_scoreboard -- per-artifact SLA verdict engine (IOX-1).

WHY THIS EXISTS
---------------
ops.metrics_rollup only counts LIVENESS (how many services report a heartbeat);
it never computes a per-artifact, per-SLA-deadline breach verdict. One glance at
the SLA scoreboard answers "is anything stale?" across every output artifact the
stack owns.

API
---
build(artifacts, now) -> list[dict]
    Given a list of (artifact_path, sla_sec) tuples and an epoch ``now``, return
    one row per artifact:

        {
          "name":     str,          # basename of artifact_path
          "age_sec":  float | None, # seconds since mtime; None when file absent
          "sla_sec":  float,        # configured SLA deadline
          "breached": bool,         # True if age_sec is None OR age_sec > sla_sec
          "status":   str           # "ok" | "STALE"
        }

    Invariants:
    - missing file -> age_sec=None, breached=True, status="STALE"
    - age_sec > sla_sec -> breached=True, status="STALE"
    - age_sec <= sla_sec -> breached=False, status="ok"
    - empty input -> returns [] (never raises)
    - never raises on any input

write_scoreboard(rows, out_path) -> bool
    Atomically write the scoreboard list to ``out_path`` as ASCII JSON.
    Returns True on success, False on I/O error (never raises).

INVARIANTS: <=300 LOC; ASCII only; stdlib only; no $ field; no ROI; stale-never-
green; never raises; MEASUREMENT-ONLY (reads mtime, writes one JSON file).
"""
from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for _ in range(10):
        here = here.parent
        if (here / "CLAUDE.md").exists():
            return here
    return pathlib.Path(__file__).resolve().parents[4]


_REPO = _find_repo_root()

# Default output path (written atomically each tick)
DEFAULT_OUT = _REPO / "data" / "frontend" / "ops" / "sla_scoreboard.json"

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

_STATUS_OK = "ok"
_STATUS_STALE = "STALE"


# ---------------------------------------------------------------------------
# Core verdict logic
# ---------------------------------------------------------------------------

def _mtime_age(path: pathlib.Path, now: float) -> Optional[float]:
    """Return seconds since file mtime, or None if absent / unreadable."""
    try:
        return now - os.path.getmtime(str(path))
    except OSError:
        return None


def _row(
    artifact_path: Union[str, pathlib.Path],
    sla_sec: float,
    now: float,
) -> Dict[str, Any]:
    """Build one SLA verdict row. Never raises."""
    p = pathlib.Path(artifact_path)
    name = p.name
    age = _mtime_age(p, now)

    if age is None:
        # file absent -> always breached, never ok/green
        return {
            "name": name,
            "age_sec": None,
            "sla_sec": float(sla_sec),
            "breached": True,
            "status": _STATUS_STALE,
        }

    breached = age > sla_sec
    return {
        "name": name,
        "age_sec": round(age, 3),
        "sla_sec": float(sla_sec),
        "breached": breached,
        "status": _STATUS_STALE if breached else _STATUS_OK,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build(
    artifacts: Sequence[Tuple[Union[str, pathlib.Path], float]],
    now: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Build SLA verdict rows from a list of (artifact_path, sla_sec) pairs.

    Parameters
    ----------
    artifacts : sequence of (path, sla_sec)
        Each element is (path-to-artifact, SLA-deadline-in-seconds).
    now : float | None
        Epoch timestamp for age computation. Defaults to time.time().

    Returns
    -------
    list[dict]
        One row per artifact with keys: name, age_sec, sla_sec, breached, status.
        Empty input -> [].  Never raises.
    """
    if not artifacts:
        return []
    _now = float(now) if now is not None else time.time()
    rows: List[Dict[str, Any]] = []
    for item in artifacts:
        try:
            artifact_path, sla_sec = item
            rows.append(_row(artifact_path, float(sla_sec), _now))
        except Exception:  # noqa: BLE001 -- one bad entry must not abort the list
            pass
    return rows


def write_scoreboard(
    rows: List[Dict[str, Any]],
    out_path: Optional[Union[str, pathlib.Path]] = None,
    *,
    generated_at_epoch: Optional[float] = None,
) -> bool:
    """Atomically write the SLA scoreboard to *out_path* as ASCII JSON.

    The output document:
        {
          "generated_at": "<ISO-8601 UTC>",
          "rows": [ <row>, ... ],
          "any_breached": <bool>,
          "honest_note": "<string>"
        }

    Returns True on success, False on I/O error. Never raises.
    """
    path = pathlib.Path(out_path) if out_path is not None else DEFAULT_OUT
    try:
        ts = generated_at_epoch if generated_at_epoch is not None else time.time()
        from datetime import datetime, timezone
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        doc: Dict[str, Any] = {
            "generated_at": iso,
            "rows": rows,
            "any_breached": any(r.get("breached", True) for r in rows),
            "honest_note": (
                "MEASUREMENT-ONLY SLA scoreboard (IOX-1). "
                "Calibration not edge; no dollar field; stale-never-green."
            ),
        }
        raw = json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- I/O failure must not propagate
        return False


__all__ = ["build", "write_scoreboard", "DEFAULT_OUT"]
