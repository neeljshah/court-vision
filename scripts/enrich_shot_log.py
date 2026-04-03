"""
enrich_shot_log.py — Enrich shot_log.csv in two ways:

  Mode 1 (default/--fill): Fill missing shots using NBA Stats shot chart ground truth.
    For each processed game in data/tracking/, fetches nba_shot_chart for that game
    and adds shots the CV tracker missed (tagged source="nba_api").

  Mode 2 (--pbp): Re-enrich shot_log and possessions with official PBP data.
    Fetches play-by-play for all 4 periods and matches shots to official events.

Usage:
    python scripts/enrich_shot_log.py [--game-ids ID1 ID2 ...]  # fill from shot chart
    python scripts/enrich_shot_log.py --pbp [--game-ids ...]    # re-enrich with PBP
    python scripts/enrich_shot_log.py --all                     # PBP re-enrich all games
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_DATA      = os.path.join(PROJECT_DIR, "data")
_TRACKING  = os.path.join(_DATA, "tracking")
_NBA_CACHE = os.path.join(_DATA, "nba")

# Seconds window for deduplication: if a CV shot is within ±N sec of an NBA shot, skip
_DEDUP_WINDOW_SEC = 8.0


# ── NBA shot chart helpers ─────────────────────────────────────────────────────

def _rate_limit() -> None:
    time.sleep(0.6)


def _cache_path(key: str) -> str:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    import re
    return os.path.join(_NBA_CACHE, re.sub(r"[^A-Za-z0-9_-]", "_", key) + ".json")


def fetch_shot_chart(game_id: str, season: str = "2024-25") -> List[dict]:
    """Fetch NBA Stats shot chart for a game (cached to data/nba/).

    Returns list of dicts with keys:
        PLAYER_NAME, TEAM_ABBREVIATION, PERIOD, MINUTES_REMAINING,
        SECONDS_REMAINING, LOC_X, LOC_Y, SHOT_ZONE_BASIC, SHOT_MADE_FLAG,
        ACTION_TYPE, SHOT_TYPE
    """
    cache = _cache_path(f"shot_chart_{game_id}")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)

    try:
        from nba_api.stats.endpoints import shotchartdetail
    except ImportError:
        raise RuntimeError("nba_api not installed. Run: pip install nba_api")

    _rate_limit()
    raw = shotchartdetail.ShotChartDetail(
        player_id=0,        # 0 = all players for the game
        team_id=0,
        game_id_nullable=game_id,
        context_measure_simple="FGA",
        season_nullable=season,
    )
    df = raw.get_data_frames()[0]
    rows = df.to_dict(orient="records")

    with open(cache, "w") as f:
        json.dump(rows, f, indent=2)

    return rows


def _nba_coords_to_ft(loc_x: float, loc_y: float) -> tuple:
    """Convert NBA API shot coordinates (tenths of feet from basket) to court feet.

    NBA API:
      LOC_X: horizontal offset — negative = left of basket, positive = right.
              Measured from directly below the basket along the baseline.
      LOC_Y: distance from basket toward halfcourt (always positive for field goals).

    We convert to (ft_x_from_left_sideline, ft_y_from_left_baseline):
      ft_x = 25.0 + LOC_X / 10.0   (court is 50 ft wide; basket at 25 ft)
      ft_y =  5.25 + LOC_Y / 10.0  (basket is ~5.25 ft from baseline)
    """
    ft_x = 25.0 + loc_x / 10.0
    ft_y = 5.25 + loc_y / 10.0
    return round(ft_x, 2), round(ft_y, 2)


def _period_to_game_time(period: int, minutes_remaining: int, seconds_remaining: int) -> float:
    """Convert (period, min_remaining, sec_remaining) to absolute game time in seconds."""
    if period <= 4:
        period_len = 720        # 12-minute quarters
        period_offset = (period - 1) * 720
    else:
        period_len = 300        # 5-minute OT periods
        period_offset = 4 * 720 + (period - 5) * 300
    elapsed_in_period = period_len - (minutes_remaining * 60 + seconds_remaining)
    return float(period_offset + elapsed_in_period)


# ── Mode 1: Fill from NBA shot chart ──────────────────────────────────────────

def enrich_game_from_shot_chart(game_id: str, season: str = "2024-25") -> Optional[dict]:
    """Enrich shot_log.csv for one game using NBA shot chart ground truth.

    Returns dict with before/after shot counts, or None if game dir not found.
    """
    game_dir = os.path.join(_TRACKING, game_id)
    if not os.path.isdir(game_dir):
        print(f"  [skip] {game_id}: tracking dir not found")
        return None

    shot_log_path = os.path.join(game_dir, "shot_log.csv")
    if not os.path.exists(shot_log_path):
        print(f"  [skip] {game_id}: shot_log.csv not found")
        return None

    with open(shot_log_path, newline="", encoding="utf-8", errors="replace") as f:
        cv_shots = list(csv.DictReader(f))
    n_cv = len(cv_shots)

    try:
        nba_shots = fetch_shot_chart(game_id, season=season)
    except Exception as e:
        print(f"  [error] {game_id}: shot chart fetch failed — {e}")
        return None

    if not nba_shots:
        print(f"  [skip] {game_id}: shot chart returned 0 shots")
        return None

    # Build CV timestamps for dedup
    cv_timestamps: List[float] = []
    for shot in cv_shots:
        try:
            cv_timestamps.append(float(shot.get("timestamp", 0) or 0))
        except (ValueError, TypeError):
            cv_timestamps.append(0.0)

    # Determine field names
    if cv_shots:
        fieldnames = list(cv_shots[0].keys())
    else:
        fieldnames = [
            "frame", "timestamp", "player_name", "team",
            "x_norm", "y_norm", "ft_x", "ft_y",
            "shot_zone", "made", "source",
        ]
    for col in ("ft_x", "ft_y", "shot_zone", "made", "source", "player_name"):
        if col not in fieldnames:
            fieldnames.append(col)

    # Tag existing CV shots
    for shot in cv_shots:
        if not shot.get("source"):
            shot["source"] = "cv"

    new_rows: List[dict] = []
    for nba_shot in nba_shots:
        try:
            period  = int(nba_shot.get("PERIOD", 1) or 1)
            min_rem = int(nba_shot.get("MINUTES_REMAINING", 0) or 0)
            sec_rem = int(nba_shot.get("SECONDS_REMAINING", 0) or 0)
            game_ts = _period_to_game_time(period, min_rem, sec_rem)
        except (ValueError, TypeError):
            continue

        # Skip if covered by a CV shot
        if any(abs(cv_ts - game_ts) <= _DEDUP_WINDOW_SEC for cv_ts in cv_timestamps):
            continue

        try:
            loc_x = float(nba_shot.get("LOC_X", 0) or 0)
            loc_y = float(nba_shot.get("LOC_Y", 0) or 0)
            ft_x, ft_y = _nba_coords_to_ft(loc_x, loc_y)
        except (ValueError, TypeError):
            ft_x, ft_y = "", ""

        row: Dict[str, object] = {k: "" for k in fieldnames}
        row["frame"]       = int(game_ts * 30)   # estimate at 30 fps
        row["timestamp"]   = round(game_ts, 3)
        row["player_name"] = str(nba_shot.get("PLAYER_NAME", "") or "")
        row["team"]        = str(nba_shot.get("TEAM_ABBREVIATION", "") or "")
        row["ft_x"]        = ft_x
        row["ft_y"]        = ft_y
        row["shot_zone"]   = str(nba_shot.get("SHOT_ZONE_BASIC", "") or "")
        row["made"]        = int(nba_shot.get("SHOT_MADE_FLAG", 0) or 0)
        row["source"]      = "nba_api"
        new_rows.append(row)
        cv_timestamps.append(game_ts)  # prevent double-counting same NBA shot

    n_added = len(new_rows)
    n_total = n_cv + n_added

    if new_rows:
        all_rows = cv_shots + new_rows
        all_rows.sort(key=lambda r: float(r.get("timestamp", 0) or 0))
        with open(shot_log_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_rows)
        print(f"  Game {game_id}: {n_cv} CV shots + {n_added} NBA fills = {n_total} total")
    else:
        print(f"  Game {game_id}: {n_cv} CV shots + 0 NBA fills = {n_total} total (CV covered all)")

    return {"game_id": game_id, "cv_shots": n_cv, "nba_fills": n_added, "total": n_total}


# ── Mode 2: PBP re-enrichment (original enrich_shot_log.py logic) ─────────────

def enrich_game_pbp(game_id: str) -> dict:
    """Re-enrich a single game's shot_log and possessions with official PBP data."""
    from src.data.nba_enricher import enrich, _infer_period_count, _infer_fps

    game_dir = os.path.join(_TRACKING, game_id)
    if not os.path.isdir(game_dir):
        print(f"  {game_id}: directory not found — skipped")
        return {}
    if not os.path.exists(os.path.join(game_dir, "shot_log.csv")):
        print(f"  {game_id}: no shot_log.csv — skipped")
        return {}

    periods, max_ts = _infer_period_count(game_dir)
    clip_fps = _infer_fps(game_dir, default=30.0)

    print(f"\n{'='*60}")
    print(f"  Enriching {game_id}")
    print(f"  Periods: {periods}, max_ts: {max_ts:.0f}s, fps: {clip_fps}")
    print(f"{'='*60}")

    try:
        if len(periods) == 1:
            result = enrich(
                game_id=game_id,
                period=1,
                clip_start_sec=0.0,
                fps=clip_fps,
                data_dir=game_dir,
            )
        else:
            result = enrich(
                game_id=game_id,
                periods=periods,
                clip_start_sec=0.0,
                fps=clip_fps,
                data_dir=game_dir,
            )
        return result
    except Exception as exc:
        print(f"  {game_id}: enrichment failed — {exc}")
        return {}


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich shot_log.csv with NBA shot chart fills or PBP re-enrichment"
    )
    parser.add_argument(
        "game_ids_pos", nargs="*", metavar="GAME_ID",
        help="Game IDs to process (positional, optional)"
    )
    parser.add_argument(
        "--game-ids", nargs="*", metavar="GAME_ID",
        help="Game IDs to process (flag form)"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Process all games in data/tracking/"
    )
    parser.add_argument(
        "--pbp", action="store_true",
        help="Mode 2: re-enrich with PBP (default is shot chart fill)"
    )
    parser.add_argument(
        "--season", default="2024-25",
        help="NBA season for shot chart API (default: 2024-25)"
    )
    args = parser.parse_args()

    # Collect game IDs
    game_ids = list(args.game_ids_pos or []) + list(args.game_ids or [])

    if args.all or not game_ids:
        discovered = []
        if os.path.isdir(_TRACKING):
            for entry in sorted(os.listdir(_TRACKING)):
                full = os.path.join(_TRACKING, entry)
                if (os.path.isdir(full)
                        and os.path.exists(os.path.join(full, "shot_log.csv"))):
                    discovered.append(entry)
        if discovered:
            game_ids = game_ids + [g for g in discovered if g not in game_ids]
        if not game_ids:
            print("No processed games found in data/tracking/")
            return

    # Remove duplicates preserving order
    seen = set()
    unique_ids: List[str] = []
    for g in game_ids:
        if g not in seen:
            seen.add(g)
            unique_ids.append(g)
    game_ids = unique_ids

    if args.pbp:
        # Mode 2: PBP re-enrichment
        print(f"PBP re-enriching {len(game_ids)} game(s)...")
        for gid in game_ids:
            enrich_game_pbp(gid)
        print("\nDone. Run audit_phase_g.py to verify results.")
    else:
        # Mode 1: Shot chart fill (default)
        print(f"Filling shots from NBA shot chart for {len(game_ids)} game(s)")
        print(f"Season: {args.season}  |  Dedup window: ±{_DEDUP_WINDOW_SEC}s\n")

        results = []
        for gid in game_ids:
            result = enrich_game_from_shot_chart(gid, season=args.season)
            if result:
                results.append(result)

        if results:
            print("\n── Summary ─────────────────────────────")
            total_cv    = sum(r["cv_shots"]  for r in results)
            total_fills = sum(r["nba_fills"] for r in results)
            total_shots = sum(r["total"]     for r in results)
            for r in results:
                print(f"  {r['game_id']}: {r['cv_shots']:3d} CV + {r['nba_fills']:3d} NBA = {r['total']:3d} total")
            print(f"  {'─'*38}")
            print(f"  Total  : {total_cv:3d} CV + {total_fills:3d} NBA fills = {total_shots} total")


if __name__ == "__main__":
    main()
