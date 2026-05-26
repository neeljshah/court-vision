"""probe_R14_H3_possession_sim.py — possession-LITE Monte Carlo stepping stone.

Tests whether a per-possession rate × predicted possessions model can match
or beat the current direct per-game q50/blend prediction. This is the
foundation for the eventual full per-possession Monte Carlo simulator
(50 ML models, 10K sims/game) — but in LITE form:

  per_possession_rate = stat / possessions  (proxy possessions = min * 2.2)
  rate_L20            = shift(1).expanding L20 mean per-player per-stat
  pred_possessions    = pred_min * team_pace_per_min
                      = ewma_min * (team_pace_l5 / 48)
  pred_stat           = rate_L20 * pred_possessions

Honest framing: this is likely to REJECT because L20 rate is blind to
matchup, role, fatigue, opp defense — all of which the current 85-feature
gradient-boosted blend captures. BUT it's a foundation. Even a REJECT
informs the design (which stats benefit from mechanistic decomposition,
which need the full feature stack).

Baseline: the SAME 2-way XGB+LGB blend used by prop_pergame_walk_forward,
trained on the same WF folds, so the comparison is apples-to-apples.

Ship gate: >= 3/7 stats with mean delta MAE <= -0.005 AND 4/4 WF folds win.
Realistic candidates: PTS, REB, AST (volume stats where rate*poss is
mechanically correct).

Outputs:
  scripts/probe_R14_H3_possession_sim.py                (this file)
  data/cache/probe_R14_H3_possession_sim_results.json   (per-stat MAE)
  data/models/possession_rate_l20_<stat>.parquet        (if any stat SHIPS)

Run:
    python -u scripts/probe_R14_H3_possession_sim.py
"""
from __future__ import annotations

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
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

POSS_PER_MIN = 2.2  # league avg ~96 possessions / 48 min / 2 teams + overlap
L20_WINDOW = 20

_RESULTS_JSON = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R14_H3_possession_sim_results.json"
)


def _parse_gamelog_date(s: str) -> str:
    """Parse 'Feb 11, 2025' -> '2025-02-11'."""
    try:
        return datetime.strptime(s, "%b %d, %Y").strftime("%Y-%m-%d")
    except Exception:
        return ""


def _build_player_team_lookup() -> Dict[Tuple[int, str], str]:
    """player_id+game_date -> team_tricode (from per-player NBA gamelog JSONs)."""
    print("Building player->team lookup from gamelogs...", flush=True)
    lookup: Dict[Tuple[int, str], str] = {}
    gl_files = glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json"))
    n_skip = 0
    for fp in gl_files:
        try:
            base = os.path.basename(fp)
            # gamelog_<pid>_<season>.json
            pid_str = base.split("_")[1]
            pid = int(pid_str)
            with open(fp) as f:
                d = json.load(f)
            if not isinstance(d, list):
                continue
            for row in d:
                gd_raw = row.get("GAME_DATE")
                matchup = row.get("MATCHUP", "")
                if not gd_raw or not matchup:
                    continue
                gdate = _parse_gamelog_date(gd_raw)
                if not gdate:
                    continue
                # MATCHUP is e.g. 'IND vs. NYK' or 'IND @ NYK'
                team = matchup.split()[0]
                lookup[(pid, gdate)] = team
        except Exception:
            n_skip += 1
            continue
    print(f"  built {len(lookup)} player-date->team rows, skipped {n_skip} gamelogs", flush=True)
    return lookup


