"""Wave 1 builder: per-team OFFENSE/DEFENSE granularity signal profile.

Sources (all real, schema-verified before writing):
  - data/nba/synergy_offensive_all_{season}.json  — team play-type PPP & freq (OFF)
  - data/nba/synergy_defensive_all_{season}.json  — team play-type PPP allowed & freq (DEF)
  - data/cache/cv_fix/shotloc_regular_season_*.parquet  — player-level shot zones,
      aggregated to team for shot diet (RA / paint-non-RA / mid-range / corner-3 / AB3)
  - data/team_advanced_stats.parquet  — per-game pace, off_rtg, def_rtg, tov_ratio,
      efg_pct (aggregated to season-mean across all available games)

Key signals (registry domain team.offense / team.defense):
  OFF play-type: ppp & freq for 10 play types (Isolation/Transition/PRBallHandler/
    PRRollMan/Postup/Spotup/Handoff/Cut/OffScreen/OffRebound)
  DEF play-type: ppp allowed & freq for same 10 types
  shot_diet: share of FGA from RA / paint-non-RA / mid-range / corner-3 / above-break-3
  pace: season-mean possessions proxy (team_advanced_stats.pace)
  off_efg_pct, off_rtg, def_rtg, tov_ratio: season-mean from team_advanced_stats
  late_clock_ppp: NOT available at team level in current data — listed in gaps

Leak rule: season-aggregate (scouting-only, consumer A/C). No per-game shifting needed
because entity is team-season (no overlapping bet path). Label: leak_rule="season-agg".

  python scripts/signals/build_team_offdef.py
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NBA_DIR = os.path.join(ROOT, "data", "nba")
SHOTLOC_GLOB = os.path.join(ROOT, "data", "cache", "cv_fix", "shotloc_regular_season_*.parquet")
TAS_PATH = os.path.join(ROOT, "data", "team_advanced_stats.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "team_offdef.parquet")

SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]

PLAY_TYPES = [
    "Isolation", "Transition", "PRBallHandler", "PRRollMan",
    "Postup", "Spotup", "Handoff", "Cut", "OffScreen", "OffRebound",
]

# Compact key names for play-type columns
PT_KEY = {
    "Isolation": "iso",
    "Transition": "trans",
    "PRBallHandler": "pnrh",
    "PRRollMan": "pnrr",
    "Postup": "post",
    "Spotup": "spotup",
    "Handoff": "handoff",
    "Cut": "cut",
    "OffScreen": "offscr",
    "OffRebound": "offreb",
}

SHOTZONE_FGA = [
    "Restricted Area|FGA",
    "In The Paint (Non-RA)|FGA",
    "Mid-Range|FGA",
    "Corner 3|FGA",
    "Above the Break 3|FGA",
]
SHOTZONE_FGM = [
    "Restricted Area|FGM",
    "In The Paint (Non-RA)|FGM",
    "Mid-Range|FGM",
    "Corner 3|FGM",
    "Above the Break 3|FGM",
]
ZONE_KEYS = ["ra", "paint_non_ra", "midrange", "corner3", "ab3"]


# ── synergy helpers ──────────────────────────────────────────────────────────


def _load_synergy(side: str, season: str) -> pd.DataFrame:
    """Load one synergy_{side}_all_{season}.json; return empty DF if absent."""
    path = os.path.join(NBA_DIR, f"synergy_{side}_all_{season}.json")
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    df = pd.DataFrame(rows)
    df["season"] = season
    return df


def _pivot_synergy(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Pivot play-type rows into one wide row per team with ppp/freq columns."""
    if df.empty:
        return pd.DataFrame()
    records = []
    for tri, g in df.groupby("team_abbreviation"):
        rec: dict = {"team_tricode": tri}
        for _, row in g.iterrows():
            pt = row["play_type"]
            key = PT_KEY.get(pt)
            if key is None:
                continue
            rec[f"{prefix}_{key}_ppp"] = round(float(row["ppp"]), 3)
            rec[f"{prefix}_{key}_freq"] = round(float(row["freq_pct"]), 3)
            rec[f"{prefix}_{key}_efg"] = round(float(row.get("efg_pct", np.nan)), 3)
        records.append(rec)
    return pd.DataFrame(records)


