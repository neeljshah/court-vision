"""Go through EVERY game's raw defender-matchup file and build a comprehensive
multi-season head-to-head coverage matrix — the deepest "how players play against
each other" intelligence.

The shipped coverage_faced_matrix.parquet is 2024-25 only and carries pts/FG.
The raw per-game files (data/defender_matchups/raw_<game_id>.json, 2214 games:
2023-24, 2024-25, 2025-26 reg + playoffs) carry the FULL matchup line per
(off_player, def_player): possessions, points, FG/3P/FT, ASSISTS, TURNOVERS,
BLOCKS, shooting fouls, switches.

Aggregates per (off_player_id, def_player_id, season) and writes:
  data/cache/coverage_faced_allseasons.parquet
keyed (season, off_player_id, def_player_id) with summed counting stats + derived
rates + n_games. Read-only except its own parquet.
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "defender_matchups")
OUT = os.path.join(ROOT, "data", "cache", "coverage_faced_allseasons.parquet")

# game_id prefix -> season label
PREFIX_SEASON = {"00223": "2023-24", "00224": "2024-25", "00225": "2025-26",
                 "00423": "2024-PO", "00424": "2025-PO", "00425": "2026-PO"}

SUM_FIELDS = ["partial_possessions", "player_points", "matchup_assists", "matchup_turnovers",
              "matchup_blocks", "matchup_fg_made", "matchup_fg_attempted", "matchup_3pm",
              "matchup_3pa", "matchup_ftm", "matchup_fta", "shooting_fouls", "switches_on"]


def season_of(game_id: str) -> str:
    p = str(game_id)[:5]
    return PREFIX_SEASON.get(p, "other")


def main():
    files = sorted(glob.glob(os.path.join(RAW, "raw_*.json")))
    print(f"reading {len(files)} raw matchup files ...", flush=True)
    agg = defaultdict(lambda: {f: 0.0 for f in SUM_FIELDS} | {"n_games": 0,
          "off_player_name": "", "def_player_name": ""})
    bad = 0
    for i, fp in enumerate(files):
        gid = os.path.basename(fp)[4:].replace(".json", "")
        season = season_of(gid)
        try:
            recs = json.load(open(fp, encoding="utf-8"))
        except Exception:
            bad += 1
            continue
        for r in recs:
            try:
                key = (season, int(r["off_player_id"]), int(r["def_player_id"]))
            except (KeyError, TypeError, ValueError):
                continue
            a = agg[key]
            a["n_games"] += 1
            a["off_player_name"] = r.get("off_player_name", a["off_player_name"])
            a["def_player_name"] = r.get("def_player_name", a["def_player_name"])
            for f in SUM_FIELDS:
                try:
                    a[f] += float(r.get(f) or 0)
                except (TypeError, ValueError):
                    pass
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(files)} files, {len(agg)} pairs", flush=True)

    rows = []
    for (season, off_id, def_id), a in agg.items():
        poss = a["partial_possessions"]
        fga = a["matchup_fg_attempted"]
        fg3a = a["matchup_3pa"]
        rows.append({
            "season": season, "off_player_id": off_id, "def_player_id": def_id,
            "off_player_name": a["off_player_name"], "def_player_name": a["def_player_name"],
            "n_games": a["n_games"], "poss": round(poss, 1),
            "pts": a["player_points"], "ast": a["matchup_assists"], "tov": a["matchup_turnovers"],
            "blk": a["matchup_blocks"], "fgm": a["matchup_fg_made"], "fga": fga,
            "fg3m": a["matchup_3pm"], "fg3a": fg3a, "ftm": a["matchup_ftm"], "fta": a["matchup_fta"],
            "sfouls": a["shooting_fouls"], "switches": a["switches_on"],
            "pts_per_poss": round(a["player_points"] / poss, 3) if poss > 0 else None,
            "fg_pct": round(a["matchup_fg_made"] / fga, 3) if fga > 0 else None,
            "fg3_pct": round(a["matchup_3pm"] / fg3a, 3) if fg3a > 0 else None,
        })
    df = pd.DataFrame(rows)
    df.to_parquet(OUT, index=False)
    print(f"DONE: {len(df):,} (season,off,def) pairs -> {OUT}  (bad files={bad})", flush=True)
    for s in sorted(df.season.unique()):
        sub = df[df.season == s]
        print(f"  {s}: {len(sub):,} pairs, {sub.off_player_id.nunique()} off, {sub.def_player_id.nunique()} def")


if __name__ == "__main__":
    main()
