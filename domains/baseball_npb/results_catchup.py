"""domains.baseball_npb.results_catchup -- idempotent backfill-on-invocation
for the NPB (and KBO) results parquets, closing the "nobody re-ran the ingest
script by hand" lag (LANE npbkbo-results-lag).

THE GAP THIS CLOSES
--------------------
label_finals_refresh.py (scripts/platformkit/autonomy/, a prior wave-29 lane)
already wires a bounded periodic catch-up for soccer_intl/MLB/WNBA finals, but
explicitly scopes NPB/KBO OUT: "their refresh stays manual/CLI for now;
recorded here as an honest scope boundary, not silently dropped." freshness_sla.py
confirms the same thing from the monitoring side: npb_results/kbo_results are
"SLA-monitored but NOT auto-refreshed by this" runner. Nobody was invoking
domains.baseball_npb.ingest_npb / domains.baseball_kbo.ingest_kbo between
slates, so the parquets only advanced whenever a human happened to run the
CLI. Live-verified 2026-07-04: the KBO parquet's on-disk max date was
2026-07-03, but a live re-fetch of the SAME season already returns 2026-07-04
finals (5 games) -- the source is not late; nobody asked it.

WHY A SEPARATE MODULE INSTEAD OF EXTENDING label_finals_refresh.py DIRECTLY
-----------------------------------------------------------------------------
scripts/platformkit/autonomy/** is outside this lane's OWNS paths (this lane
owns domains/baseball_npb/** + the KBO ingest module only). This module is the
runnable, idempotent catch-up CLI callable today; wiring it INTO
label_finals_refresh.SPECS (so it fires on the same autonomous tick as the
other three) is a one-spec-per-sport addition documented as a PROPOSED diff
below (see PROPOSED_WIRING at the bottom of this docstring) for a human/future
lane with scripts/platformkit/autonomy/ in scope to apply.

WHY A SEASON-LEVEL RE-INGEST (not a per-date one) IS CORRECT HERE
--------------------------------------------------------------------
Unlike the ESPN JSON feeds label_finals_refresh.py targets (one JSON call per
missing UTC date), NPB is a monthly HTML scrape and KBO's fast path is a
WHOLE-SEASON single request (fetch_season_whole). Re-running ingest_season for
the current season is already idempotent (dedup key: date+home_team+away_team,
keep='last') and, for KBO, is exactly ONE HTTP request -- there is no benefit
to a per-date diff here; the "bounded" primitive on this side is "how many
months/seasons to touch", not "how many dates".

WHAT catchup_npb / catchup_kbo DO
-----------------------------------
Read the parquet's current max date (or None if missing) -> if the gap since
today (UTC) is at least --stale-after-days (default 1 -- i.e. the parquet's
newest row is not from today), re-run ingest_season for the CURRENT season
only (bounded: never touches prior seasons on a routine catch-up tick). A
gap>=1 is the correct default because NPB/KBO games finish same local day
(JST/KST) well before UTC midnight, so "max date == yesterday" already means
today's (and possibly yesterday's late-finishing) results are available and
missing. Returns a small dict: rows before/after, whether a refresh ran, and
the reason. Never raises -- a fetch failure degrades to {"refreshed": False,
"error": "..."} so a caller's tick is never sunk (same discipline as
label_finals_refresh.refresh_one).

HONESTY: descriptive/realized-score ingestion only; no $/edge field; never
writes data/registry/; never flips a flag; local commit only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_results_catchup.py -q

PROPOSED_WIRING (apply by a lane with scripts/platformkit/autonomy/ in scope):
  In scripts/platformkit/autonomy/label_finals_refresh.py, add two RefreshSpec
  entries to _default_specs() that call this module's catchup fetch_fn shape
  (dates arg ignored; season-level, not date-level):

      def _npb_results_fetch(dates, out_path):
          from domains.baseball_npb.results_catchup import catchup_npb
          return catchup_npb(out_path=out_path)

      def _kbo_results_fetch(dates, out_path):
          from domains.baseball_kbo.results_catchup_kbo import catchup_kbo
          return catchup_kbo(out_path=out_path)

  RefreshSpec(name="npb_results", out_path=repo_root/"data"/"domains"/"npb"/"npb_results.parquet",
              fetch_fn=_npb_results_fetch, max_dates_per_tick=1, bootstrap_days=1)
  RefreshSpec(name="kbo_results", out_path=repo_root/"data"/"domains"/"kbo"/"kbo_results.parquet",
              fetch_fn=_kbo_results_fetch, max_dates_per_tick=1, bootstrap_days=1)

  (max_dates_per_tick=1/bootstrap_days=1 is a no-op-shaped bound here since the
  fetch_fn ignores `dates` and re-derives its own season/current-date logic;
  kept for RefreshSpec shape-compatibility, not because it is load-bearing.)
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

log = logging.getLogger(__name__)

DEFAULT_STALE_AFTER_DAYS = 1


def _existing_row_count(out_path: Path) -> int:
    try:
        if not Path(out_path).exists():
            return 0
        return len(pd.read_parquet(out_path, columns=["date"]))
    except Exception as exc:  # noqa: BLE001
        log.debug("results_catchup: row-count read failed for %s: %s", out_path, exc)
        return 0


def _max_existing_date(out_path: Path) -> Optional[dt.date]:
    try:
        if not Path(out_path).exists():
            return None
        df = pd.read_parquet(out_path, columns=["date"])
        if df.empty:
            return None
        d = pd.to_datetime(df["date"], errors="coerce").dropna()
        if d.empty:
            return None
        return d.max().date()
    except Exception as exc:  # noqa: BLE001
        log.debug("results_catchup: max-date read failed for %s: %s", out_path, exc)
        return None


def _catchup_generic(
    *,
    label: str,
    out_path: Path,
    ingest_season_fn: Callable[..., Path],
    current_season_fn: Callable[[dt.date], str],
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    today: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """Shared idempotent catch-up shape for NPB/KBO: check staleness, re-run
    ingest_season for the CURRENT season only if stale, report before/after.
    Never raises."""
    now = today if today is not None else dt.datetime.now(dt.timezone.utc).date()
    out = Path(out_path)
    max_dt = _max_existing_date(out)
    rows_before = _existing_row_count(out)
    gap_days = None if max_dt is None else (now - max_dt).days

    is_stale = max_dt is None or gap_days >= stale_after_days
    if not is_stale:
        return {
            "name": label, "refreshed": False, "reason": "fresh",
            "max_date_before": str(max_dt) if max_dt else None,
            "gap_days": gap_days, "rows_before": rows_before,
            "rows_after": rows_before, "error": None,
        }

    season = current_season_fn(now)
    try:
        ingest_season_fn(season, out_path=out)
    except Exception as exc:  # noqa: BLE001 -- a bad fetch must never sink a caller's tick
        log.warning("results_catchup[%s] ingest_season(%s) failed: %s", label, season, exc)
        return {
            "name": label, "refreshed": False, "reason": "fetch_error",
            "max_date_before": str(max_dt) if max_dt else None,
            "gap_days": gap_days, "rows_before": rows_before,
            "rows_after": rows_before, "error": str(exc)[:200],
        }

    rows_after = _existing_row_count(out)
    max_after = _max_existing_date(out)
    return {
        "name": label, "refreshed": True, "reason": "stale",
        "max_date_before": str(max_dt) if max_dt else None,
        "max_date_after": str(max_after) if max_after else None,
        "gap_days": gap_days, "rows_before": rows_before,
        "rows_after": rows_after, "rows_added": rows_after - rows_before,
        "error": None,
    }


def catchup_npb(
    out_path: Optional[Path] = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    today: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """Idempotent NPB catch-up: re-runs ingest_season for the current season
    if the parquet's max date is at least *stale_after_days* behind UTC
    today. Safe to call on every invocation -- a fresh parquet is a no-op."""
    from domains.baseball_npb.ingest_npb import ingest_season, _DEFAULT_OUT
    out = Path(out_path) if out_path else _DEFAULT_OUT
    return _catchup_generic(
        label="npb_results", out_path=out, ingest_season_fn=ingest_season,
        current_season_fn=lambda now: str(now.year),
        stale_after_days=stale_after_days, today=today,
    )


def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Idempotent catch-up backfill for the NPB results parquet."
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("--stale-after-days", type=int, default=DEFAULT_STALE_AFTER_DAYS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = catchup_npb(out_path=args.out, stale_after_days=args.stale_after_days)
    print(result)


if __name__ == "__main__":
    _main()


__all__ = ["catchup_npb", "DEFAULT_STALE_AFTER_DAYS"]
