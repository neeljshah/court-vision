"""backfill_quarter_box_2425.py — fetch missing 2024-25 quarter-box JSONs.

Targets 2024-25 season games NOT yet in data/cache/quarter_box/, prioritising
the Jan-Apr 2025 window (folds 2 + 3 test sets in the inplay WF probe).

Idempotent: skips any (game_id, period) already on disk.
Errors logged to data/nba/quarter_box_fetch_errors.log, never crash.

Usage
-----
    python scripts/backfill_quarter_box_2425.py
    python scripts/backfill_quarter_box_2425.py --seasons 2022-23 2023-24
    python scripts/backfill_quarter_box_2425.py --limit 0   # unlimited
    python scripts/backfill_quarter_box_2425.py --sleep 1.2
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from typing import List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
_NBA_DIR = os.path.join(PROJECT_DIR, "data", "nba")
_ERR_LOG = os.path.join(PROJECT_DIR, "data", "nba", "quarter_box_fetch_errors.log")
_PERIODS = (1, 2, 3, 4)

_QUARTER_RANGE = {
    1: (0, 7200),
    2: (7200, 14400),
    3: (14400, 21600),
    4: (21600, 28800),
}

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_ERR_LOG, mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def collect_game_ids(seasons: List[str], priority_date_from: str = "") -> List[str]:
    """Collect game_ids from season_games_<season>.json files.

    If priority_date_from is set (YYYY-MM-DD), games on/after that date come
    first so we fill fold 2+3 test data before earlier training games.
    """
    rows = []
    for season in seasons:
        path = os.path.join(_NBA_DIR, f"season_games_{season}.json")
        if not os.path.exists(path):
            log.warning("no season_games file for %s: %s", season, path)
            continue
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            log.warning("failed to read %s: %s", path, exc)
            continue
        for g in payload.get("rows", []) if isinstance(payload, dict) else payload:
            gid = g.get("game_id") or g.get("GAME_ID")
            date = g.get("game_date", "")
            if gid:
                rows.append((str(gid).zfill(10), date))

    # Sort: priority window first (to fill fold 2+3 test sets), then chronological
    if priority_date_from:
        priority = [(gid, dt) for gid, dt in rows if dt >= priority_date_from]
        rest = [(gid, dt) for gid, dt in rows if dt < priority_date_from]
        priority.sort(key=lambda x: x[1])
        rest.sort(key=lambda x: x[1])
        ordered = priority + rest
    else:
        rows.sort(key=lambda x: x[1])
        ordered = rows

    # Deduplicate preserving order
    seen = set()
    result = []
    for gid, _ in ordered:
        if gid not in seen:
            seen.add(gid)
            result.append(gid)
    return result


def _coerce(v):
    """JSON-safe coercion (NaN → None)."""
    if v is None:
        return None
    if isinstance(v, (str, int, bool)):
        return v
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    try:
        f = float(v)
        if f != f:  # NaN check
            return None
        if f.is_integer():
            return int(f)
        return f
    except (TypeError, ValueError):
        return str(v)


def fetch_quarter(game_id: str, period: int,
                  cache_dir: str = _CACHE_DIR) -> bool:
    """Fetch boxscoretraditionalv2 slice for one (game_id, period).

    Returns True on successful new write, False on skip (already cached) or error.
    Errors are logged, never raised.
    """
    out_path = os.path.join(cache_dir, f"{game_id}_q{period}.json")
    if os.path.exists(out_path):
        return False
    start_tick, end_tick = _QUARTER_RANGE.get(int(period), (0, 7200))
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv2
        bs = boxscoretraditionalv2.BoxScoreTraditionalV2(
            game_id=game_id,
            start_period=str(period),
            end_period=str(period),
            start_range=str(start_tick),
            end_range=str(end_tick),
            range_type="1",
            timeout=30,
        )
        frames = bs.get_data_frames()
    except Exception as exc:
        log.error("FETCH ERROR %s q%d: %s", game_id, period, exc)
        return False

    payload = {
        "game_id": game_id,
        "period": period,
        "players": (
            [{k.lower(): _coerce(v) for k, v in row.items()}
             for row in frames[0].to_dict("records")]
            if len(frames) > 0 else []
        ),
        "teams": (
            [{k.lower(): _coerce(v) for k, v in row.items()}
             for row in frames[1].to_dict("records")]
            if len(frames) > 1 else []
        ),
    }
    os.makedirs(cache_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=["2024-25"],
                    help="Seasons to fetch (default: 2024-25)")
    ap.add_argument("--priority-from", default="2025-01-01",
                    help="Fetch games on/after this date first (fills fold 2+3 test sets)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max NEW games to fetch this run (0 = unlimited).")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="Seconds between API calls (default 1.5 = ~40 req/min).")
    ap.add_argument("--max-minutes", type=float, default=85.0,
                    help="Hard stop after this many minutes (default 85).")
    args = ap.parse_args()

    os.makedirs(_CACHE_DIR, exist_ok=True)

    ids = collect_game_ids(args.seasons, priority_date_from=args.priority_from)
    log.info("[backfill] %d unique game_ids across %s", len(ids), args.seasons)
    log.info("[backfill] priority window: games from %s onward come first", args.priority_from)

    # Identify games not fully cached
    new_games = [
        gid for gid in ids
        if not all(
            os.path.exists(os.path.join(_CACHE_DIR, f"{gid}_q{p}.json"))
            for p in _PERIODS
        )
    ]
    log.info("[backfill] %d games not fully cached", len(new_games))
    if args.limit > 0:
        new_games = new_games[: args.limit]
        log.info("[backfill] limiting to %d games (~%d calls)", len(new_games), len(new_games) * 4)

    written = skipped = errors = 0
    t_start = time.time()
    deadline = t_start + args.max_minutes * 60

    for i, gid in enumerate(new_games):
        if time.time() > deadline:
            log.info("[backfill] DEADLINE reached after %.1f min — stopping",
                     (time.time() - t_start) / 60)
            break

        for period in _PERIODS:
            out_path = os.path.join(_CACHE_DIR, f"{gid}_q{period}.json")
            if os.path.exists(out_path):
                skipped += 1
                continue
            time.sleep(args.sleep)
            ok = fetch_quarter(gid, period)
            if ok:
                written += 1
            else:
                errors += 1

        if (i + 1) % 50 == 0 or (i + 1) == len(new_games):
            elapsed = (time.time() - t_start) / 60
            log.info("  [%d/%d] written=%d skipped=%d errors=%d elapsed=%.1fmin",
                     i + 1, len(new_games), written, skipped, errors, elapsed)

    elapsed = (time.time() - t_start) / 60
    log.info("[done] written=%d skipped=%d errors=%d elapsed=%.1fmin",
             written, skipped, errors, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
