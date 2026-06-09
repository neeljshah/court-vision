"""build_defender_matchups_2025-26.py — refresh defensive-matchup layer to 2025-26.

Fetches BoxScoreMatchupsV3 for every 2025-26 regular-season game (cache-first,
reusing fetch_defender_matchup.py's perpetual per-game raw cache), then produces
TWO parquets with schemas identical to their 2024-25 counterparts:

  data/defender_matchups_2025-26.parquet           (defender-keyed)
  data/cache/coverage_faced_matrix_2025-26.parquet (offense-keyed)

Cache-first: a re-run only re-fetches games whose raw_<gid>.json is missing.
Does NOT overwrite the 2024-25 files. Logs games_processed/total — no silent
truncation.

CLI:
    python scripts/build_defender_matchups_2025-26.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:  # pragma: no cover
    from src.data import nba_api_headers_patch  # noqa: F401
except Exception:
    pass

from scripts.fetch_defender_matchup import (
    fetch_game_matchups,
    summarize_defender,
    _flt,
    _int,
)

SEASON = "2025-26"
SCHEDULE_PATH = os.path.join(PROJECT_DIR, "data", "tmp_2526", "schedule_2025-26.json")
DEFENDER_OUT = os.path.join(PROJECT_DIR, "data", f"defender_matchups_{SEASON}.parquet")
COVERAGE_OUT = os.path.join(PROJECT_DIR, "data", "cache",
                            f"coverage_faced_matrix_{SEASON}.parquet")


def _load_schedule() -> Dict[str, Any]:
    """Load (or build) the 2025-26 regular-season schedule."""
    if os.path.exists(SCHEDULE_PATH):
        with open(SCHEDULE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data
    # Build it fresh.
    from nba_api.stats.endpoints import leaguegamelog
    time.sleep(0.6)
    log = leaguegamelog.LeagueGameLog(
        season=SEASON, season_type_all_star="Regular Season",
        player_or_team_abbreviation="T", timeout=30,
    )
    df = log.get_data_frames()[0]
    gids = sorted({str(g).zfill(10) for g in df["GAME_ID"].tolist()})
    date_lookup = {str(g).zfill(10): str(d)
                   for g, d in zip(df["GAME_ID"], df["GAME_DATE"])}
    os.makedirs(os.path.dirname(SCHEDULE_PATH), exist_ok=True)
    with open(SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump({"game_ids": gids, "date_lookup": date_lookup}, f)
    return {"game_ids": gids, "date_lookup": date_lookup}


def build(limit: int | None = None, delay: float = 0.7) -> Dict[str, Any]:
    sched = _load_schedule()
    game_ids: List[str] = sched["game_ids"]
    date_lookup: Dict[str, str] = sched["date_lookup"]
    total = len(game_ids)
    if limit is not None:
        game_ids = game_ids[:limit]

    defender_rows: List[Dict[str, Any]] = []
    pairs: Dict[tuple, Dict[str, Any]] = {}
    games_processed = 0
    games_empty = 0

    for i, gid in enumerate(game_ids, 1):
        cache_path = os.path.join(PROJECT_DIR, "data", "defender_matchups",
                                  f"raw_{gid}.json")
        had_cache = os.path.exists(cache_path)
        raw = fetch_game_matchups(gid)  # cache-first
        if not had_cache:
            time.sleep(delay)  # only sleep on genuine API hits

        if not raw:
            games_empty += 1
            if i % 50 == 0:
                print(f"[build] {i}/{len(game_ids)} scanned "
                      f"({games_processed} processed, {len(pairs)} pairs)")
            continue
        games_processed += 1

        # ---- defender-keyed summary ----
        summary = summarize_defender(
            raw, game_id=gid, season=SEASON,
            game_date=date_lookup.get(gid, ""),
        )
        defender_rows.extend(summary)

        # ---- offense-keyed pairs ----
        seen_this_game: set = set()
        for m in raw:
            off_raw = m.get("off_player_id")
            def_raw = m.get("def_player_id")
            try:
                if off_raw is None or off_raw != off_raw:
                    continue
                if def_raw is None or def_raw != def_raw:
                    continue
                off_id = int(off_raw)
                def_id = int(def_raw)
            except (TypeError, ValueError):
                continue
            key = (off_id, def_id)
            agg = pairs.setdefault(key, {
                "off_player_id":         off_id,
                "off_player_name":       m.get("off_player_name", "") or "",
                "def_player_id":         def_id,
                "def_player_name":       m.get("def_player_name", "") or "",
                "season":                SEASON,
                "n_games_matched":       0,
                "matchup_minutes_total": 0.0,
                "partial_possessions":   0.0,
                "off_points":            0,
                "off_fgm":               0,
                "off_fga":               0,
                "off_fg3m":              0,
                "off_fg3a":              0,
            })
            if not agg["off_player_name"] and m.get("off_player_name"):
                agg["off_player_name"] = m["off_player_name"]
            if not agg["def_player_name"] and m.get("def_player_name"):
                agg["def_player_name"] = m["def_player_name"]
            agg["matchup_minutes_total"] += _flt(m.get("matchup_minutes_float", 0))
            agg["partial_possessions"]   += _flt(m.get("partial_possessions", 0))
            agg["off_points"]            += _int(m.get("player_points", 0))
            agg["off_fgm"]               += _int(m.get("matchup_fg_made", 0))
            agg["off_fga"]               += _int(m.get("matchup_fg_attempted", 0))
            agg["off_fg3m"]              += _int(m.get("matchup_3pm", 0))
            agg["off_fg3a"]              += _int(m.get("matchup_3pa", 0))
            if key not in seen_this_game:
                agg["n_games_matched"] += 1
                seen_this_game.add(key)

        if i % 50 == 0:
            print(f"[build] {i}/{len(game_ids)} scanned "
                  f"({games_processed} processed, {len(pairs)} pairs)")

    import pandas as pd

    # ---- write defender-keyed parquet ----
    def_cols = [
        "game_id", "game_date", "season", "def_player_id", "def_player_name",
        "def_team_tricode", "matchup_minutes_total", "partial_possessions",
        "points_allowed", "fg_made_allowed", "fg_attempted_allowed",
        "fg3_made_allowed", "fg3_attempted_allowed", "switches_on",
        "blocks_matchup", "help_blocks", "matchups_count",
        "fg_pct_allowed", "fg3_pct_allowed",
    ]
    ddf = pd.DataFrame(defender_rows)
    ddf = ddf[def_cols]
    ddf.to_parquet(DEFENDER_OUT, index=False)

    # ---- write offense-keyed parquet ----
    cov_rows: List[Dict[str, Any]] = []
    for agg in pairs.values():
        fga = agg["off_fga"]
        fg3a = agg["off_fg3a"]
        agg["off_fg_pct"]  = round(agg["off_fgm"] / fga, 4) if fga else 0.0
        agg["off_fg3_pct"] = round(agg["off_fg3m"] / fg3a, 4) if fg3a else 0.0
        agg["matchup_minutes_total"] = round(agg["matchup_minutes_total"], 3)
        agg["partial_possessions"]   = round(agg["partial_possessions"], 2)
        cov_rows.append(agg)
    cov_cols = [
        "off_player_id", "off_player_name", "def_player_id", "def_player_name",
        "season", "n_games_matched", "matchup_minutes_total",
        "partial_possessions", "off_points", "off_fgm", "off_fga",
        "off_fg3m", "off_fg3a", "off_fg_pct", "off_fg3_pct",
    ]
    os.makedirs(os.path.dirname(COVERAGE_OUT), exist_ok=True)
    cdf = pd.DataFrame(cov_rows)
    cdf = cdf[cov_cols]
    cdf.to_parquet(COVERAGE_OUT, index=False)

    return {
        "defender_out": DEFENDER_OUT,
        "coverage_out": COVERAGE_OUT,
        "defender_rows": len(ddf),
        "coverage_rows": len(cdf),
        "distinct_defenders": int(ddf["def_player_id"].nunique()),
        "distinct_off": int(cdf["off_player_id"].nunique()),
        "games_processed": games_processed,
        "games_empty": games_empty,
        "games_total": total,
        "games_attempted": len(game_ids),
        "defender_df": ddf,
        "coverage_df": cdf,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    res = build(limit=args.limit)
    ddf = res.pop("defender_df")
    cdf = res.pop("coverage_df")
    print("\n=== 2025-26 DEFENSIVE-MATCHUP REFRESH ===")
    print(f"defender parquet : {res['defender_out']}")
    print(f"  rows={res['defender_rows']}  distinct_defenders={res['distinct_defenders']}")
    print(f"coverage parquet : {res['coverage_out']}")
    print(f"  rows={res['coverage_rows']}  distinct_off={res['distinct_off']}")
    print(f"games processed  : {res['games_processed']}/{res['games_total']} "
          f"(attempted {res['games_attempted']}, empty/missing {res['games_empty']})")
    print(f"season labels    : def={ddf['season'].unique().tolist()} "
          f"cov={cdf['season'].unique().tolist()}")

    # SGA sanity (coverage-faced: his top defenders)
    sub = cdf[cdf["off_player_id"] == 1628983]
    print("\n[sanity] SGA (1628983) top-3 defenders by matchup minutes:")
    for _, r in sub.sort_values("matchup_minutes_total", ascending=False).head(3).iterrows():
        nm = (r["def_player_name"] or "").encode("ascii", "replace").decode("ascii")
        print(f"  {nm:<24} min={r['matchup_minutes_total']:6.1f} "
              f"games={int(r['n_games_matched']):2d} fga={int(r['off_fga']):3d} "
              f"fg%={r['off_fg_pct']:.3f} pts={int(r['off_points']):3d}")
