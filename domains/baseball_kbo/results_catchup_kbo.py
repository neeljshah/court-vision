"""domains.baseball_kbo.results_catchup_kbo -- idempotent backfill-on-invocation
for the KBO results parquet (KBO half of LANE npbkbo-results-lag; see
domains.baseball_npb.results_catchup for the full gap writeup + PROPOSED
wiring into scripts/platformkit/autonomy/label_finals_refresh.py, which this
module's docstring intentionally does not repeat).

Live-verified 2026-07-04: on-disk kbo_results.parquet max date was 2026-07-03
(5 games missing); a live re-fetch of season 2026 via fetch_season_whole (ONE
HTTP request -- verified recipe in ingest_kbo.py's module docstring) already
returns 2026-07-04 finals. The source was never late; nobody re-invoked
ingest_season since 07-03.

Season-level (not per-date) re-ingest is correct here: KBO's default fetch
path is gameMonth='' (whole season in one request), so re-running
ingest_season for the CURRENT season is one HTTP call and is already
idempotent (dedup key date+home_team+away_team, keep='last').

HONESTY: descriptive/realized-score ingestion only; no $/edge field; never
writes data/registry/; never flips a flag; local commit only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_results_catchup_kbo.py -q
"""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_STALE_AFTER_DAYS = 1


def catchup_kbo(
    out_path: Optional[Path] = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    today: Optional[dt.date] = None,
) -> Dict[str, Any]:
    """Idempotent KBO catch-up: re-runs ingest_season for the current season
    if the parquet's max date is at least *stale_after_days* behind UTC
    today. Safe to call on every invocation -- a fresh parquet is a no-op.
    Shares the staleness-check/report shape with catchup_npb (imported lazily
    to avoid a hard cross-domain import at module load)."""
    from domains.baseball_kbo.ingest_kbo import ingest_season, _DEFAULT_OUT
    from domains.baseball_npb.results_catchup import _catchup_generic

    out = Path(out_path) if out_path else _DEFAULT_OUT
    return _catchup_generic(
        label="kbo_results", out_path=out, ingest_season_fn=ingest_season,
        current_season_fn=lambda now: str(now.year),
        stale_after_days=stale_after_days, today=today,
    )


def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Idempotent catch-up backfill for the KBO results parquet."
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("--stale-after-days", type=int, default=DEFAULT_STALE_AFTER_DAYS)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = catchup_kbo(out_path=args.out, stale_after_days=args.stale_after_days)
    print(result)


if __name__ == "__main__":
    _main()


__all__ = ["catchup_kbo", "DEFAULT_STALE_AFTER_DAYS"]
