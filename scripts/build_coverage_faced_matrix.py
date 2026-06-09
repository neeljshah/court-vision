"""build_coverage_faced_matrix.py — OFFENSIVE-player-keyed coverage matrix.

Offensive complement to data/defender_matchups_2024-25.parquet (defender-keyed).
For each OFFENSIVE player, aggregates across games which DEFENDERS guarded them,
how many matchup minutes / partial possessions, and how the offensive player
shot WHEN guarded by each defender.

Reuses the per-game raw cache produced by fetch_defender_matchup.py
(data/defender_matchups/raw_<game_id>.json). Each raw record is a single
(offensive player x defensive player x game) row already parsed into our schema.
This script does NOT re-fetch from the NBA API when the cache is present — it
re-aggregates the same 500-game 2024-25 universe the defender file used, just
keyed by the offensive player instead of the defender.

Output (LONG, one row per off_player x def_player pair):
    off_player_id, off_player_name, def_player_id, def_player_name, season,
    n_games_matched, matchup_minutes_total, partial_possessions,
    off_points, off_fgm, off_fga, off_fg3m, off_fg3a, off_fg_pct, off_fg3_pct

Writes EXACTLY: data/cache/coverage_faced_matrix.parquet
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Headers patch — only matters if a cache miss forces a live fetch.
try:  # pragma: no cover
    from src.data import nba_api_headers_patch  # noqa: F401
except Exception:
    pass

# Reuse the proven per-game fetch+parse (cache-first) from the defender script.
from scripts.fetch_defender_matchup import fetch_game_matchups, _flt, _int

SEASON = "2024-25"
# Exact universe the defender-keyed file used: 0022400001 .. 0022400500.
GAME_IDS = [f"00224{i:05d}" for i in range(1, 501)]

OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "coverage_faced_matrix.parquet")


def build() -> Dict[str, Any]:
    # key: (off_player_id, def_player_id) -> aggregate dict
    pairs: Dict[tuple, Dict[str, Any]] = {}
    games_processed = 0
    games_empty = 0

    for n, gid in enumerate(GAME_IDS, 1):
        raw = fetch_game_matchups(gid)  # cache-first; returns [] on miss/error
        if not raw:
            games_empty += 1
            continue
        games_processed += 1

        # Track which (off,def) pairs appeared in THIS game so n_games_matched
        # counts distinct games, not raw rows.
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
            # Backfill names if an earlier row had blanks.
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

        if n % 50 == 0:
            print(f"[coverage] {n}/{len(GAME_IDS)} games scanned "
                  f"({len(pairs)} pairs so far)")

    rows: List[Dict[str, Any]] = []
    for agg in pairs.values():
        fga = agg["off_fga"]
        fg3a = agg["off_fg3a"]
        agg["off_fg_pct"]  = round(agg["off_fgm"] / fga, 4) if fga else 0.0
        agg["off_fg3_pct"] = round(agg["off_fg3m"] / fg3a, 4) if fg3a else 0.0
        agg["matchup_minutes_total"] = round(agg["matchup_minutes_total"], 3)
        agg["partial_possessions"]   = round(agg["partial_possessions"], 2)
        rows.append(agg)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    import pandas as pd
    df = pd.DataFrame(rows)
    # Column order
    cols = [
        "off_player_id", "off_player_name", "def_player_id", "def_player_name",
        "season", "n_games_matched", "matchup_minutes_total",
        "partial_possessions", "off_points", "off_fgm", "off_fga",
        "off_fg3m", "off_fg3a", "off_fg_pct", "off_fg3_pct",
    ]
    df = df[cols]
    df.to_parquet(OUT_PATH, index=False)

    return {
        "out_path": OUT_PATH,
        "total_rows": len(df),
        "distinct_off": int(df["off_player_id"].nunique()),
        "distinct_pairs": int(len(df)),
        "games_processed": games_processed,
        "games_empty": games_empty,
        "games_total": len(GAME_IDS),
        "df": df,
    }


if __name__ == "__main__":
    res = build()
    df = res.pop("df")
    print("\n=== COVERAGE-FACED MATRIX ===")
    print(f"path           : {res['out_path']}")
    print(f"season         : {SEASON}")
    print(f"games processed: {res['games_processed']}/{res['games_total']} "
          f"(empty/missing: {res['games_empty']})")
    print(f"total rows     : {res['total_rows']}")
    print(f"distinct off   : {res['distinct_off']}")
    print(f"distinct pairs : {res['distinct_pairs']}")

    # Sanity readout for a star.
    for star_id, star_name in [(1628983, "SGA"), (203999, "Jokic")]:
        sub = df[df["off_player_id"] == star_id]
        if sub.empty:
            print(f"\n[sanity] {star_name} ({star_id}): no rows")
            continue
        top = sub.sort_values("matchup_minutes_total", ascending=False).head(5)
        print(f"\n[sanity] {star_name} ({star_id}) top-5 defenders by matchup minutes:")
        for _, r in top.iterrows():
            nm = (r["def_player_name"] or "").encode(
                sys.stdout.encoding or "utf-8", errors="replace"
            ).decode(sys.stdout.encoding or "utf-8", errors="replace")
            print(f"  {nm:<24} min={r['matchup_minutes_total']:6.1f}  "
                  f"games={int(r['n_games_matched']):2d}  "
                  f"fga={int(r['off_fga']):3d}  fg%={r['off_fg_pct']:.3f}  "
                  f"pts={int(r['off_points']):3d}")
