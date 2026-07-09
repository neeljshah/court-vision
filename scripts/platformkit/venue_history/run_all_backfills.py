"""scripts.platformkit.venue_history.run_all_backfills -- one-process-per-sport
driver that widens kalshi_intragame's settled-candle backfill from MLB-only to
every sport in kalshi_series_spec.SERIES_SPEC, and every (series_ticker,
market_type) pair within a sport -- NOT just the moneyline "GAME" series.

Pure orchestration: calls kalshi_intragame.run_backfill / polymarket_game_slug_
backfill.run_backfill directly as a library (no core-file edits, no CLI change
to either module). One call per (series, sport) pair, politeness inherited
from run_backfill's own sleep_sec (never parallelized within a process).

OUTPUT LAYOUT (kalshi): the pre-existing MONEYLINE "GAME" series for a sport
keeps writing to its EXISTING flat dir, data/venue_history/kalshi/<sport>/, so
every current consumer (nba_close_corpus_kalshi.py etc, which glob *.jsonl
non-recursively) sees no change. Every OTHER series (spread/total/team_total,
and tennis's second moneyline series) writes to its own subdir keyed by the
series ticker itself (never market_type alone -- tennis has TWO moneyline
series, ATP+WTA, so market_type would collide): data/venue_history/kalshi/
<sport>/<series_ticker_lower>/. A subdir is invisible to a flat glob, so this
never disturbs existing readers.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_run_all_backfills.py -q
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.platformkit.odds_provider.kalshi_series_spec import SERIES_SPEC, _GAME_SERIES
from scripts.platformkit.venue_history import kalshi_intragame
from scripts.platformkit.venue_history import polymarket_game_slug_backfill as pm_slug

_REPO_ROOT = Path(__file__).resolve().parents[3]
KALSHI_OUT = _REPO_ROOT / "data" / "venue_history" / "kalshi"

# Sports with a confirmed 2024plus Polymarket per-game moneyline corpus (see
# polymarket_game_slug_backfill module docstring: the "<sport>-<away>-<home>-
# YYYY-MM-DD" slug family is verified live ONLY for nba/mlb -- other sports'
# per-game slugs follow different conventions, e.g. soccer's tag_slug listing
# returns "epl-<team>-vs-<team>" futures/props, not a dated game pattern; see
# reference_ingame_data_sources memory). NOT looped blindly.
POLYMARKET_GAME_SLUG_SPORTS = ("nba", "mlb")


def kalshi_out_dir(sport: str, series_ticker: str) -> Path:
    """Where one (sport, series_ticker) pair's JSONL files land. The sport's
    primary moneyline GAME series keeps the pre-existing flat directory;
    every other series gets its own series-keyed subdir (never collides,
    never seen by a flat *.jsonl glob on the parent)."""
    sport_l = series_l = sport.lower()
    series_l = series_ticker.lower()
    base = KALSHI_OUT / sport.lower()
    if _GAME_SERIES.get(sport.lower()) == series_ticker:
        return base
    return base / series_l


def plan_kalshi_calls(sport: str) -> List[Tuple[str, str, Path]]:
    """(series_ticker, market_type, out_dir) for every series wired to *sport*
    in SERIES_SPEC, or [] if the sport is unsupported. Pure; never raises."""
    pairs = SERIES_SPEC.get(sport.lower(), [])
    return [(series, mt, kalshi_out_dir(sport, series)) for series, mt in pairs]


def run_kalshi_sport(sport: str, *, max_requests: int = 1200, sleep_sec: float = 1.0) -> Dict[str, Any]:
    """Run kalshi_intragame.run_backfill once per series wired to *sport*
    (sequential, politeness inherited), returning one result dict per series.

    governor_caller="backfill" (2026-07-09 fix): every request also clears the
    shared cross-process kalshi_rate_governor budget, not just this call's own
    sleep_sec pacing -- see kalshi_rate_governor.DEFAULT_RATE_SHARES."""
    results = []
    for series, market_type, out_dir in plan_kalshi_calls(sport):
        res = kalshi_intragame.run_backfill(
            series, sport, out_dir=out_dir, max_requests=max_requests, sleep_sec=sleep_sec,
            governor_caller="backfill")
        res["market_type"] = market_type
        results.append(res)
    return {"sport": sport, "venue": "kalshi", "series_results": results}


def run_many(sports: List[str], venue: str, *, max_concurrent: int = 2,
            max_requests: int = 1200, sleep_sec: float = 1.0) -> List[Dict[str, Any]]:
    """Run *venue*'s per-sport backfill for every sport in *sports*, at most
    *max_concurrent* at once (ThreadPoolExecutor -- network-bound, GIL released
    during I/O waits; sequential queue for the rest). Replaces the ad hoc "launch
    N sports as N separate unpaced processes" pattern that stacked 8 backfills on
    the shared Kalshi budget in one shot and tripped a 429 penalty (2026-07-09)."""
    runner = run_kalshi_sport if venue == "kalshi" else run_polymarket_game_slug_sport
    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrent))) as ex:
        futs = [ex.submit(runner, sport, max_requests=max_requests, sleep_sec=sleep_sec)
               for sport in sports]
        return [f.result() for f in futs]


def run_polymarket_game_slug_sport(sport: str, *, max_requests: int = 1200,
                                   sleep_sec: float = 1.0) -> Dict[str, Any]:
    """Resume the 2024plus per-game moneyline backfill for *sport* (nba/mlb
    only -- see POLYMARKET_GAME_SLUG_SPORTS). Returns {} if unsupported."""
    if sport.lower() not in POLYMARKET_GAME_SLUG_SPORTS:
        return {"sport": sport, "venue": "polymarket_game_slug", "skipped": "no confirmed slug family"}
    start = pm_slug.DEFAULT_NBA_START if sport.lower() == "nba" else pm_slug.DEFAULT_MLB_START
    result = pm_slug.run_backfill(sport, start, max_requests=max_requests, sleep_sec=sleep_sec)
    result["venue"] = "polymarket_game_slug"
    return result


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="run_all_backfills")
    ap.add_argument("--venue", choices=["kalshi", "polymarket_game_slug"], required=True)
    ap.add_argument("--sport", required=True, nargs="+", help="one or more sports")
    ap.add_argument("--max-requests", type=int, default=1200)
    ap.add_argument("--sleep-sec", type=float, default=1.0)
    ap.add_argument("--max-concurrent", type=int, default=2,
                    help="max sports run at once (2026-07-09 429-incident cap)")
    a = ap.parse_args()
    results = run_many(a.sport, a.venue, max_concurrent=a.max_concurrent,
                       max_requests=a.max_requests, sleep_sec=a.sleep_sec)
    print(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()


__all__ = [
    "kalshi_out_dir", "plan_kalshi_calls", "run_kalshi_sport",
    "run_polymarket_game_slug_sport", "run_many", "POLYMARKET_GAME_SLUG_SPORTS",
]
