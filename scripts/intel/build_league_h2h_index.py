"""League-wide head-to-head intelligence from the multi-season coverage matrix.
Writes NEW vault notes (no collision with the per-player scouting fan-out):

  vault/Intelligence/Scouts/_Stopper_Index_<season>.md  — best perimeter/rim
     defenders ranked by points-allowed-per-possession (+ who they shut down).
  vault/Intelligence/Matchups/_Lockdown_And_Feast_<season>.md — the most extreme
     individual matchups: defenders who hold a scorer far below his baseline
     pts/poss ("lockdowns"), and scorers who torch a specific defender ("feasts").

"How players play against each other" at the league level. Read-only except notes.
Run: python scripts/intel/build_league_h2h_index.py [--season 2025-26]
"""
from __future__ import annotations

import argparse
import os
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MATRIX = os.path.join(ROOT, "data", "cache", "coverage_faced_allseasons.parquet")
SCOUTS = os.path.join(ROOT, "vault", "Intelligence", "Scouts")
MATCHUPS = os.path.join(ROOT, "vault", "Intelligence", "Matchups")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="2025-26")
    ap.add_argument("--min-def-poss", type=float, default=150.0)
    ap.add_argument("--min-pair-poss", type=float, default=20.0)
    args = ap.parse_args()
    df = pd.read_parquet(MATRIX)
    df = df[df.season == args.season].copy()
    if df.empty:
        print(f"no rows for {args.season}"); return
    os.makedirs(SCOUTS, exist_ok=True); os.makedirs(MATCHUPS, exist_ok=True)

    # ---- Stopper Index: aggregate per defender ----
    g = df.groupby(["def_player_id", "def_player_name"]).agg(
        poss=("poss", "sum"), pts=("pts", "sum"), fgm=("fgm", "sum"), fga=("fga", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"), ast=("ast", "sum"), tov=("tov", "sum"),
        blk=("blk", "sum"), assignments=("off_player_id", "nunique")).reset_index()
    g = g[g.poss >= args.min_def_poss].copy()
    g["pts_per_poss_allowed"] = g.pts / g.poss
    g["fg_pct_allowed"] = g.fgm / g.fga.replace(0, np.nan)
    g["fg3_pct_allowed"] = g.fg3m / g.fg3a.replace(0, np.nan)
    g = g.sort_values("pts_per_poss_allowed")
    lg_ppp = (g.pts.sum() / g.poss.sum())

    L = [f"# Stopper Index — {args.season}",
         f"> Defenders ranked by points allowed per matchup-possession (min {args.min_def_poss:.0f} poss). "
         f"League avg ≈ {lg_ppp:.3f} pts/poss. Lower = stingier. From raw defender-matchup files (game-by-game).", ""]
    L.append("## Top 30 stoppers (lowest pts/poss allowed)")
    L.append("| # | Defender | Poss | Pts/Poss | FG% allowed | 3P% allowed | Assign. |")
    L.append("|--|---|--|--|--|--|--|")
    for i, r in enumerate(g.head(30).itertuples(index=False), 1):
        # top shutdown assignment for this defender
        sub = df[(df.def_player_id == r.def_player_id) & (df.poss >= args.min_pair_poss)]
        L.append(f"| {i} | {r.def_player_name} | {r.poss:.0f} | {r.pts_per_poss_allowed:.3f} | "
                 f"{'' if pd.isna(r.fg_pct_allowed) else int(r.fg_pct_allowed*100)} | "
                 f"{'' if pd.isna(r.fg3_pct_allowed) else int(r.fg3_pct_allowed*100)} | {r.assignments} |")
    L.append("\n## Most-exploited defenders (highest pts/poss allowed, min poss)")
    L.append("| # | Defender | Poss | Pts/Poss | FG% allowed |")
    L.append("|--|---|--|--|--|")
    for i, r in enumerate(g.sort_values("pts_per_poss_allowed", ascending=False).head(20).itertuples(index=False), 1):
        L.append(f"| {i} | {r.def_player_name} | {r.poss:.0f} | {r.pts_per_poss_allowed:.3f} | "
                 f"{'' if pd.isna(r.fg_pct_allowed) else int(r.fg_pct_allowed*100)} |")
    open(os.path.join(SCOUTS, f"_Stopper_Index_{args.season}.md"), "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote Stopper Index ({len(g)} qualified defenders)")

    # ---- Lockdown & Feast: per-pair vs scorer baseline ----
    # baseline pts/poss per offensive player this season
    obase = df.groupby("off_player_id").agg(opts=("pts", "sum"), oposs=("poss", "sum")).reset_index()
    obase["base_ppp"] = obase.opts / obase.oposs.replace(0, np.nan)
    obase = obase[obase.oposs >= 200]  # established scorers
    bmap = dict(zip(obase.off_player_id, obase.base_ppp))
    pair = df[df.poss >= args.min_pair_poss].copy()
    pair["base_ppp"] = pair.off_player_id.map(bmap)
    pair = pair.dropna(subset=["base_ppp"])
    pair["rel"] = pair.pts_per_poss / pair.base_ppp
    pair = pair[pair.base_ppp >= 0.30]  # above-average scorers (league matchup ppp ~0.24)
    pair = pair[pair.n_games >= 3]      # >=3 meetings: cut singleton noise (matchups are sparse)

    M = [f"# Lockdown & Feast Matchups — {args.season}",
         f"> Individual matchups (min {args.min_pair_poss:.0f} poss, ≥3 meetings) where a defender most suppresses "
         f"(or a scorer most torches) relative to the scorer's own season pts/poss baseline. The detail the box score "
         f"hides. ⚠️ SMALL SAMPLE: individual off-vs-def pairings are sparse (20-60 poss/season); treat the tails as "
         f"leads to investigate, not settled facts. The per-defender Stopper Index is the robust aggregate.", ""]
    lock = pair.sort_values("rel").head(35)
    M.append("## Lockdowns — defender holds the scorer FAR below his baseline")
    M.append("| Scorer | Defender | G | Poss | Pts | Pts/Poss | Baseline | vs base |")
    M.append("|---|---|--|--|--|--|--|--|")
    for r in lock.itertuples(index=False):
        M.append(f"| {r.off_player_name} | {r.def_player_name} | {r.n_games} | {r.poss:.0f} | {int(r.pts)} | "
                 f"{r.pts_per_poss:.2f} | {r.base_ppp:.2f} | {r.rel:.2f} |")
    feast = pair.sort_values("rel", ascending=False).head(35)
    M.append("\n## Feasts — scorer torches a specific defender")
    M.append("| Scorer | Defender | G | Poss | Pts | Pts/Poss | Baseline | vs base |")
    M.append("|---|---|--|--|--|--|--|--|")
    for r in feast.itertuples(index=False):
        M.append(f"| {r.off_player_name} | {r.def_player_name} | {r.n_games} | {r.poss:.0f} | {int(r.pts)} | "
                 f"{r.pts_per_poss:.2f} | {r.base_ppp:.2f} | {r.rel:.2f} |")
    open(os.path.join(MATCHUPS, f"_Lockdown_And_Feast_{args.season}.md"), "w", encoding="utf-8").write("\n".join(M))
    print(f"wrote Lockdown & Feast ({len(pair)} qualified pairs)")


if __name__ == "__main__":
    main()
