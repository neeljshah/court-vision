"""Wave 1 proof builder: per-player DEFENSIVE matchup signal profile.

Reads data/cache/coverage_faced_allseasons.parquet (291k off×def×season rows) and
emits one wide row per (defender, season) with metrics that DON'T exist in the notes
today. The current "As a defender" block shows only raw pts/FG% allowed. This adds the
metric that actually measures defense: performance RELATIVE TO each assignment's own
scoring baseline that season.

Key signals (registry domain player.defense):
  stops_index   = allowed_ppp / expected_ppp        (<1.0 = suppresses offense)
  fg_suppression= allowed_fg%  / expected_fg%        (<1.0 = lowers shooting)
  ppp_allowed, fg3_allowed, poss_defended, n_assignments (versatility)
  switch_rate, block_rate, foul_rate (per 100 poss)
  top_shutdowns / got_cooked_by  (named extremes, >=MIN_POSS)

Expected baselines are possession-weighted over each assignment's season-wide PPP/FG%
across ALL defenders, so the index isolates THIS defender's effect from who he guarded.

This is a season-aggregate SCOUTING signal (consumer C, no overfit risk). A leak-free
as-of-date variant would be needed before feeding the point model.

  python scripts/signals/build_defense_matchup.py
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(ROOT, "data", "cache", "coverage_faced_allseasons.parquet")
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "defense_matchup.parquet")
MIN_POSS_NAMED = 18.0   # threshold for naming an individual shutdown/cooked matchup


def _off_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Per (season, off_player) season-wide PPP and FG% across all defenders."""
    g = df.groupby(["season", "off_player_id"]).agg(
        pts=("pts", "sum"), poss=("poss", "sum"),
        fgm=("fgm", "sum"), fga=("fga", "sum")).reset_index()
    g["base_ppp"] = g.pts / g.poss.replace(0, np.nan)
    g["base_fg"] = g.fgm / g.fga.replace(0, np.nan)
    return g[["season", "off_player_id", "base_ppp", "base_fg"]]


def build() -> pd.DataFrame:
    df = pd.read_parquet(MATRIX)
    base = _off_baselines(df)
    df = df.merge(base, on=["season", "off_player_id"], how="left")
    # expected = what each assignment normally produces, weighted by poss faced here
    df["exp_pts"] = df.base_ppp * df.poss
    df["exp_fgm"] = df.base_fg * df.fga

    rows = []
    for (season, did), g in df.groupby(["season", "def_player_id"]):
        poss = float(g.poss.sum())
        if poss < 5:
            continue
        fga = float(g.fga.sum())
        exp_pts = float(g.exp_pts.sum())
        exp_fgm = float(g.exp_fgm.sum())
        allowed_ppp = float(g.pts.sum()) / poss
        exp_ppp = exp_pts / poss if poss else 0.0
        stops_index = (allowed_ppp / exp_ppp) if exp_ppp else None
        allowed_fg = float(g.fgm.sum()) / fga if fga else None
        exp_fg = (exp_fgm / fga) if fga else None
        fg_suppression = (allowed_fg / exp_fg) if (allowed_fg is not None and exp_fg) else None
        fg3a = float(g.fg3a.sum())
        fg3_allowed = float(g.fg3m.sum()) / fg3a if fg3a else None

        named = g[g.poss >= MIN_POSS_NAMED].copy()
        named["ppp"] = named.pts / named.poss.replace(0, np.nan)
        named["rel"] = pd.to_numeric(named.ppp / named.base_ppp.replace(0, np.nan), errors="coerce")
        # points_saved vs baseline drives notability: holding a real scorer below his
        # norm ranks above holding a non-scorer to zero (avoids uninformative 0.00 ties).
        named["pts_saved"] = pd.to_numeric(named.exp_pts - named.pts, errors="coerce")
        named = named.dropna(subset=["rel", "pts_saved"])
        shutdowns = named.nlargest(5, "pts_saved")[["off_player_name", "rel"]]
        cooked = named.nsmallest(5, "pts_saved")[["off_player_name", "rel"]]

        rows.append({
            "season": season,
            "def_player_id": int(did),
            "def_player_name": g.def_player_name.iloc[0],
            "poss_defended": round(poss, 1),
            "n_assignments": int((g.poss >= MIN_POSS_NAMED).sum()),
            "n_assignments_any": int(len(g)),
            "ppp_allowed": round(allowed_ppp, 3),
            "expected_ppp": round(exp_ppp, 3),
            "stops_index": round(stops_index, 3) if stops_index is not None else None,
            "fg_allowed": round(allowed_fg, 3) if allowed_fg is not None else None,
            "fg_suppression": round(fg_suppression, 3) if fg_suppression is not None else None,
            "fg3_allowed": round(fg3_allowed, 3) if fg3_allowed is not None else None,
            "switch_per100": round(100 * float(g.switches.sum()) / poss, 2),
            "block_per100": round(100 * float(g.blk.sum()) / poss, 2),
            "foul_per100": round(100 * float(g.sfouls.sum()) / poss, 2),
            "top_shutdowns": "; ".join(f"{r.off_player_name} ({r.rel:.2f})"
                                       for r in shutdowns.itertuples(index=False)),
            "got_cooked_by": "; ".join(f"{r.off_player_name} ({r.rel:.2f})"
                                       for r in cooked.itertuples(index=False)),
        })
    out = pd.DataFrame(rows)
    # league percentile of stops_index within season (1 = best/lowest allowed rel)
    out["stops_pctile"] = out.groupby("season")["stops_index"].rank(pct=True, ascending=False)
    out["stops_pctile"] = (out["stops_pctile"] * 100).round(0)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)
    cov = out.def_player_id.nunique()
    print(f"DONE: defense_matchup signals -> {OUT}")
    print(f"  rows={len(out)}  distinct defenders={cov}  seasons={sorted(out.season.unique())}")
    # sanity: best stoppers 2025-26 by stops_index (min poss 150)
    s = out[(out.season == "2025-26") & (out.poss_defended >= 150)].nsmallest(8, "stops_index")
    print("  Top 2025-26 stoppers (>=150 poss, lowest stops_index):")
    for r in s.itertuples(index=False):
        print(f"    {r.def_player_name:24s} idx={r.stops_index}  ppp_allowed={r.ppp_allowed}  poss={r.poss_defended}")


if __name__ == "__main__":
    main()
