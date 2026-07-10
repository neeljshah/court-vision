"""scripts.platformkit.autoloop.calibration_refresh_job -- M17: cadence-gated
REFRESH of the calibration-scoreboard ops artifact
(data/frontend/ops/calibration_scoreboard_latest.json). Before this job,
scripts/platformkit/scoreboard_history.py:15 SOURCE pointed at the one-shot
data/frontend/ops/calibration_scoreboard_wave21.json (~151h stale, no daemon
refreshes it) -- the m38 scoreboard_history maintenance job appended nothing
because the source never moved. This is the daemon side of that gap.

REFRESH ONLY: calls calibration_scoreboard.build_calibration_scoreboard(),
which now also writes the ops-json artifact (calibration_scoreboard.py's own
_write_ops_json, M17). No new tuner/verdict math here; per-sport isolation
(one tuner raising must not block the rest) already lives inside
build_calibration_scoreboard's own per-provider try/except.

Cadence = calibration_scoreboard_latest.json's own mtime. Self-resetting: a
successful run overwrites that file, so the next check needs a fresh 72h
before it fires again -- same convention as M15/M16 (benchmark_refresh_job /
clv_refresh_job). The `watermarks` dict param is accepted for call-shape
uniformity with every other maintenance job; unused here.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag. A raise here is isolated by run_all's own
per-job try/except (maintenance_templates._JOB_TABLE), same as every other job.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_calibration_refresh_job.py -q
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
_LATEST_PATH = _REPO / "data" / "frontend" / "ops" / "calibration_scoreboard_latest.json"
_STALE_AFTER_H = 72.0


def _artifact_age_h(path: Path) -> Optional[float]:
    """Age in hours of the ops-json artifact; None if it does not exist yet
    (treated as due -- there is nothing to be fresh)."""
    p = Path(path)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def _default_build() -> Any:
    from scripts.platformkit.calibration_scoreboard import build_calibration_scoreboard
    return build_calibration_scoreboard(write=True)


def run_calibration_refresh(watermarks: Optional[Dict[str, Any]] = None, *,
                            artifact_path: Optional[Path] = None,
                            age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                            build_fn: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
    """Refresh iff calibration_scoreboard_latest.json is >72h stale (or
    missing). Refresh only: rebuilds the scoreboard, no verdict math."""
    p = Path(artifact_path) if artifact_path is not None else _LATEST_PATH
    age_h = (age_fn or _artifact_age_h)(p)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}
    (build_fn or _default_build)()
    return {"status": "ran", "age_h": age_h}


__all__ = ["run_calibration_refresh"]