def build_synergy_season(season: str) -> pd.DataFrame:
    """Return wide row per team for OFF + DEF play-type signals, one season."""
    off_raw = _load_synergy("offensive", season)
    def_raw = _load_synergy("defensive", season)
    off_wide = _pivot_synergy(off_raw, "off")
    def_wide = _pivot_synergy(def_raw, "def")

    if off_wide.empty and def_wide.empty:
        return pd.DataFrame()
    if off_wide.empty:
        merged = def_wide
    elif def_wide.empty:
        merged = off_wide
    else:
        merged = off_wide.merge(def_wide, on="team_tricode", how="outer")
    merged["season"] = season
    return merged


# ── shot diet helper ─────────────────────────────────────────────────────────


def build_shot_diet() -> pd.DataFrame:
    """Aggregate player-level shotloc to team shot diet for 2025-26 season.

    Uses the latest available shotloc file (most complete 2025-26 snapshot).
    Only the most recent file is used to avoid double-counting cumulative stats.
    """
    files = sorted(glob.glob(SHOTLOC_GLOB))
    if not files:
        return pd.DataFrame()
    latest = files[-1]  # most complete 2025-26 snapshot
    sl = pd.read_parquet(latest)

    # Aggregate FGM/FGA to team by summing player-season cumulative counts
    agg_fga = sl.groupby("TEAM_ABBREVIATION")[SHOTZONE_FGA].sum()
    agg_fgm = sl.groupby("TEAM_ABBREVIATION")[SHOTZONE_FGM].sum()
    total_fga = agg_fga.sum(axis=1).replace(0, np.nan)

    rows = []
    for tri in agg_fga.index:
        t_fga = agg_fga.loc[tri]
        t_fgm = agg_fgm.loc[tri]
        tot = total_fga.loc[tri]
        rec: dict = {"team_tricode": tri, "season": "2025-26"}
        for fga_col, fgm_col, key in zip(SHOTZONE_FGA, SHOTZONE_FGM, ZONE_KEYS):
            fga = float(t_fga[fga_col])
            fgm = float(t_fgm[fgm_col])
            rec[f"shot_share_{key}"] = round(fga / tot, 3) if tot else None
            rec[f"fg_pct_{key}"] = round(fgm / fga, 3) if fga > 0 else None
        # Derived: 3PA share = corner3 + ab3
        c3 = rec.get("shot_share_corner3") or 0.0
        ab3 = rec.get("shot_share_ab3") or 0.0
        rec["shot_share_3pt"] = round(c3 + ab3, 3)
        rec["shot_share_paint"] = round(
            (rec.get("shot_share_ra") or 0.0) + (rec.get("shot_share_paint_non_ra") or 0.0),
            3,
        )
        rows.append(rec)
    return pd.DataFrame(rows)


# ── team_advanced_stats helper ───────────────────────────────────────────────

# Map calendar year-month to NBA season string
def _infer_season(game_date: pd.Series) -> pd.Series:
    """Infer season label from game_date (YYYY-MM-DD)."""
    yr = game_date.str[:4].astype(int)
    mo = game_date.str[5:7].astype(int)
    # Oct-Dec of year Y → Y-(Y+1) season; Jan-Jun → (Y-1)-Y
    season_start = yr.where(mo >= 10, yr - 1)
    season_end = (season_start + 1).astype(str).str[-2:]
    return season_start.astype(str) + "-" + season_end


def build_tas_agg() -> pd.DataFrame:
    """Season-mean pace/ratings/tov per team from team_advanced_stats."""
    tas = pd.read_parquet(TAS_PATH)
    tas["season"] = _infer_season(tas["game_date"])
    agg = (
        tas.groupby(["team_tricode", "season"])
        .agg(
            pace=("pace", "mean"),
            off_rtg=("off_rtg", "mean"),
            def_rtg=("def_rtg", "mean"),
            tov_ratio=("tov_ratio", "mean"),
            oreb_pct=("oreb_pct", "mean"),
            dreb_pct=("dreb_pct", "mean"),
            ast_pct=("ast_pct", "mean"),
            efg_pct=("efg_pct", "mean"),
            ts_pct=("ts_pct", "mean"),
            n_games=("game_id", "count"),
        )
        .reset_index()
    )
    for col in ["pace", "off_rtg", "def_rtg", "tov_ratio", "oreb_pct",
                "dreb_pct", "ast_pct", "efg_pct", "ts_pct"]:
        agg[col] = agg[col].round(3)
    return agg


