"""
fetch_pbp_backfill_fast.py
===========================
Fast bulk PBP backfill: ONE API call per game (full game, all periods).
Splits the response into per-period JSON files matching the schema expected by
build_pbp_possession_features.py and backfill_pbp_context.py:

    data/nba/pbp_{game_id}_p{period}.json

Each file is a list of event dicts:
    {period, game_clock_sec, event_type, event_desc,
     player_name, team_abbrev, score, score_margin}

At ~0.6s delay + ~1-2s network per game = ~2s/game → 1230 games ≈ 40 min.
4 periods × old approach = 4-5 calls × 8s avg = ~35s/game → 1230 games ≈ 7h.

Usage:
    python scripts/fetch_pbp_backfill_fast.py --seasons 2023-24
    python scripts/fetch_pbp_backfill_fast.py --seasons 2023-24 2022-23
    python scripts/fetch_pbp_backfill_fast.py --seasons 2023-24 --max 50
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Apply NBA API headers patch BEFORE any nba_api import
from src.data.nba_api_headers_patch import apply_patch
apply_patch()

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_ERROR_LOG = os.path.join(_NBA_CACHE, "pbp_fetch_errors.log")

# Delay between API calls (seconds). 0.6s stays within NBA rate limits.
_DELAY = 0.6

# Period-length constants (seconds elapsed, not remaining)
_V3_ACTION_TO_EVTYPE = {
    "Made Shot":    1,
    "Missed Shot":  2,
    "Free Throw":   3,
    "Rebound":      4,
    "Turnover":     5,
    "Foul":         6,
    "Substitution": 8,
}


def _log_error(game_id: str, msg: str) -> None:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(_ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{ts}  game={game_id}  error={msg}\n")


def _parse_clock(clock_str: str, period: int) -> int:
    """Convert V3 ISO clock string to elapsed seconds in period."""
    try:
        m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
        if not m:
            return 0
        remaining = int(m.group(1)) * 60 + float(m.group(2))
        period_len = 300 if period > 4 else 720
        return int(period_len - remaining)
    except Exception:
        return 0


def _game_is_cached(game_id: str) -> bool:
    """Return True if at least p1-p4 are all cached with period-end event."""
    for p in range(1, 5):
        path = os.path.join(_NBA_CACHE, f"pbp_{game_id}_p{p}.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, list) or len(data) == 0:
                return False
        except Exception:
            return False
    return True


def fetch_game_pbp_fast(game_id: str) -> bool:
    """
    Fetch all periods for one game in a single API call.

    Saves per-period JSON files. Returns True on success.
    """
    from nba_api.stats.endpoints import playbyplayv3

    try:
        time.sleep(_DELAY)
        raw = playbyplayv3.PlayByPlayV3(game_id=game_id)
        df = raw.get_data_frames()[0]
    except Exception as e:
        _log_error(game_id, f"API call failed: {str(e)[:200]}")
        return False

    if len(df) == 0:
        _log_error(game_id, "empty response from API")
        return False

    # Forward-fill scores
    df = df.copy()
    df["scoreHome"] = df["scoreHome"].replace("", None).ffill()
    df["scoreAway"] = df["scoreAway"].replace("", None).ffill()

    # Group events by period
    by_period: dict[int, list[dict]] = {}

    for _, r in df.iterrows():
        period = int(r.get("period", 0))
        if period <= 0:
            continue

        clock_str = str(r.get("clock", "PT12M00.00S"))
        elapsed = _parse_clock(clock_str, period)

        action = str(r.get("actionType", "") or "")
        sub    = str(r.get("subType", "") or "")
        ev_type = (
            13 if (action == "period" and sub == "end")
            else _V3_ACTION_TO_EVTYPE.get(action, 0)
        )

        sh = str(r.get("scoreHome", "") or "")
        sa = str(r.get("scoreAway", "") or "")
        score  = f"{sh}-{sa}" if sh and sa else ""
        try:
            margin = str(int(sh) - int(sa)) if sh and sa else ""
        except Exception:
            margin = ""

        row = {
            "period":         period,
            "game_clock_sec": elapsed,
            "event_type":     ev_type,
            "event_desc":     str(r.get("description", "") or ""),
            "player_name":    str(r.get("playerName", "") or ""),
            "team_abbrev":    str(r.get("teamTricode", "") or ""),
            "score":          score,
            "score_margin":   margin,
        }
        by_period.setdefault(period, []).append(row)

    if not by_period:
        _log_error(game_id, "no period events parsed from response")
        return False

    # Write per-period JSON files
    os.makedirs(_NBA_CACHE, exist_ok=True)
    for period, events in sorted(by_period.items()):
        path = os.path.join(_NBA_CACHE, f"pbp_{game_id}_p{period}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f)

    return True


def _load_game_ids(season: str) -> list[str]:
    path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(path):
        print(f"[backfill] ERROR: season_games file not found: {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    rows = data.get("rows", data) if isinstance(data, dict) else data
    return [str(r["game_id"]) for r in rows if r.get("game_id")]


def backfill_season(
    season: str,
    max_games: int = 9999,
    t_deadline: float = float("inf"),
) -> dict:
    game_ids = _load_game_ids(season)
    if not game_ids:
        return {"season": season, "total": 0, "fetched": 0, "skipped": 0, "errored": 0}

    print(f"\n[backfill] Season {season}: {len(game_ids)} games in schedule")
    print(f"[backfill] Already cached: {sum(1 for g in game_ids if _game_is_cached(g))}")

    total_fetched = 0
    total_skipped = 0
    total_errored = 0
    processed = 0
    t_start = time.time()

    for gid in game_ids:
        if processed >= max_games:
            print(f"[backfill] Reached --max {max_games}. Stopping.")
            break
        if time.time() > t_deadline:
            remaining = len(game_ids) - processed
            print(f"[backfill] Time budget reached at game {processed}/{len(game_ids)} "
                  f"({remaining} remaining). Stopping.")
            break

        if _game_is_cached(gid):
            total_skipped += 1
            processed += 1
            # Don't print individual skips — too noisy for 1000+ games
            if processed % 100 == 0:
                elapsed = time.time() - t_start
                rate = processed / elapsed if elapsed > 0 else 1
                remaining = len(game_ids) - processed
                eta_min = remaining / rate / 60
                print(
                    f"  [{season}] {processed}/{len(game_ids)} | "
                    f"fetched={total_fetched} skipped={total_skipped} err={total_errored} | "
                    f"{elapsed:.0f}s elapsed ETA~{eta_min:.0f}min",
                    flush=True
                )
            continue

        ok = fetch_game_pbp_fast(gid)
        if ok:
            total_fetched += 1
        else:
            total_errored += 1
        processed += 1

        if total_fetched % 50 == 0 and total_fetched > 0:
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 1
            remaining = len(game_ids) - processed
            eta_min = remaining / rate / 60
            print(
                f"  [{season}] {processed}/{len(game_ids)} | "
                f"fetched={total_fetched} skipped={total_skipped} err={total_errored} | "
                f"{elapsed:.0f}s elapsed ETA~{eta_min:.0f}min",
                flush=True
            )

    elapsed = time.time() - t_start
    # Final count of cached files
    final_cached = sum(1 for g in game_ids if _game_is_cached(g))
    print(
        f"\n[backfill] {season} DONE | "
        f"fetched={total_fetched} skipped={total_skipped} err={total_errored} | "
        f"total cached={final_cached}/{len(game_ids)} | "
        f"{elapsed:.0f}s ({elapsed/60:.1f} min)",
        flush=True
    )
    return {
        "season": season,
        "total": len(game_ids),
        "processed": processed,
        "fetched": total_fetched,
        "skipped": total_skipped,
        "errored": total_errored,
        "final_cached": final_cached,
        "elapsed_sec": round(elapsed, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fast bulk PBP backfill (1 call/game)")
    ap.add_argument(
        "--seasons", nargs="+", default=["2023-24"],
        help="Seasons to backfill (e.g. 2023-24 2022-23)",
    )
    ap.add_argument(
        "--max", type=int, default=9999,
        help="Max games per season (testing only)",
    )
    ap.add_argument(
        "--budget-minutes", type=float, default=85,
        help="Total time budget in minutes (default 85)",
    )
    args = ap.parse_args()

    t_deadline = time.time() + args.budget_minutes * 60
    print(
        f"[backfill] Seasons={args.seasons} | Budget={args.budget_minutes}min | "
        f"Max/season={args.max}"
    )
    print(f"[backfill] Error log: {_ERROR_LOG}")

    results = []
    for season in args.seasons:
        if time.time() > t_deadline:
            print(f"[backfill] Budget exhausted before {season}")
            break
        r = backfill_season(season, max_games=args.max, t_deadline=t_deadline)
        results.append(r)

    print("\n[backfill] === SUMMARY ===")
    for r in results:
        print(
            f"  {r['season']}: fetched={r.get('fetched', 0)} "
            f"skipped={r.get('skipped', 0)} err={r.get('errored', 0)} "
            f"total_cached={r.get('final_cached', '?')}/{r.get('total', '?')} "
            f"({r.get('elapsed_sec', 0):.0f}s)"
        )


if __name__ == "__main__":
    main()
