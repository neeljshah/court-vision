"""scripts.platformkit.autoloop.mlb_results_refresh_job -- M23: cadence-gated
REFRESH of data/domains/mlb/games_current.parquet (2022..present FINAL MLB
results). Gap found this morning: the parquet sat 27 days stale with zero
freshness REDs -- no daemon caller existed, a human running
domains.mlb.ingest_current by hand was the only prior path. A second cause
compounded it: ingest_current.build_current()'s end_date defaulted to a
FROZEN literal (the authoring date), so even a no-arg call kept re-stopping
at that fixed date forever -- fixed alongside this job (build_current's
default is now None -> yesterday, see that module's docstring).

REFRESH ONLY: calls domains.mlb.ingest_current.build_current() directly
in-process (never _main(), which only adds a print wrapper) with no
end_date override, so it inherits build_current's own "yesterday" default --
one definition of "current", not two that can drift apart.

Cadence = this job's OWN success stamp (data/frontend/ops/
mlb_results_refresh_latest.json), mtime-only, same convention as M20's
statcast_refresh_job. No live-slate gate exists for this job (mirrors M20,
which also has none -- MLB final-results ingest has no in-progress state to
avoid, _FINAL-only rows are leak-free by construction).

CORRUPTION GUARD: row count is read before and after the refresh call. A
network hiccup that leaves ingest_current mid-write (or upstream schedule
API returning a truncated day range) must never let a SHRUNK parquet look
like success -- no stamp is written unless rows_after >= rows_before, same
principle as M20's opus-flagged parquet-mtime class. A raised exception from
the ingest call is also NOT re-raised here (unlike M20's uncaught-propagate
convention): ingest_current shells out to curl per season, and a transient
network failure must not crash the autoloop tick; it is caught, reported,
and left unstamped so the next daily tick retries.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_mlb_results_refresh_job.py -q
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_REPO = Path(__file__).resolve().parents[3]
# Self-defined (matches domains.mlb.ingest_current._OUT) rather than imported at
# module level -- an eager `from domains.mlb.ingest_current import ...` here would
# bind "ingest_current" onto the domains.mlb package permanently for the process,
# which defeats the sys.modules monkeypatch _default_run's own per-file test uses
# (same class of trap the M20 statcast job's docstring warns about).
_PARQUET_PATH = _REPO / "data" / "domains" / "mlb" / "games_current.parquet"
_STAMP_PATH = _REPO / "data" / "frontend" / "ops" / "mlb_results_refresh_latest.json"
_STALE_AFTER_H = 24.0  # daily results cache, mirrors M20's statcast cadence


def _artifact_age_h(path: Path) -> Optional[float]:
    """Age in hours of this job's own success stamp; None if it does not
    exist yet (treated as due -- there is nothing to be fresh)."""
    p = Path(path)
    if not p.exists():
        return None
    return (time.time() - p.stat().st_mtime) / 3600.0


def _row_count(path: Path) -> Optional[int]:
    """FINAL-game row count of games_current.parquet; None if it does not
    exist yet (nothing to compare a shrink against)."""
    p = Path(path)
    if not p.exists():
        return None
    import pandas as pd  # noqa: PLC0415
    return len(pd.read_parquet(p, columns=["date"]))


def _default_run() -> None:
    """Call ingest_current.build_current() directly (never _main()) with no
    end_date override -- inherits build_current's own yesterday default."""
    from domains.mlb import ingest_current as IC
    IC.build_current()


def _write_stamp(path: Path, rows: int) -> None:
    import json
    from datetime import datetime, timezone
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "stamped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }, indent=1), encoding="ascii")


def run_mlb_results_refresh(watermarks: Optional[Dict[str, Any]] = None, *,
                            stamp_path: Optional[Path] = None,
                            parquet_path: Optional[Path] = None,
                            age_fn: Optional[Callable[[Path], Optional[float]]] = None,
                            row_count_fn: Optional[Callable[[Path], Optional[int]]] = None,
                            run_fn: Optional[Callable[[], Any]] = None) -> Dict[str, Any]:
    """Refresh iff this job's own success stamp is >24h stale (or missing).
    Stamps only when the refresh completed without raising AND the parquet's
    row count did not shrink; a network failure or a row-shrink both leave
    the stamp untouched so the next daily tick retries. The `watermarks`
    dict param is accepted for call-shape uniformity with every other
    maintenance job; unused here."""
    sp = Path(stamp_path) if stamp_path is not None else _STAMP_PATH
    age_h = (age_fn or _artifact_age_h)(sp)
    if age_h is not None and age_h < _STALE_AFTER_H:
        return {"status": "skipped", "age_h": round(age_h, 1)}

    pq = Path(parquet_path) if parquet_path is not None else _PARQUET_PATH
    rc = row_count_fn or _row_count
    rows_before = rc(pq)

    try:
        (run_fn or _default_run)()
    except Exception as exc:  # noqa: BLE001 -- transient network/ingest failure must not crash the tick
        return {"status": "ran", "age_h": age_h, "stamped": False,
                "reason": "error", "error": str(exc)[:200]}

    rows_after = rc(pq)
    if rows_after is None:
        return {"status": "ran", "age_h": age_h, "stamped": False,
                "reason": "no_parquet_after_run"}
    if rows_before is not None and rows_after < rows_before:
        return {"status": "ran", "age_h": age_h, "stamped": False, "reason": "row_shrink",
                "rows_before": rows_before, "rows_after": rows_after}

    _write_stamp(sp, rows_after)
    return {"status": "ran", "age_h": age_h, "stamped": True,
            "rows_before": rows_before, "rows_after": rows_after}


__all__ = ["run_mlb_results_refresh"]