def _build_team_pace_lookup() -> Dict[Tuple[str, str], float]:
    """(team_tricode, game_date) -> rolling L5 pace through shift(1)."""
    ta = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "team_advanced_stats.parquet"))
    ta["game_date"] = ta["game_date"].astype(str).str[:10]
    ta = ta.sort_values(["team_tricode", "game_date"]).reset_index(drop=True)
    # L5 shift(1) so the pace for game G uses only games before G
    ta["pace_l5"] = (
        ta.groupby("team_tricode")["pace"]
          .apply(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
          .reset_index(level=0, drop=True)
    )
    lookup: Dict[Tuple[str, str], float] = {}
    for team, date, pace in zip(ta["team_tricode"], ta["game_date"], ta["pace_l5"]):
        if pd.notna(pace):
            lookup[(team, date)] = float(pace)
    print(f"  built {len(lookup)} (team,date)->pace_l5 rows", flush=True)
    return lookup


def _build_player_pp_rates(stats: List[str]) -> Dict[Tuple[int, str], Dict[str, float]]:
    """(player_id, game_date) -> {stat: per_possession_rate_L20_shifted}.

    Uses player_quarter_stats aggregated to per-game, then for each
    (player, stat) computes shift(1).rolling(L20).mean() of stat/possessions.
    """
    print("Computing per-player per-possession L20 rates...", flush=True)
    qs = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet"))
    pg = qs.groupby(["game_id", "player_id"]).agg(
        pts=("pts", "sum"), reb=("reb", "sum"), ast=("ast", "sum"),
        fg3m=("fg3m", "sum"), stl=("stl", "sum"), blk=("blk", "sum"),
        tov=("tov", "sum"), min=("min", "sum"),
    ).reset_index()
    # join game_date
    ta = pd.read_parquet(os.path.join(PROJECT_DIR, "data", "team_advanced_stats.parquet"))
    gid_to_date = {str(g): str(d)[:10] for g, d in zip(ta["game_id"], ta["game_date"])}
    pg["game_id"] = pg["game_id"].astype(str)
    pg["game_date"] = pg["game_id"].map(gid_to_date)
    pg = pg.dropna(subset=["game_date"])
    # possessions proxy
    pg["possessions"] = pg["min"] * POSS_PER_MIN
    pg = pg[pg["possessions"] > 0.5].reset_index(drop=True)
    pg = pg.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    # per-game per-possession rate
    for s in stats:
        pg[f"pp_{s}"] = pg[s] / pg["possessions"]
    # shift(1).rolling(L20) per player
    for s in stats:
        pg[f"rate_l20_{s}"] = (
            pg.groupby("player_id")[f"pp_{s}"]
              .apply(lambda x: x.shift(1).rolling(L20_WINDOW, min_periods=1).mean())
              .reset_index(level=0, drop=True)
        )
    # build lookup (player_id, game_date) -> rates dict
    lookup: Dict[Tuple[int, str], Dict[str, float]] = {}
    for _, row in pg.iterrows():
        pid = int(row["player_id"])
        gdate = str(row["game_date"])
        d = {}
        ok = True
        for s in stats:
            v = row[f"rate_l20_{s}"]
            if pd.isna(v):
                ok = False
                break
            d[s] = float(v)
        if ok:
            lookup[(pid, gdate)] = d
    # also persist the per-player history for any shipped stat (game_date+rate)
    # (we save the full pg below if ship)
    print(f"  computed {len(lookup)} (player,date) with full L20 rates", flush=True)
    return lookup, pg


def _train_xgb_lgb_baseline(stat, X_tr, y_tr, X_val, y_val, X_ho, sw):
    """2-way XGB+LGB NNLS-blended baseline (mirrors prop_pergame_walk_forward
    minus the MLP). Returns holdout predictions array."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression

    is_count = stat in ("stl", "blk")
    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])
    xv, lv = xgb_m.predict(X_val), lgb_m.predict(X_val)
    xh, lh = xgb_m.predict(X_ho), lgb_m.predict(X_ho)
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])
    return w[0] * xh + w[1] * lh


def run_probe(n_splits: int = 4) -> dict:
    print("=" * 72)
    print("R14_H3 — possession-sim LITE (rate * predicted possessions)")
    print("=" * 72)
    print()

    # 1) build the canonical pergame dataset
    print(f"Loading pergame dataset (n_splits={n_splits})...", flush=True)
    t0 = time.time()
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    print(f"  rows={len(rows)} features={len(fc)} took={time.time()-t0:.1f}s", flush=True)

    # 2) build lookups
    team_lookup = _build_player_team_lookup()
    pace_lookup = _build_team_pace_lookup()
    pp_lookup, pp_df = _build_player_pp_rates(list(STATS))

    # 3) build X_all + possession-sim predictions per row
    print("Joining possession-sim inputs to pergame rows...", flush=True)
    sim_preds: Dict[str, List[float]] = {s: [] for s in STATS}
    has_sim: List[bool] = []
    ewma_min_idx = fc.index("ewma_min")

    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    targets = {s: np.array([r[f"target_{s}"] for r in rows], dtype=float) for s in STATS}

    n_no_team, n_no_pace, n_no_rate = 0, 0, 0
    for r in rows:
        pid = int(r["player_id"])
        gdate = str(r["date"])[:10]
        team = team_lookup.get((pid, gdate))
        if team is None:
            has_sim.append(False)
            for s in STATS:
                sim_preds[s].append(np.nan)
            n_no_team += 1
            continue
        pace = pace_lookup.get((team, gdate))
        if pace is None:
            has_sim.append(False)
            for s in STATS:
                sim_preds[s].append(np.nan)
            n_no_pace += 1
            continue
        rates = pp_lookup.get((pid, gdate))
        if rates is None:
            has_sim.append(False)
            for s in STATS:
                sim_preds[s].append(np.nan)
            n_no_rate += 1
            continue
        # predicted possessions = pred_min * pace_per_min
        # pace stat = total team possessions per 48 min, so pace/48 = poss/min
        # pred_min = ewma_min (already a feature)
        pred_min = float(r["ewma_min"]) if r["ewma_min"] is not None else 0.0
        pred_poss = pred_min * (pace / 48.0)
        has_sim.append(True)
        for s in STATS:
            sim_preds[s].append(rates[s] * pred_poss)

    has_sim = np.array(has_sim, dtype=bool)
    print(f"  sim coverage: {has_sim.sum()}/{len(rows)} ({100*has_sim.mean():.1f}%)", flush=True)
    print(f"  drops: no_team={n_no_team} no_pace={n_no_pace} no_rate={n_no_rate}", flush=True)

    # 4) WF folds — train baseline on same fold layout as prop_pergame_walk_forward
    n = len(rows)
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    per_stat_folds: Dict[str, list] = {s: [] for s in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 4000 or (te_end - va_end) < 1500:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, te={te_end-tr_end}) — skip")
            continue
        X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        # holdout mask for rows with sim coverage
        ho_idx = np.arange(va_end, te_end)
        ho_has_sim = has_sim[ho_idx]
        n_ho_sim = int(ho_has_sim.sum())

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
              f"ho={te_end-va_end} ho_sim={n_ho_sim}", flush=True)
        if n_ho_sim < 500:
            print(f"  too few sim-covered holdout rows ({n_ho_sim}) — skip")
            continue

        for stat in STATS:
            y_full = targets[stat]
            y_tr, y_val, y_ho = y_full[:tr_end], y_full[tr_end:va_end], y_full[va_end:te_end]
            t0 = time.time()
            base_pred = _train_xgb_lgb_baseline(stat, X_tr, y_tr, X_val, y_val, X_ho, sw)
            # restrict to sim-covered subset for fair compare
            sim_pred_ho = np.array([sim_preds[stat][i] for i in ho_idx])
            mask = ho_has_sim & ~np.isnan(sim_pred_ho)
            if mask.sum() < 500:
                continue
            mae_base = float(np.mean(np.abs(y_ho[mask] - base_pred[mask])))
            mae_sim = float(np.mean(np.abs(y_ho[mask] - sim_pred_ho[mask])))
            delta = mae_sim - mae_base
            per_stat_folds[stat].append({
                "fold": fold_idx + 1,
                "n": int(mask.sum()),
                "mae_baseline": mae_base,
                "mae_sim": mae_sim,
                "delta_mae": delta,
            })
            print(f"  {stat.upper():4s} base={mae_base:.4f} sim={mae_sim:.4f} "
                  f"delta={delta:+.4f}  ({time.time()-t0:.0f}s)", flush=True)

    # 5) Summarise + ship gate
    summary: dict = {
        "by_stat": {},
        "ship_gate_strict": "fold_wins == 4 AND mean_delta <= -0.005",
        "ship_gate_covered": "all covered folds win AND mean_delta <= -0.005",
    }
    n_ship_strict = 0
    n_ship_covered = 0
    ships_strict: List[str] = []
    ships_covered: List[str] = []
    print("\n=== POSSESSION-SIM SUMMARY ===")
    print(" stat | baseline MAE | sim MAE | mean delta |  WF wins | strict | covered")
    print("------+--------------+---------+------------+----------+--------+--------")
    for stat in STATS:
        folds = per_stat_folds[stat]
        if not folds:
            continue
        mean_base = float(np.mean([f["mae_baseline"] for f in folds]))
        mean_sim = float(np.mean([f["mae_sim"] for f in folds]))
        mean_delta = float(np.mean([f["delta_mae"] for f in folds]))
        fold_wins = int(sum(1 for f in folds if f["delta_mae"] <= 0.0))
        n_folds = len(folds)
        is_ship_strict = (fold_wins == n_folds == 4) and (mean_delta <= -0.005)
        is_ship_covered = (fold_wins == n_folds) and (mean_delta <= -0.005)
        summary["by_stat"][stat] = {
            "mae_baseline_mean": mean_base,
            "mae_sim_mean": mean_sim,
            "delta_mae_mean": mean_delta,
            "fold_wins": fold_wins,
            "n_folds": n_folds,
            "ship_strict": is_ship_strict,
            "ship_covered": is_ship_covered,
            "folds": folds,
        }
        if is_ship_strict:
            n_ship_strict += 1
            ships_strict.append(stat)
        if is_ship_covered:
            n_ship_covered += 1
            ships_covered.append(stat)
        print(f"  {stat.upper():4s} | {mean_base:12.4f} | {mean_sim:7.4f} | "
              f"{mean_delta:+10.4f} | {fold_wins}/{n_folds}      | "
              f"{'SHIP' if is_ship_strict else '----'}   | "
              f"{'SHIP' if is_ship_covered else '----'}")

    summary["n_ship_strict"] = n_ship_strict
    summary["n_ship_covered"] = n_ship_covered
    summary["ships_strict"] = ships_strict
    summary["ships_covered"] = ships_covered
    summary["overall_ship_decision"] = "SHIP" if n_ship_strict >= 3 else "REJECT"
    print(f"\n>>> strict gate: {n_ship_strict}/7 stats ship; "
          f"covered gate: {n_ship_covered}/7 stats ship;")
    print(f">>> overall (strict): {summary['overall_ship_decision']}")

    # 6) Persist shipped stats' rate parquets (strict gate only — covered gate
    # is informational, not production-ready due to coverage gaps).
    if ships_strict:
        for s in ships_strict:
            out = os.path.join(PROJECT_DIR, "data", "models",
                               f"possession_rate_l20_{s}.parquet")
            keep = pp_df[["player_id", "game_id", "game_date", f"rate_l20_{s}",
                          "min", "possessions"]].copy()
            keep.to_parquet(out, index=False)
            print(f"  wrote {out}", flush=True)

    # 7) Write json
    os.makedirs(os.path.dirname(_RESULTS_JSON), exist_ok=True)
    with open(_RESULTS_JSON, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nWrote {_RESULTS_JSON}")
    return summary


if __name__ == "__main__":
    run_probe(n_splits=4)
