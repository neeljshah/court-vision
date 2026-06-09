"""Edge-mining analysis (a): CONDITIONAL ROI GRID + close-game PTS check.

Reads data/cache/edge_mining_bets.parquet (built by edge_mining_systematic.py).

Gate for a candidate cell (disciplined generalization of the AST/pace finding):
  positive on MAIN held-out LATE half  AND  >=1 independent corpus  AND  the
  2024-25 SEASON (or sign-stable, win% > breakeven). |odds|>=100 already applied.

Corpora available after OOF-join (OOF is regular-season only, no playoffs):
  MAIN          benashkar_2526   (2026 Jan-Apr, DK/FD/MGM)  n~4100
  CROSS-SEASON  oddsapi_2425     (2024-25 SEASON)           n~302
  2ND/DIFF-SCR  oddsapi_2526reg  (2025-26 reg, diff scrape) n~277
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
_BETS = _ROOT / "data" / "cache" / "edge_mining_bets.parquet"
_OUT = _ROOT / "data" / "cache" / "edge_mining_grid.json"

MAIN = "benashkar_2526"
SEASON = "oddsapi_2425"
DIFFSCR = "oddsapi_2526reg"

BREAKEVEN = 100.0 / 1.9090909  # ~52.4% at -110; use 52.4 as nominal


def roi(sub) -> dict:
    n = len(sub)
    if n == 0:
        return {"n": 0, "roi": np.nan, "win": np.nan}
    return {"n": int(n), "roi": round(float(sub["pnl"].mean()), 2),
            "win": round(float(sub["won"].mean() * 100), 1)}


def temporal_halves(df):
    """Split MAIN corpus by date median into early/late."""
    d = df.sort_values("gd").reset_index(drop=True)
    cut = pd.to_datetime(d["gd"]).quantile(0.5)
    dts = pd.to_datetime(d["gd"])
    return d[dts <= cut], d[dts > cut]


def main():
    bt = pd.read_parquet(_BETS)
    bt["gd"] = bt["gd"].astype(str)
    main = bt[bt.corpus == MAIN].copy()
    season = bt[bt.corpus == SEASON].copy()
    diffscr = bt[bt.corpus == DIFFSCR].copy()

    early, late = temporal_halves(main)
    print(f"MAIN n={len(main)} early={len(early)} (<= {early['gd'].max()}) "
          f"late={len(late)} (>= {late['gd'].min()})")

    report = {"meta": {
        "main_n": len(main), "early_n": len(early), "late_n": len(late),
        "season_n": len(season), "diffscr_n": len(diffscr),
        "note": "opp_pace/opp_def for 2026 corpora are STALE (carried from end of "
                "2024-25; team_advanced_stats has no 2025-26). Treat pace tercile "
                "on 2026 as last-season pace identity, not in-season pace."}}

    # ── add conditioner buckets ──
    def add_buckets(df):
        df = df.copy()
        # line bucket
        df["line_bucket"] = pd.cut(df["line"], bins=[-1, 2.5, 5.5, 9.5, 14.5, 19.5, 24.5, 999],
                                   labels=["0-2.5", "3-5.5", "6-9.5", "10-14.5",
                                           "15-19.5", "20-24.5", "25+"])
        # minutes tercile (within stat? use global)
        df["min_tier"] = pd.qcut(df["l10_min"].fillna(df["l10_min"].median()),
                                 3, labels=["lowmin", "midmin", "himin"], duplicates="drop")
        # pace tercile
        df["pace_tier"] = pd.qcut(df["opp_pace"].rank(method="first"),
                                  3, labels=["slow", "mid", "fast"], duplicates="drop")
        df["rest_tier"] = np.where(df["rest_days"] <= 1, "b2b/1d",
                                   np.where(df["rest_days"] >= 3, "rest3+", "2d"))
        df["edge_tier"] = np.where(df["abs_edge"] >= 1.5, "edge1.5+",
                                   np.where(df["abs_edge"] >= 1.0, "edge1.0+", "edge<1"))
        df["home"] = np.where(df["is_home"] == 1, "home", "away")
        return df

    early, late, main_b = add_buckets(early), add_buckets(late), add_buckets(main)
    season_b, diffscr_b = add_buckets(season), add_buckets(diffscr)

    CONDS = ["pace_tier", "line_bucket", "min_tier", "rest_tier", "edge_tier", "home"]
    STATS = ["pts", "reb", "ast", "fg3m"]

    grid = []
    for stat in STATS:
        for cond in CONDS:
            for cval in main_b[main_b.stat == stat][cond].dropna().unique():
                def cell(df):
                    return roi(df[(df.stat == stat) & (df[cond] == cval)])
                c_early = cell(early)
                c_late = cell(late)
                c_season = cell(season_b)
                c_diff = cell(diffscr_b)
                # GATE: late>0 AND season>0(or win>52.4) AND (early>0 or diffscr>0)
                late_ok = c_late["n"] >= 20 and c_late["roi"] > 0
                season_ok = (c_season["n"] >= 15 and
                             (c_season["roi"] > 0 or c_season["win"] > 52.4))
                early_ok = c_early["n"] >= 20 and c_early["roi"] > 0
                diff_ok = c_diff["n"] >= 15 and c_diff["roi"] > 0
                passes = late_ok and season_ok and (early_ok or diff_ok)
                grid.append({
                    "stat": stat, "cond": cond, "val": str(cval),
                    "early": c_early, "late": c_late,
                    "season2425": c_season, "diffscr2526": c_diff,
                    "PASS": bool(passes),
                })
    report["grid"] = grid

    # ── print survivors ──
    print("\n" + "=" * 78)
    print("CONDITIONAL GRID SURVIVORS (late>0 & season ok & (early>0 or diffscr>0))")
    print("=" * 78)
    survivors = [g for g in grid if g["PASS"]]
    if not survivors:
        print("  (none)")
    for g in survivors:
        print(f"  {g['stat']:4s} {g['cond']:11s}={g['val']:9s} | "
              f"early {g['early']['roi']:+5.1f}%(n{g['early']['n']}) "
              f"late {g['late']['roi']:+5.1f}%(n{g['late']['n']}) "
              f"season2425 {g['season2425']['roi']:+5.1f}%(n{g['season2425']['n']}) "
              f"diffscr {g['diffscr2526']['roi']:+5.1f}%(n{g['diffscr2526']['n']})")

    # ── per-stat baseline (no conditioner) across all corpora ──
    print("\n" + "=" * 78)
    print("PER-STAT BASELINE across corpora (the reference)")
    print("=" * 78)
    base = {}
    for stat in ["pts", "reb", "ast", "fg3m"]:
        e = roi(early[early.stat == stat]); l = roi(late[late.stat == stat])
        s = roi(season[season.stat == stat]); d = roi(diffscr[diffscr.stat == stat])
        base[stat] = {"early": e, "late": l, "season2425": s, "diffscr2526": d}
        print(f"  {stat:4s} | early {e['roi']:+5.1f}%(n{e['n']}) late {l['roi']:+5.1f}%(n{l['n']}) "
              f"season2425 {s['roi']:+5.1f}%(n{s['n']}) diffscr {d['roi']:+5.1f}%(n{d['n']})")
    report["per_stat_baseline"] = base

    # ── close-game PTS-OVER cross-check ──
    # The in-game hint: PTS systematically UNDER-projects in close games.
    # Pregame proxy: we cannot know final margin pregame, so test whether
    # betting PTS OVER (regardless of model) wins; and whether model-OVER PTS
    # is better than model-UNDER PTS. (HURTS MAE but may win.)
    print("\n" + "=" * 78)
    print("CLOSE-GAME / PTS-OVER cross-check")
    print("=" * 78)
    cg = {}
    for label, df in [("MAIN", main), ("season2425", season), ("diffscr2526", diffscr)]:
        p = df[df.stat == "pts"]
        over = p[p.bet_over]
        under = p[~p.bet_over]
        # blind OVER (ignore model): bet over on every pts line
        blind_over_win = ((p["actual"] > p["line"]).mean() * 100) if len(p) else np.nan
        cg[label] = {
            "model_over": roi(over), "model_under": roi(under),
            "blind_over_winpct": round(float(blind_over_win), 1) if len(p) else None,
        }
        print(f"  {label:11s} | model-OVER {roi(over)} | model-UNDER {roi(under)} | "
              f"blind-over win% {cg[label]['blind_over_winpct']}")
    report["close_game_pts"] = cg

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(_OUT, "w"), indent=2, default=str)
    print(f"\nsaved -> {_OUT.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
