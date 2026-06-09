"""Wave 1 builder: 5-man lineup signal profile (entity=lineup, edge=lineup-pregame).

Reads the raw NBA Stats LeagueDashLineups files for each team/season and emits one row
per (team, season, lineup_rank) — the top N 5-man lineups per team sorted by minutes,
with their net/off/def rating, pace, eFG%, AST/TO, and possessions.

Sources:
  primary:  data/nba/lineups/lineup_splits_<TRI>_<season>.json   (30 teams × seasons)
  fallback: data/cache/atlas_team_lineup_synergy.parquet          (pre-parsed combo_5man)

Key signals (registry domain lineup.fivemix):
  net_rating, off_rating, def_rating, pace, efg_pct, ast_to,
  minutes, poss, w_pct, oreb_pct, dreb_pct, tm_tov_pct, ts_pct, pie

Season coverage:
  - 2024-25: full 30 teams from lineup split JSON files.
  - 2025-26: only GSW + LAL from the atlas fallback (thin — minutes-only, no poss/ast_to).
  - Prior seasons (2018-19, 2020-21, 2021-22, 2022-23, 2023-24): present in JSON files
    but this builder focuses on 2024-25 + best-available 2025-26.

Leak rule: SEASON-AGGREGATE — these are full-season box net ratings, suitable for
scouting/intel consumers only (consumer A/B). Label leak_rule='season-agg'.
Do NOT feed directly into a per-game point model (prior-season version is safe).

  python scripts/signals/build_lineup_5man.py
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINEUP_DIR = os.path.join(ROOT, "data", "nba", "lineups")
ATLAS_PATH = os.path.join(ROOT, "data", "cache", "atlas_team_lineup_synergy.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "lineup_5man.parquet")

# Include the top N lineups per (team, season); raise to taste.
TOP_N = 10
# Minimum minutes for a lineup to qualify
MIN_MINUTES = 10.0
# Target season to lead with
PRIMARY_SEASON = "2024-25"


def _round(val: Any, n: int = 1) -> Any:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return round(float(val), n)
    except (TypeError, ValueError):
        return None


def _load_json_file(path: str, season: str, tri: str) -> list[dict]:
    """Parse one lineup_splits JSON and return cleaned rows for that team+season."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list) or not raw:
        return []
    rows = []
    for entry in raw:
        # Only 5-man lineups
        sz = entry.get("lineup_size") or (
            len(entry.get("lineup", [])) if entry.get("lineup") else None
        )
        if sz is not None and int(sz) != 5:
            continue
        minutes = entry.get("min") or entry.get("minutes")
        if not minutes or float(minutes) < MIN_MINUTES:
            continue
        # Lineup identity
        lineup_names = entry.get("lineup") or []
        if not lineup_names:
            grp = entry.get("group_name", "")
            lineup_names = [n.strip() for n in grp.split(" - ")] if grp else []
        group_id = entry.get("group_id", "")

        rows.append({
            "team_tricode": tri,
            "season": season,
            "group_id": group_id,
            "lineup_names": lineup_names,
            "lineup_str": " | ".join(lineup_names),
            "minutes": _round(minutes, 1),
            "poss": _round(entry.get("poss"), 0),
            "gp": _round(entry.get("gp"), 0),
            "w_pct": _round(entry.get("w_pct"), 3),
            "net_rating": _round(entry.get("net_rating") or entry.get("net_rtg"), 1),
            "off_rating": _round(entry.get("off_rating"), 1),
            "def_rating": _round(entry.get("def_rating"), 1),
            "pace": _round(entry.get("pace") or entry.get("e_pace"), 1),
            "efg_pct": _round(entry.get("efg_pct"), 3),
            "ts_pct": _round(entry.get("ts_pct"), 3),
            "ast_to": _round(entry.get("ast_to"), 2),
            "oreb_pct": _round(entry.get("oreb_pct"), 3),
            "dreb_pct": _round(entry.get("dreb_pct"), 3),
            "tm_tov_pct": _round(entry.get("tm_tov_pct"), 3),
            "pie": _round(entry.get("pie"), 3),
        })
    return rows


