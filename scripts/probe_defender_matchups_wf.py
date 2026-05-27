"""probe_defender_matchups_wf.py — iter-5 side-band probe.

Tests whether per-(game,opp_team) defender-pressure features aggregated
from data/defender_matchups_2024-25.parquet improve walk-forward MAE
for q50 quantile-head stats (FG3M first, then BLK+TOV if FG3M passes).

LOCAL ONLY. Does NOT modify prop_pergame.py or production artifacts.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset,
    feature_columns,
    _opponent_from_matchup,
    _parse_date,
)

NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
PARQUET   = os.path.join(PROJECT_DIR, "data", "defender_matchups_2024-25.parquet")


# ─── 1. Build (game_date, opp_team) -> 4 expanding-mean defender features ────

def build_opp_team_defender_features() -> pd.DataFrame:
    """Aggregate defender_matchups to (game_id, def_team_tricode) team-level
    allowed metrics, then for each (date, team) compute the EXPANDING MEAN
    of the team's PRIOR games (shift(1).expanding().mean()).

    Returns a DataFrame keyed by (game_date_iso, opp_team) -> 4 features.
    """
    raw = pd.read_parquet(PARQUET)
    raw["game_date"] = pd.to_datetime(raw["game_date"])

    # Team-level aggregate per game.
    def _agg(g):
        mtot = g["matchup_minutes_total"].sum()
        fga  = g["fg_attempted_allowed"].sum()
        fg3a = g["fg3_attempted_allowed"].sum()
        return pd.Series({
            "team_pts_allowed_pm": g["points_allowed"].sum() / mtot if mtot > 0 else np.nan,
            "team_fg_pct_allowed_wavg": (
                (g["fg_pct_allowed"] * g["fg_attempted_allowed"]).sum() / fga
                if fga > 0 else np.nan
            ),
            "team_fg3_pct_allowed_wavg": (
                (g["fg3_pct_allowed"] * g["fg3_attempted_allowed"]).sum() / fg3a
                if fg3a > 0 else np.nan
            ),
            "team_switches_pm": g["switches_on"].sum() / mtot if mtot > 0 else np.nan,
            "game_date": g["game_date"].iloc[0],
        })

    team_game = raw.groupby(["game_id", "def_team_tricode"], group_keys=False).apply(_agg).reset_index()
    team_game = team_game.sort_values(["def_team_tricode", "game_date"])

    # Expanding mean of PRIOR games per team (shift(1).expanding().mean())
    feat_cols = ["team_pts_allowed_pm", "team_fg_pct_allowed_wavg",
                 "team_fg3_pct_allowed_wavg", "team_switches_pm"]
    out_cols  = ["opp_def_pts_allowed_per_min", "opp_def_fg_pct_allowed_wavg",
                 "opp_def_fg3_pct_allowed_wavg", "opp_def_switches_per_min"]

    for f, o in zip(feat_cols, out_cols):
        team_game[o] = (
            team_game.groupby("def_team_tricode")[f]
                     .transform(lambda s: s.shift(1).expanding().mean())
        )

    team_game["date_iso"] = team_game["game_date"].dt.strftime("%Y-%m-%d")
    return team_game[["date_iso", "def_team_tricode"] + out_cols].rename(
        columns={"def_team_tricode": "opp_team"}
    )


# ─── 2. Build (player_id, date) -> opp_team mapping from gamelogs ─────────────

def build_player_date_to_opp() -> Dict[Tuple[int, str], str]:
    """Walk gamelog cache and emit {(player_id, date_iso): opp_team}."""
    mapping: Dict[Tuple[int, str], str] = {}
    for path in glob.glob(os.path.join(NBA_CACHE, "gamelog_*.json")):
        try:
            games = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        basename = os.path.basename(path)
        try:
            pid = int(basename.split("_")[1])
        except Exception:
            continue
        for g in games:
            gd = _parse_date(g.get("GAME_DATE"))
            if gd is None:
                continue
            opp = _opponent_from_matchup(str(g.get("MATCHUP", "")))
            if not opp:
                continue
            mapping[(pid, gd.strftime("%Y-%m-%d"))] = opp
    return mapping


# ─── 3. WF probe ──────────────────────────────────────────────────────────────

def _q50_quantile_model(X_tr, y_tr, X_val, y_val, X_ho, eval_metric="mae"):
    """Single XGB quantile regressor at q50 (median)."""
    import xgboost as xgb
    m = xgb.XGBRegressor(
        n_estimators=600, max_depth=4, learning_rate=0.04,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42, objective="reg:quantileerror",
        quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric=eval_metric,
    )
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    return m.predict(X_ho)


def run_wf_for_stats(stats: List[str], n_splits: int = 4):
    print(f"[1/3] Loading pergame dataset...", flush=True)
    t0 = time.time()
    rows, fc = build_pergame_dataset(min_prior=0)
    print(f"      rows={len(rows)} features={len(fc)} ({time.time()-t0:.1f}s)", flush=True)

    print(f"[2/3] Building (player,date)->opp map + opp-team feature table...", flush=True)
    t0 = time.time()
    p2opp = build_player_date_to_opp()
    opp_feats = build_opp_team_defender_features()
    opp_feats_idx = opp_feats.set_index(["date_iso", "opp_team"])
    print(f"      p2opp={len(p2opp)} opp_feat_rows={len(opp_feats)} ({time.time()-t0:.1f}s)", flush=True)

    # Attach opp_team + the 4 new features per row.
    new_keys = ["opp_def_pts_allowed_per_min", "opp_def_fg_pct_allowed_wavg",
                "opp_def_fg3_pct_allowed_wavg", "opp_def_switches_per_min"]
    n_hit = 0
    for r in rows:
        pid = r.get("player_id", 0)
        date_iso = r["date"][:10]
        opp = p2opp.get((int(pid), date_iso))
        feats = None
        if opp is not None:
            try:
                feats = opp_feats_idx.loc[(date_iso, opp)]
                n_hit += 1
            except KeyError:
                feats = None
        for k in new_keys:
            v = float(feats[k]) if feats is not None and not pd.isna(feats[k]) else np.nan
            r[k] = v

    cov = n_hit / len(rows) * 100
    print(f"      coverage: {n_hit}/{len(rows)} rows ({cov:.2f}%) have a non-NaN match", flush=True)

    # NaN-fill with column-mean (computed on training portion only inside fold).
    rows.sort(key=lambda r: r["date"])
    n = len(rows)

    base_cols = fc
    probe_cols = fc + new_keys

    X_base  = np.array([[r[c] for c in base_cols]  for r in rows], dtype=float)
    X_probe = np.array([[r.get(c, np.nan) for c in probe_cols] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    results_table: List[Tuple[int, str, float, float, float, str]] = []
    per_stat_signs: Dict[str, List[int]] = {s: [] for s in stats}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            continue

        # NaN-fill via training-only mean (per col)
        def _fill(X):
            X = X.copy()
            tr_means = np.nanmean(X[:tr_end], axis=0)
            tr_means = np.where(np.isnan(tr_means), 0.0, tr_means)
            for j in range(X.shape[1]):
                mask = np.isnan(X[:, j])
                X[mask, j] = tr_means[j]
            return X

        Xb = _fill(X_base)
        Xp = _fill(X_probe)
        Xb_tr, Xb_va, Xb_ho = Xb[:tr_end], Xb[tr_end:va_end], Xb[va_end:te_end]
        Xp_tr, Xp_va, Xp_ho = Xp[:tr_end], Xp[tr_end:va_end], Xp[va_end:te_end]

        from sklearn.metrics import mean_absolute_error
        for stat in stats:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr, y_va, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]

            pb = _q50_quantile_model(Xb_tr, y_tr, Xb_va, y_va, Xb_ho)
            pp = _q50_quantile_model(Xp_tr, y_tr, Xp_va, y_va, Xp_ho)
            mae_b = float(mean_absolute_error(y_ho, pb))
            mae_p = float(mean_absolute_error(y_ho, pp))
            delta = mae_p - mae_b
            sign = -1 if delta < 0 else (1 if delta > 0 else 0)
            per_stat_signs[stat].append(sign)
            result_str = "DOWN" if delta < 0 else ("UP" if delta > 0 else "FLAT")
            results_table.append((fold_idx + 1, stat.upper(), mae_b, mae_p, delta, result_str))
            print(f"  fold {fold_idx+1} {stat.upper():4s}  base={mae_b:.4f}  probe={mae_p:.4f}  d={delta:+.4f}  {result_str}", flush=True)

    print()
    print("| Fold | Stat | Baseline MAE | Probe MAE | Delta   | Result |")
    print("|------|------|--------------|-----------|---------|--------|")
    for f, s, b, p, d, r in results_table:
        print(f"| {f}    | {s:4s} | {b:.4f}       | {p:.4f}    | {d:+.4f} | {r:4s}   |")

    print()
    print("=== VERDICT ===")
    verdicts: Dict[str, str] = {}
    for stat in stats:
        signs = per_stat_signs[stat]
        n_down = sum(1 for s in signs if s == -1)
        n_total = len(signs)
        if n_total == 0:
            verdicts[stat] = "INCONCLUSIVE"
        elif n_down == n_total:
            verdicts[stat] = "SHIP"
        else:
            verdicts[stat] = "REJECT"
        print(f"  {stat.upper():4s}: {n_down}/{n_total} folds positive  ->  {verdicts[stat]}")

    return verdicts, cov


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--stats", nargs="*", default=None,
                    help="default: probe FG3M only, expand if it ships")
    args = ap.parse_args()

    stats = args.stats or ["fg3m"]
    t_global = time.time()
    verdicts, cov = run_wf_for_stats(stats, n_splits=args.splits)
    if "fg3m" in verdicts and verdicts["fg3m"] == "SHIP" and not args.stats:
        print("\nFG3M shipped — expanding to BLK+TOV...\n")
        run_wf_for_stats(["blk", "tov"], n_splits=args.splits)
    print(f"\nTotal runtime: {time.time()-t_global:.1f}s")