# ── main build ───────────────────────────────────────────────────────────────


def build() -> pd.DataFrame:
    # 1. Synergy play-type signals — all seasons
    syn_frames = []
    for s in SEASONS:
        f = build_synergy_season(s)
        if not f.empty:
            syn_frames.append(f)
    if not syn_frames:
        raise RuntimeError("No synergy JSON files found — check data/nba/ directory.")
    syn = pd.concat(syn_frames, ignore_index=True)

    # 2. Team advanced stats (pace / ratings) — all seasons
    tas = build_tas_agg()

    # 3. Merge synergy + TAS on (team_tricode, season)
    out = syn.merge(tas, on=["team_tricode", "season"], how="left")

    # Sanity: no cartesian blowup — rows should equal n_teams * n_seasons max
    n_teams = out["team_tricode"].nunique()
    n_seasons = out["season"].nunique()
    assert len(out) <= n_teams * n_seasons + 2, (
        f"Row count {len(out)} unexpectedly exceeds {n_teams}*{n_seasons}. "
        "Check for duplicate team-season rows in synergy or TAS."
    )

    # 4. Shot diet — 2025-26 only; merge in
    diet = build_shot_diet()
    if not diet.empty:
        out = out.merge(diet, on=["team_tricode", "season"], how="left")

    # 5. League percentile ranks within each season for key metrics (OFF)
    for metric in ["off_iso_ppp", "off_pnrh_ppp", "off_trans_ppp", "off_spotup_ppp",
                   "off_cut_ppp", "pace", "off_rtg", "def_rtg"]:
        if metric in out.columns:
            out[f"{metric}_pctile"] = out.groupby("season")[metric].rank(
                pct=True, ascending=(metric != "def_rtg")
            ).mul(100).round(0)

    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)
    n_teams = out["team_tricode"].nunique()
    print(f"DONE: team_offdef signals -> {OUT}")
    print(f"  rows={len(out)}  distinct teams={n_teams}  seasons={sorted(out['season'].unique())}")
    print(f"  columns ({len(out.columns)}): {list(out.columns)}")
    print()
    # 3 sample rows
    print("=== 3 sample rows ===")
    cols_show = ["team_tricode", "season", "off_iso_ppp", "off_pnrh_ppp",
                 "off_trans_ppp", "def_iso_ppp", "def_pnrh_ppp", "pace", "off_rtg", "def_rtg"]
    cols_show = [c for c in cols_show if c in out.columns]
    print(out[cols_show].head(3).to_string(index=False))
    print()
    # Sanity ranking: 2025-26 teams by offensive PnR-handler PPP
    s26 = out[out["season"] == "2025-26"].copy()
    if "off_pnrh_ppp" in s26.columns:
        top = s26.nlargest(8, "off_pnrh_ppp")[["team_tricode", "off_pnrh_ppp", "off_pnrh_freq", "pace"]]
        print("Top 8 teams 2025-26 by OFF PnR-handler PPP:")
        for r in top.itertuples(index=False):
            print(f"  {r.team_tricode:4s}  pnrh_ppp={r.off_pnrh_ppp:.3f}  freq={r.off_pnrh_freq:.2%}  pace={r.pace:.1f}")
    print()
    # Sanity: best defensive teams by ISO PPP allowed (lowest = best)
    if "def_iso_ppp" in s26.columns:
        best_def = s26.nsmallest(5, "def_iso_ppp")[["team_tricode", "def_iso_ppp", "def_rtg"]]
        print("Best 5 ISO defenders 2025-26 (lowest def_iso_ppp):")
        for r in best_def.itertuples(index=False):
            print(f"  {r.team_tricode:4s}  def_iso_ppp={r.def_iso_ppp:.3f}  def_rtg={r.def_rtg:.1f}")


if __name__ == "__main__":
    main()