def _load_atlas_fallback(season: str) -> list[dict]:
    """Load thin atlas data for seasons not covered by JSON files (e.g. 2025-26 partial)."""
    if not os.path.exists(ATLAS_PATH):
        return []
    atlas = pd.read_parquet(ATLAS_PATH)
    subset = atlas[atlas["lineup_season"] == season].copy()
    rows = []
    for _, row in subset.iterrows():
        tri = row["team_tricode"]
        combo_raw = row.get("combo_5man")
        if not combo_raw or combo_raw in (None, "null", "[]", ""):
            continue
        try:
            lineups = json.loads(combo_raw) if isinstance(combo_raw, str) else combo_raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(lineups, list):
            continue
        for lu in lineups:
            lineup_names = lu.get("lineup", [])
            minutes = lu.get("minutes")
            if not minutes or float(minutes) < MIN_MINUTES:
                continue
            rows.append({
                "team_tricode": tri,
                "season": season,
                "group_id": "",
                "lineup_names": lineup_names,
                "lineup_str": " | ".join(lineup_names) if lineup_names else "",
                "minutes": _round(minutes, 1),
                "poss": _round(lu.get("poss"), 0),
                "gp": None,
                "w_pct": None,
                "net_rating": _round(lu.get("net_rating"), 1),
                "off_rating": _round(lu.get("off_rating"), 1),
                "def_rating": _round(lu.get("def_rating"), 1),
                "pace": _round(lu.get("pace"), 1),
                "efg_pct": _round(lu.get("efg_pct"), 3),
                "ts_pct": None,
                "ast_to": _round(lu.get("ast_to"), 2),
                "oreb_pct": None,
                "dreb_pct": None,
                "tm_tov_pct": None,
                "pie": None,
            })
    return rows


def build() -> pd.DataFrame:
    all_rows: list[dict] = []

    # --- Primary: raw JSON files (all seasons present) ---
    json_files = glob.glob(os.path.join(LINEUP_DIR, "lineup_splits_*_*.json"))
    covered_team_seasons: set[tuple[str, str]] = set()

    for path in sorted(json_files):
        fname = os.path.basename(path)
        parts = fname.replace(".json", "").split("_")
        # Expected: lineup_splits_<TRI>_<season>
        if len(parts) < 4:
            continue
        tri = parts[2]
        season = parts[3]
        rows = _load_json_file(path, season, tri)
        all_rows.extend(rows)
        if rows:
            covered_team_seasons.add((tri, season))

    # --- Fallback: atlas for 2025-26 teams not in JSON files ---
    fallback_rows = _load_atlas_fallback("2025-26")
    for r in fallback_rows:
        key = (r["team_tricode"], r["season"])
        if key not in covered_team_seasons:
            all_rows.append(r)

    df = pd.DataFrame(all_rows)
    if df.empty:
        raise RuntimeError("No lineup rows loaded — check data paths.")

    # Sort by (team, season, minutes desc) and assign rank within each group
    df = df.sort_values(["team_tricode", "season", "minutes"], ascending=[True, True, False])
    df["lineup_rank"] = df.groupby(["team_tricode", "season"]).cumcount() + 1

    # Keep only top N per team×season
    df = df[df["lineup_rank"] <= TOP_N].reset_index(drop=True)

    # Closing-lineup flag: rank==1 (most-minutes unit, best proxy for closing unit)
    df["is_top_unit"] = df["lineup_rank"] == 1

    # Net-rating tier label for quick scouting
    def _tier(net):
        if net is None or (isinstance(net, float) and np.isnan(net)):
            return "unknown"
        if net >= 15:
            return "elite"
        if net >= 5:
            return "good"
        if net >= -5:
            return "average"
        return "poor"

    df["net_rating_tier"] = df["net_rating"].apply(_tier)

    # Reorder columns sensibly
    col_order = [
        "team_tricode", "season", "lineup_rank", "is_top_unit",
        "lineup_str", "lineup_names",
        "minutes", "poss", "gp", "w_pct",
        "net_rating", "off_rating", "def_rating", "net_rating_tier",
        "pace", "efg_pct", "ts_pct", "ast_to",
        "oreb_pct", "dreb_pct", "tm_tov_pct", "pie",
        "group_id",
    ]
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    return df


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = build()
    df.to_parquet(OUT, index=False)

    seasons = sorted(df["season"].unique())
    n_team_seasons = df.groupby(["team_tricode", "season"]).ngroups
    print(f"DONE: lineup_5man signals -> {OUT}")
    print(f"  rows={len(df)}  team-season groups={n_team_seasons}  seasons={seasons}")

    # Sanity: top lineup per team for PRIMARY_SEASON
    top1 = df[(df["season"] == PRIMARY_SEASON) & (df["lineup_rank"] == 1)].copy()
    top1 = top1.sort_values("net_rating", ascending=False, na_position="last")
    print(f"\n  Best #1 lineups by net_rating ({PRIMARY_SEASON}, min>={MIN_MINUTES}min):")
    for r in top1.head(8).itertuples(index=False):
        poss_str = f"poss={int(r.poss)}" if r.poss is not None else "poss=?"
        safe_lineup = r.lineup_str[:50].encode("ascii", "replace").decode("ascii")
        print(
            f"    {r.team_tricode:4s}  net={r.net_rating:+.1f} ({r.net_rating_tier})"
            f"  off={r.off_rating}  def={r.def_rating}"
            f"  {poss_str}  min={r.minutes}"
            f"  [{safe_lineup}]"
        )

    # Three sample rows for the verifier
    print("\n  3 sample rows:")
    print(df[["team_tricode", "season", "lineup_rank", "net_rating", "minutes", "lineup_str"]].head(3).to_string(index=False))


if __name__ == "__main__":
    main()
