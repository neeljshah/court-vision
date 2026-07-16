"""scripts.platformkit.autoloop.econ_scoreboard_refresh_job -- M29: cadence-gated
REFRESH of the 3 hand/CLI-run econ ops scoreboards freshness_sla.py's Lane 1
comment (autonomy/freshness_sla.py:175-193) flagged as "no ProcSpec/daemon at
all": after_cost_scoreboard.json, beat_the_line.json, execution_quality.json.
Found 13.8d/13.8d/9.5d stale (2026-07-16 freshness audit) -- execution_quality
is also a fail-closed input to greenlight_trust_honesty.channel_trust_status
(criterion_e), so its staleness silently withholds every greenlight forever.
This is the daemon side of that gap, mirroring clv_refresh_job.py (M16)
exactly: same argv=[] discipline, same file-mtime self-resetting cadence.

REFRESH ONLY: calls each module's own main(argv=[]) which writes its own
_OUT_JSON. No new $/verdict math -- edge_claimed semantics stay whatever the
wrapped tools already write.

Cadence = the OLDEST of the 3 artifacts' own mtime (any one going stale is
due). Self-resetting: a successful run overwrites all 3, so the next check
needs a fresh 24h before it fires again -- same convention as M15/M16.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag. A raise here is isolated by run_all's own
per-job try/except (maintenance_templates._JOB_TABLE), same as every other job.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_econ_scoreboard_refresh_job.py -q
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
_OPS_DIR = _REPO / "data" / "frontend" / "ops"
_ARTIFACTS = ("after_cost_scoreboard.json", "beat_the_line.json", "execution_quality.json")
_STALE_AFTER_H = 24.0


def _oldest_age_h(ops_dir: Path) -> Optional[float]:
    """Age in hours of the OLDEST of the 3 artifacts; None if any is missing
    (treated as due -- there is nothing to be fresh)."""
    paths = [Path(ops_dir) / name for name in _ARTIFACTS]
    if any(not p.exists() for p in paths):
        return None
    oldest = min(p.stat().st_mtime for p in paths)
    return (time.time() - oldest) / 3600.0


def _default_after_cost() -> Any:
    from scripts.platformkit.econ import after_cost_scoreboard as A
    return A.main(argv=[])


def _default_beat_the_line() -> Any:
    from scripts.platformkit.econ import beat_the_line as B
    return B.main(argv=[])


def _default_execution_quality() -> Any:
    from scripts.platformkit.clv import execution_quality as E
    return E.main(argv=[])


def run_econ_scoreboard_refresh(watermarks: Optional[Dict[str, Any]] = None, *,
                                ops_dir: Optional[Path] = None,
                                age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                                after_cost_fn: Optional[Callable[[], Any]] = None,
                                beat_the_line_fn: Optional[Callable[[], Any]] = None,
                                execution_quality_fn: Optional[Callable[[], Any]] = None
                                ) -> Dict[str, Any]:
    """Refresh iff the oldest of the 3 artifacts is >24h stale (or any is
    missing). Refresh only: reruns each scoreboard's own main(), no verdict
    math. `watermarks` accepted for call-shape uniformity; unused here (same
    convention as clv_refresh_job / calibration_refresh_job)."""
    d = Path(ops_dir) if ops_dir is not None else _OPS_DIR
    age_h = (age_fn or _oldest_age_h)(d)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}
    (after_cost_fn or _default_after_cost)()
    (beat_the_line_fn or _default_beat_the_line)()
    (execution_quality_fn or _default_execution_quality)()
    return {"status": "ran", "age_h": age_h}


__all__ = ["run_econ_scoreboard_refresh"]
