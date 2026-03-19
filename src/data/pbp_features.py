"""
pbp_features.py — Extract per-player per-season features from PBP event files.

Outputs data/nba/pbp_features_{season}.json:
  {player_id_str: {q4_shot_rate, q4_pts_share, fta_rate_pbp, foul_drawn_rate_pbp,
                   comeback_pts_pg, games_seen}}

CLI:
  python src/data/pbp_features.py --season 2024-25
  python src/data/pbp_features.py --all-seasons
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")


def _season_from_game_id(game_id: str) -> str | None:
    """Map NBA API GAME_ID prefix to season string."""
    if game_id.startswith("0022200") or game_id.startswith("0042200"):
        return "2022-23"
    if game_id.startswith("0022300") or game_id.startswith("0042300"):
        return "2023-24"
    if game_id.startswith("0022400") or game_id.startswith("0042400"):
        return "2024-25"
    return None


def _desc_contains(event: dict, text: str) -> bool:
    """Return True if any description field contains text (case-insensitive)."""
    for key in ("HOMEDESCRIPTION", "VISITORDESCRIPTION", "NEUTRALDESCRIPTION"):
        v = event.get(key) or ""
        if text.upper() in v.upper():
            return True
    return False


def _parse_margin(margin_str) -> int | None:
    """Parse SCOREMARGIN. TIE → None, None → None, else int."""
    if not margin_str or str(margin_str).upper() == "TIE":
        return None
    try:
        return int(margin_str)
    except (ValueError, TypeError):
        return None


def build(season_filter: str | None = None) -> dict:
    """Build PBP feature cache. Returns {season: {player_id: {features}}}."""
    files = sorted(glob.glob(os.path.join(_NBA_CACHE, "pbp_*.json")))
    print(f"[pbp_features] Found {len(files)} PBP files")

    # {season: {pid: {shots_total, shots_q4, pts_total, pts_q4, fta, fouls_drawn, comeback_pts}}}
    seasons: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    # Track games per player per season
    game_sets: dict = defaultdict(lambda: defaultdict(set))

    for fpath in files:
        try:
            events = json.load(open(fpath, encoding="utf-8"))
        except Exception as e:
            print(f"  skip {fpath}: {e}")
            continue
        if not events:
            continue

        game_id_raw = str(events[0].get("GAME_ID", ""))
        season = _season_from_game_id(game_id_raw)
        if season is None:
            continue
        if season_filter and season != season_filter:
            continue

        gid = game_id_raw or fpath

        for ev in events:
            etype = ev.get("EVENTMSGTYPE")
            period = ev.get("PERIOD", 0)
            pid1 = ev.get("PLAYER1_ID")
            pid2 = ev.get("PLAYER2_ID")
            margin = _parse_margin(ev.get("SCOREMARGIN"))

            if not pid1 or pid1 == "0" or pid1 == 0:
                continue
            pid1 = str(pid1)

            # Track game participation
            game_sets[season][pid1].add(gid)

            acc = seasons[season][pid1]

            if etype == 1:  # made FG
                is3 = _desc_contains(ev, "3PT")
                pts = 3 if is3 else 2
                acc["shots_total"] += 1
                acc["pts_total"] += pts
                if period == 4:
                    acc["shots_q4"] += 1
                    acc["pts_q4"] += pts
                # Comeback: team is losing by more than 5
                if margin is not None and margin < -5:
                    acc["comeback_pts"] += pts

            elif etype == 2:  # missed FG
                acc["shots_total"] += 1
                if period == 4:
                    acc["shots_q4"] += 1

            elif etype == 3:  # free throw
                acc["fta"] += 1
                if not _desc_contains(ev, "MISS"):
                    acc["pts_total"] += 1
                    if period == 4:
                        acc["pts_q4"] += 1
                    if margin is not None and margin < -5:
                        acc["comeback_pts"] += 1

            elif etype == 6:  # foul — PLAYER2_ID drew the foul
                if pid2 and pid2 != "0" and pid2 != 0:
                    pid2 = str(pid2)
                    game_sets[season][pid2].add(gid)
                    seasons[season][pid2]["fouls_drawn"] += 1

    # Normalize to per-game rates
    result: dict = {}
    for season, players in seasons.items():
        result[season] = {}
        for pid, acc in players.items():
            n_games = len(game_sets[season].get(pid, set())) or 1
            shots_total = max(acc.get("shots_total", 0), 1)
            pts_total = max(acc.get("pts_total", 0), 1)
            result[season][pid] = {
                "q4_shot_rate":        round(acc.get("shots_q4", 0) / shots_total, 4),
                "q4_pts_share":        round(acc.get("pts_q4", 0) / pts_total, 4),
                "fta_rate_pbp":        round(acc.get("fta", 0) / n_games, 4),
                "foul_drawn_rate_pbp": round(acc.get("fouls_drawn", 0) / n_games, 4),
                "comeback_pts_pg":     round(acc.get("comeback_pts", 0) / n_games, 4),
                "games_seen":          n_games,
            }

    # Save per-season
    for season, data in result.items():
        out = os.path.join(_NBA_CACHE, f"pbp_features_{season}.json")
        json.dump(data, open(out, "w"), indent=2)
        print(f"[pbp_features] {season}: {len(data)} players -> {out}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build PBP per-player feature cache")
    parser.add_argument("--season", help="Single season e.g. 2024-25")
    parser.add_argument("--all-seasons", action="store_true", help="Build all seasons")
    args = parser.parse_args()
    if args.all_seasons:
        build()
    elif args.season:
        build(args.season)
    else:
        build("2024-25")
