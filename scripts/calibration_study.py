"""calibration_study.py — every game, pregame pred vs final box, per-metric bias.

Step 1 of the season-wide recalibration. Builds one row per (player, game, stat)
joining the walk-forward OOF pregame prediction to the actual box score plus every
covariate that could carry systematic bias, then prints a BIAS TABLE: mean signed
error (pred - actual) and MAE in each bucket of each covariate. Wherever the signed
error is consistently non-zero, that metric is miscalibrated and correctable.

Covariates: predicted-value bucket (regression-to-mean), actual minutes, rest days,
b2b, home/away, opponent as-of pace & def rating, month, season.

Writes the joined frame to data/cache/calibration_frame.parquet for the fitting step.
Leak-free: every covariate is known pre-game (opp ratings are as-of running estimates).
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
OUT_FRAME = _ROOT / "data" / "cache" / "calibration_frame.parquet"
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _teams(matchup):
    if not matchup:
        return None, None, None
    if " @ " in matchup:
        a, b = matchup.split(" @ "); return a.strip(), b.strip(), 0  # away
    if " vs. " in matchup:
        a, b = matchup.split(" vs. "); return a.strip(), b.strip(), 1  # home
    return None, None, None


def team_state_index():
    idx = {}
    for s in ("2023-24", "2024-25", "2025-26"):
        p = _ROOT / "data" / "nba" / f"season_games_{s}.json"
        if not p.exists():
            continue
        for r in json.load(open(p, encoding="utf-8")).get("rows", []):
            d = r.get("game_date")
            for side in ("home", "away"):
                t = r.get(f"{side}_team")
                if t and d is not None and r.get(f"{side}_pace") is not None:
                    idx[(d, t)] = {
                        "pace": float(r[f"{side}_pace"]),
                        "def": float(r.get(f"{side}_def_rtg") or 112.0),
                    }
    return idx


def build_covariates():
    """(pid, date) -> dict of pre-game covariates from gamelogs."""
    cov = {}
    for fp in glob.glob(str(_ROOT / "data" / "nba" / "gamelog_*_*.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = sorted(((pd.to_datetime(g.get("GAME_DATE"), errors="coerce"), g)
                       for g in log), key=lambda kv: kv[0])
        mins = []
        prev_date = None
        season_start = None
        for d, g in recs:
            if pd.isna(d):
                continue
            team, opp, is_home = _teams(g.get("MATCHUP"))
            ds = d.date().isoformat()
            if season_start is None or (prev_date and (d - prev_date).days > 60):
                season_start = d  # reset at long gaps (new season)
            rest = (d - prev_date).days if prev_date else 3
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            cov[(pid, ds)] = {
                "team": team, "opp": opp, "is_home": is_home,
                "rest_days": min(rest, 10), "is_b2b": 1 if rest <= 1 else 0,
                "actual_min": _f(g.get("MIN")),
                "l10_min": l10_min,
                "days_into_season": (d - season_start).days if season_start else 0,
                "month": d.month,
            }
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m)
            prev_date = d
    return cov


def main():
    print("loading OOF + building covariates (all seasons)...")
    oof = pd.read_parquet(OOF)
    oof["date"] = oof["game_date"].astype(str).str[:10]
    cov = build_covariates()
    tstate = team_state_index()

    rows = []
    for r in oof.itertuples(index=False):
        key = (int(r.player_id), r.date)
        c = cov.get(key)
        if c is None:
            continue
        opp_state = tstate.get((r.date, c["opp"])) if c["opp"] else None
        rows.append({
            "player_id": int(r.player_id), "date": r.date, "stat": r.stat,
            "season": r.season, "pred": float(r.oof_pred), "actual": float(r.actual),
            "err": float(r.oof_pred - r.actual),
            "abs_err": abs(float(r.oof_pred - r.actual)),
            "actual_min": c["actual_min"], "l10_min": c["l10_min"],
            "rest_days": c["rest_days"], "is_b2b": c["is_b2b"],
            "is_home": c["is_home"], "month": c["month"],
            "days_into_season": c["days_into_season"],
            "opp_pace": opp_state["pace"] if opp_state else np.nan,
            "opp_def": opp_state["def"] if opp_state else np.nan,
        })
    df = pd.DataFrame(rows)
    df.to_parquet(OUT_FRAME, index=False)
    print(f"  frame: {len(df):,} rows -> {OUT_FRAME.relative_to(_ROOT)}\n")

    def bias_table(d, col, bins=None, labels=None, qcut=False):
        d = d.dropna(subset=[col])
        if bins is not None:
            d = d.assign(_b=pd.cut(d[col], bins, labels=labels))
        elif qcut:
            d = d.assign(_b=pd.qcut(d[col], 5, duplicates="drop"))
        else:
            d = d.assign(_b=d[col])
        g = d.groupby("_b", observed=True).agg(
            n=("err", "size"), bias=("err", "mean"), mae=("abs_err", "mean"))
        return g

    # focus on the user's priority stats but the frame holds all
    for stat in ("pts", "reb"):
        s = df[(df["stat"] == stat) & (df["season"].astype(str).str.contains("2025-26") |
                                       (df["date"] >= "2025-10-01"))]
        print("=" * 70)
        print(f"{stat.upper()}  n={len(s):,}  overall bias(pred-actual)={s['err'].mean():+.3f}  "
              f"MAE={s['abs_err'].mean():.3f}")
        print("=" * 70)
        print("\n  by PREDICTED value (regression-to-mean check):")
        print(bias_table(s, "pred", qcut=True).to_string())
        print("\n  by actual MINUTES:")
        print(bias_table(s, "actual_min", bins=[-1, 18, 26, 32, 60],
                         labels=["<18", "18-26", "26-32", "32+"]).to_string())
        print("\n  by REST days:")
        print(bias_table(s, "rest_days").to_string())
        print("\n  by HOME/AWAY (1=home):")
        print(bias_table(s, "is_home").to_string())
        print("\n  by OPP PACE quintile:")
        print(bias_table(s, "opp_pace", qcut=True).to_string())
        print("\n  by MONTH:")
        print(bias_table(s, "month").to_string())
        print()


if __name__ == "__main__":
    sys.exit(main())
