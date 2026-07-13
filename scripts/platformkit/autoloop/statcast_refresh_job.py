"""scripts.platformkit.autoloop.statcast_refresh_job -- M20: cadence-gated
REFRESH of the current-season Savant/Statcast parquet cache (data/cache/
statcast/savant_full__<season>.parquet). Gap found this morning: the cache
sat 3 days stale, silently starving the pregame crps_market MLB benchmark
(M19) and the eval-gate corpus, which both join against it -- no daemon
caller existed, a human running domains.mlb.savant_backfill by hand (or its
CLI) was the only prior path.

REFRESH ONLY: calls savant_backfill.run_season(season, max_seconds=480)
DIRECTLY -- never _main()/argparse, so no daemon argv can leak in (the
cac9f26f class; sys.argv is asserted untouched below). run_season() already
owns resumability/failure-stop/status; this job adds only the cadence gate.

SEASON: derived from the current ET calendar year via
scripts.platformkit.paper.et_day.now_et_day() -- the same shared ET-day
helper paper/bankroll/pnl already use -- rather than a frozen literal. A
frozen 2026 would silently stop refreshing the right season come next
January; deriving it is one line and reuses an existing helper.

Cadence = the season parquet's OWN mtime (data/cache/statcast/
savant_full__<season>.parquet), not a separate ops-json -- run_season()
already rewrites that exact file on every real run, so it is naturally
self-resetting, same convention as M15-M19's own-artifact-mtime watermark.
24h (not 7d): this is a live-season data cache other jobs join against, not
a claims validator. The `watermarks` dict param is accepted for call-shape
uniformity with every other maintenance job; unused here (file mtime IS the
watermark).

HONESTY: this job asserts no verdict of its own -- it passes run_season()'s
own honest status (OK / PARTIAL_CAPPED / FAILED_CONSECUTIVE /
INSUFFICIENT_DATA) through verbatim. A raise here propagates uncaught and is
isolated one level up by maintenance_templates.run_all's own try/except,
same as every other job in the table -- the parquet is untouched on that
path (stale mtime persists), so the next cycle retries.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_statcast_refresh_job.py -q
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.paper.et_day import now_et_day

_REPO = Path(__file__).resolve().parents[3]
_CACHE_DIR = _REPO / "data" / "cache" / "statcast"
_STALE_AFTER_H = 24.0  # live-season cache other jobs join against, not a claims validator
_MAX_SECONDS = 480.0


def _current_season() -> int:
    """Current season year from the shared ET calendar day (never a frozen literal)."""
    return int(now_et_day()[:4])


def _parquet_path(season: int, cache_dir: Optional[Path] = None) -> Path:
    d = Path(cache_dir) if cache_dir is not None else _CACHE_DIR
    return d / ("savant_full__%d.parquet" % season)


def _artifact_age_h(path: Path) -> Optional[float]:
    """Age in hours of the season parquet; None if it does not exist yet
    (treated as due -- there is nothing to be fresh)."""
    p = Path(path)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def _default_run() -> Dict[str, Any]:
    """Call savant_backfill.run_season() directly (never _main()/argparse) so
    no daemon argv can leak into this job's args."""
    from domains.mlb import savant_backfill as SB
    return SB.run_season(_current_season(), max_seconds=_MAX_SECONDS)


def run_statcast_refresh(watermarks: Optional[Dict[str, Any]] = None, *,
                         parquet_path: Optional[Path] = None,
                         age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                         run_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Refresh iff the current season's savant parquet is >24h stale (or
    missing). Refresh only: reruns domains.mlb.savant_backfill.run_season()
    for the current ET-year season; its own write re-arms the gate."""
    p = Path(parquet_path) if parquet_path is not None else _parquet_path(_current_season())
    age_h = (age_fn or _artifact_age_h)(p)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}
    result = (run_fn or _default_run)()
    return {"status": "ran", "age_h": age_h, "season": result.get("season"),
           "parquet_status": result.get("status")}


__all__ = ["run_statcast_refresh"]
