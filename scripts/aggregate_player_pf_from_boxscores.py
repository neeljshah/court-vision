"""aggregate_player_pf_from_boxscores.py — extract per-player PF from cached
traditional boxscores (cycle 91b, loop 5).

Reads every cached data/nba/boxscore_<game_id>.json (the traditional
boxscoresummaryv2-style cache used by the live pipeline) and writes
data/player_pf.parquet with one row per (game_id, player_id) carrying:
    game_id, player_id, team_abbreviation, game_date, pf, min

Game-date join: pulled from cached data/nba/season_games_<season>.json
(game_id -> game_date), identical pattern to aggregate_player_advanced_stats.py.

Why: data/nba/gamelog_<pid>_<season>.json keeps only
PTS/REB/AST/FG3M/STL/BLK/TOV/MIN — PF is absent. Cycle 90c T1-B foul-rate
probe silently degraded to a BLK proxy. This parquet exposes PF on a
(game_id, player_id) key so build_pergame_dataset can left-join PF per row
without disturbing the source-of-truth gamelog caches.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Dict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "player_pf.parquet")


def build_game_date_lookup() -> Dict[str, str]:
    """Map game_id -> game_date by scanning cached season_games files."""
    lookup: Dict[str, str] = {}
    for path in glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json")):
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        rows = payload["rows"] if isinstance(payload, dict) else payload
        for g in rows:
            gid = str(g.get("game_id", "")).zfill(10)
            if gid:
                lookup[gid] = str(g.get("game_date", ""))
    return lookup


def main():
    date_lookup = build_game_date_lookup()
    print(f"[pf] game_date lookup: {len(date_lookup)} entries")

    # Only the traditional boxscore_<gid>.json — not boxscore_adv_*.json (those
    # don't carry raw PF; they're advanced rates).
    files = [
        p for p in glob.glob(os.path.join(_NBA_CACHE, "boxscore_*.json"))
        if "boxscore_adv_" not in os.path.basename(p)
    ]
    print(f"[pf] reading {len(files)} traditional boxscore files")

    rows = []
    skipped_no_date = 0
    skipped_no_players = 0
    for path in files:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        gid = str(data.get("game_id", "")).zfill(10)
        gdate = date_lookup.get(gid, "")
        if not gdate:
            skipped_no_date += 1
        players = data.get("players") or []
        if not players:
            skipped_no_players += 1
            continue
        for p in players:
            pid = p.get("player_id")
            if pid is None:
                continue
            pf_raw = p.get("pf")
            try:
                pf = float(pf_raw) if pf_raw is not None else 0.0
            except (TypeError, ValueError):
                pf = 0.0
            mn_raw = p.get("min")
            try:
                mn = float(mn_raw) if mn_raw is not None else 0.0
            except (TypeError, ValueError):
                mn = 0.0
            rows.append({
                "game_id": gid,
                "player_id": int(pid),
                "team_abbreviation": str(p.get("team_abbreviation", "")),
                "game_date": gdate,
                "pf": pf,
                "min": mn,
            })

    import pandas as pd  # noqa: PLC0415
    df = pd.DataFrame(rows)
    if df.empty:
        print("[pf] no rows produced; bailing")
        return
    # Dedup on (game_id, player_id) — safe even if the same cache is double-listed.
    df = df.drop_duplicates(subset=["game_id", "player_id"], keep="last")
    print(f"[pf] {len(df)} player-game rows; "
          f"skipped {skipped_no_date} games w/o date, "
          f"{skipped_no_players} files w/o players")
    print(f"[pf] unique games: {df['game_id'].nunique()}")
    print(f"[pf] unique players: {df['player_id'].nunique()}")
    if df["game_date"].any():
        nz = df[df["game_date"] != ""]["game_date"]
        if len(nz):
            print(f"[pf] date range: {nz.min()} -> {nz.max()}")
    df.to_parquet(_OUT_PATH, index=False)
    print(f"[pf] wrote {_OUT_PATH}")


if __name__ == "__main__":
    main()
