"""scripts.platformkit.autoloop.clv_refresh_job -- M16: cadence-gated REFRESH
of the CLV ops artifacts (data/frontend/ops/clv_reconcile_<channel>.json +
clv_scoreboard.json). freshness_sla.py flags these 172800s/48h-stale because
they are hand/CLI-run only, no ProcSpec/daemon (autonomy/freshness_sla.py:176-189)
-- measured ~114h stale before this job existed. This is the daemon side of
that gap.

REFRESH ONLY: calls clv_result_reconciler.main() (default channels + out_dir --
writes every KNOWN_CHANNELS entry) then clv_scoreboard.main() (its own default
output path). No new promotion/verdict math; both artifacts keep whatever
edge_claimed semantics the wrapped tools already write.

Cadence = the newest clv_reconcile_*.json file's own mtime. Self-resetting: a
successful run overwrites those files, so the very next check needs a fresh
24h before it fires again -- no separate watermark to drift from the artifact,
same convention as M15's benchmark_refresh_job. The `watermarks` dict param is
accepted for call-shape uniformity with every other maintenance job (same
convention M12's milb_statsapi.run_daily already uses); unused here.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag. A raise here is isolated by run_all's own
per-job try/except (maintenance_templates._JOB_TABLE), same as every other job.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_clv_refresh_job.py -q
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.clv.clv_result_reconciler import _OUT_DIR as _OPS_DIR  # noqa: SLF001 -- reused, not redefined

logger = logging.getLogger(__name__)

_STALE_AFTER_H = 24.0
# W1 fix: pre-step sports for kx_ticker_close.write_closes(), same default set
# as kx_ticker_close._main's own CLI default.
_KX_SPORTS = ("mlb", "soccer_intl")


def _newest_reconcile_age_h(ops_dir: Path) -> Optional[float]:
    """Age in hours of the newest clv_reconcile_*.json; None if none exist
    yet (treated as due -- there is nothing to be fresh)."""
    files = list(Path(ops_dir).glob("clv_reconcile_*.json"))
    if not files:
        return None
    newest = max(p.stat().st_mtime for p in files)
    return (time.time() - newest) / 3600.0


def _default_reconcile() -> Any:
    from scripts.platformkit.clv import clv_result_reconciler as R
    # argv=[] is load-bearing: main() falls back to sys.argv[1:], which inside
    # the m38 daemon is the DAEMON's own args -- first live fire wrote
    # clv_reconcile_--interval.json instead of the real channels.
    return R.main(argv=[])


def _default_scoreboard() -> Any:
    from scripts.platformkit.clv import clv_scoreboard as S
    return S.main(argv=[])


def _default_write_closes() -> Any:
    """W1 fix: derive+persist kx-ticker close-proxies (kx_ticker_close.
    write_closes) so paper_ingame rows have a close to join against before
    the reconciler/scoreboard run -- same continuous cadence as M16 itself.
    Same argv=[] discipline as the other two default_* callables: no argv
    parsing here at all, write_closes(sport) is called directly."""
    from scripts.platformkit.clv import kx_ticker_close as K
    return [K.write_closes(s) for s in _KX_SPORTS]


def run_clv_refresh(watermarks: Optional[Dict[str, Any]] = None, *,
                    ops_dir: Optional[Path] = None,
                    age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                    reconcile_fn: Optional[Callable[[], Any]] = None,
                    scoreboard_fn: Optional[Callable[[], Any]] = None,
                    write_closes_fn: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
    """Refresh iff the newest clv_reconcile_*.json is >24h stale (or
    missing). Pre-step: derive kx-ticker close-proxies (write_closes_fn),
    error-isolated so a derive failure never blocks the reconcile/scoreboard
    that follow. Then reconciler then scoreboard, no verdict math."""
    d = Path(ops_dir) if ops_dir is not None else _OPS_DIR
    age_h = (age_fn or _newest_reconcile_age_h)(d)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}
    try:
        (write_closes_fn or _default_write_closes)()
    except Exception:  # noqa: BLE001 -- a close-derive failure must never block CLV refresh
        logger.warning("clv_refresh_job: kx write_closes step failed (isolated)",
                       exc_info=True)
    (reconcile_fn or _default_reconcile)()
    (scoreboard_fn or _default_scoreboard)()
    return {"status": "ran", "age_h": age_h}


__all__ = ["run_clv_refresh"]
