"""probe_R24_Q3_m2_retrain.py — Retrain m2_family multi5 ensemble and benchmark.

Goal: retrain the 20-model m2_family ensemble (5 per target x {total, spread,
home_pts, away_pts}) on fresh 2025-26 gamelogs, walk-forward backtest with
2025-26 as the final fold, and compare new vs old per-target MAE.

Ship gate (from brief):
    new wins on >=3/4 targets by >= -2% MAE on 2025-26 holdout
    AND no target regresses by more than +1%

Output: data/cache/probe_R24_Q3_results.json with per_target_mae_old /
per_target_mae_new / wf_fold_results / n_train_rows / n_val_rows / decision.

DIAGNOSTIC (R24_Q3 reality check):
  The brief assumes R17_J8 backfilled fresh 2025-26 *game-level* features that
  would enable a meaningful retrain. In fact R17_J8 backfilled per-PLAYER
  gamelogs (PlayerGameLog endpoint) for the prop_pergame prediction cache,
  which is a different pipeline. The m2_family training script
  (scripts/train_final_M2_family.py) consumes
  data/nba/season_games_*.json + data/nba/linescores_all.json — the team-level
  pregame feature snapshot. Inspect at run time:
    season_games_2025-26.json has 1230 schedule rows but ZERO featured rows
      (no home_off_rtg / home_pace / etc. populated).
    linescores_all.json contains 3 (three) 2025-26 game results.
  Therefore there is no fresh 2025-26 data to retrain on; the existing
  m2_family manifest already reflects the maximum available data (2836 games,
  trained 2026-05-26 07:46 — same morning as this probe).

The probe still runs the full re-train + 4-fold walk-forward to:
  (a) verify the training pipeline is intact and seed-deterministic,
  (b) produce per-target MAE numbers for the historical folds,
  (c) document the blocked-on-data state in the results JSON so a future
      probe can re-attempt once the 2025-26 game-level feature build (a
      separate fetch from R17_J8) lands.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
WORKTREE_DIR = os.path.dirname(os.path.dirname(PROBE_DIR))
sys.path.insert(0, WORKTREE_DIR)

# Resolve the real (root) project for read-only data access. Worktrees do not
# carry the data/models or data/nba payload (gitignored), so we always read
# from the canonical root checkout while writing outputs into the worktree.
def _resolve_data_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else WORKTREE_DIR


ROOT_DIR = _resolve_data_root()
DATA_NBA = os.path.join(ROOT_DIR, "data", "nba")
ROOT_MODELS_DIR = os.path.join(ROOT_DIR, "data", "models", "m2_family")
ROOT_BACKUP_DIR = os.path.join(ROOT_DIR, "data", "models", "m2_family_R20_M7_backup")
RESULTS_PATH = os.path.join(WORKTREE_DIR, "data", "cache", "probe_R24_Q3_results.json")

# Canonical feature set from scripts/train_final_M2_family.py (74 names; in
# practice only ~25 of these exist on the season_games rows — the rest fall
# back via fillna(0.0) on the available subset).
FEAT_COLS = [
    "home_off_rtg", "home_def_rtg", "home_net_rtg", "home_pace",
    "home_efg_pct", "home_ts_pct", "home_tov_pct", "home_rest_days",
    "home_back_to_back", "home_last5_wins", "home_season_win_pct",
    "away_off_rtg", "away_def_rtg", "away_net_rtg", "away_pace",
    "away_efg_pct", "away_ts_pct", "away_tov_pct", "away_rest_days",
    "away_back_to_back", "away_last5_wins", "away_season_win_pct",
    "net_rtg_diff", "pace_diff", "home_advantage",
    "home_off_rtg_L10", "home_def_rtg_L10", "home_net_rtg_L10",
    "away_off_rtg_L10", "away_def_rtg_L10", "away_net_rtg_L10",
    "home_efg_L10", "away_efg_L10",
    "home_pace_variance", "away_pace_variance",
    "home_travel_miles", "away_travel_miles",
    "home_top_lineup_net_rtg", "away_top_lineup_net_rtg",
    "iso_matchup_edge", "home_pnr_ppp", "away_pnr_ppp",
    "home_hustle_deflections_pg", "away_hustle_deflections_pg",
    "home_stars_available", "away_stars_available",
    "home_bench_net_rtg", "away_bench_net_rtg",
    "home_tov_pct_L10", "away_tov_pct_L10",
    "home_oreb_pct_L10", "away_oreb_pct_L10",
    "home_ft_rate_L10", "away_ft_rate_L10",
    "home_off_rtg_home_L10", "away_off_rtg_away_L10",
    "home_off_rtg_vs_top_def", "away_off_rtg_vs_top_def",
    "home_srs", "away_srs",
    "home_elo", "away_elo", "elo_differential",
    "home_def_rtg_trend", "away_def_rtg_trend",
    "b2b_diff", "elo_pace_interaction",
    "ref_avg_fouls", "ref_home_win_pct", "ref_fta_tendency",
    "sim_win_prob", "sim_score_diff_mean", "sim_score_diff_std", "sim_pace_adj",
]

LGB_SEEDS = [42, 7, 100]
XGB_SEEDS = [42, 7]
TARGETS = {
    "total":    "total_pts_box",
    "spread":   "score_diff",
    "home_pts": "home_score",
    "away_pts": "away_score",
}


def _load_dataset() -> Tuple[pd.DataFrame, List[str], Dict[str, int]]:
    """Reproduce scripts/train_final_M2_family.py load_dataset()."""
    rows: List[dict] = []
    season_counts: Dict[str, int] = {}
    for fname in ("season_games_2022-23.json", "season_games_2023-24.json",
                  "season_games_2024-25.json", "season_games_2025-26.json"):
        p = os.path.join(DATA_NBA, fname)
        if not os.path.exists(p):
            season_counts[fname] = -1
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        these = d.get("rows", d) if isinstance(d, dict) else d
        season_counts[fname] = len(these) if isinstance(these, list) else 0
        rows.extend(these or [])
    sg = pd.DataFrame(rows)

    ls_path = os.path.join(DATA_NBA, "linescores_all.json")
    with open(ls_path, encoding="utf-8") as f:
        ls_raw = json.load(f)
    ls_rows: List[dict] = []
    for gid, ls in ls_raw.items():
        try:
            hq = [float(ls.get(f"home_q{i}", 0) or 0) for i in range(1, 5)]
            aq = [float(ls.get(f"away_q{i}", 0) or 0) for i in range(1, 5)]
        except (TypeError, ValueError):
            continue
        h, a = sum(hq), sum(aq)
        if h <= 0 or a <= 0:
            continue
        ls_rows.append({
            "game_id": gid, "home_score": h, "away_score": a,
            "score_diff": h - a, "total_pts_box": h + a,
        })
    ls = pd.DataFrame(ls_rows)

    merged = sg.merge(ls, on="game_id", how="inner")
    for col in ("home_off_rtg", "away_off_rtg", "home_pace", "away_pace"):
        if col in merged.columns:
            merged = merged[merged[col] > 0]
        else:
            return merged.iloc[:0], [], season_counts
    merged = merged.sort_values("game_date").reset_index(drop=True)
    avail = [c for c in FEAT_COLS if c in merged.columns]
    if avail:
        merged[avail] = merged[avail].fillna(0.0)
    return merged, avail, season_counts


def _fit_ensemble(X: np.ndarray, y: np.ndarray):
    """Train (3 LGB + 2 XGB) seed ensemble. Returns list of fitted models."""
    import lightgbm as lgb
    import xgboost as xgb
    models = []
    for seed in LGB_SEEDS:
        m = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            min_child_samples=20, random_state=seed, n_jobs=2, verbose=-1,
        )
        m.fit(X, y)
        models.append(("lgb", seed, m))
    for seed in XGB_SEEDS:
        m = xgb.XGBRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=6,
            subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1,
            random_state=seed, n_jobs=2, verbosity=0,
        )
        m.fit(X, y)
        models.append(("xgb", seed, m))
    return models


def _ensemble_predict(models, X: np.ndarray) -> np.ndarray:
    preds = np.zeros(X.shape[0])
    for _, _, m in models:
        preds += m.predict(X)
    return preds / float(len(models))


def _walk_forward(merged: pd.DataFrame, feats: List[str], n_folds: int = 4) -> Dict:
    """Expanding-window walk-forward: split chronologically into n_folds eval
    chunks, training on everything strictly before each chunk's start."""
    if len(merged) < n_folds * 50:
        return {"error": f"insufficient rows for {n_folds}-fold WF: {len(merged)}"}
    chunk = len(merged) // (n_folds + 1)  # +1 reserves a burn-in train block
    fold_results: List[Dict] = []
    for k in range(n_folds):
        train_end = chunk * (k + 1)
        val_start = train_end
        val_end = train_end + chunk if k < n_folds - 1 else len(merged)
        tr = merged.iloc[:train_end]
        va = merged.iloc[val_start:val_end]
        Xtr = tr[feats].values
        Xva = va[feats].values
        fold_metrics: Dict[str, float] = {
            "fold": k,
            "n_train": int(len(tr)),
            "n_val": int(len(va)),
            "val_date_start": str(va["game_date"].iloc[0])[:10] if len(va) else None,
            "val_date_end":   str(va["game_date"].iloc[-1])[:10] if len(va) else None,
        }
        for tgt, label in TARGETS.items():
            ytr = tr[label].astype(float).values
            yva = va[label].astype(float).values
            models = _fit_ensemble(Xtr, ytr)
            pred = _ensemble_predict(models, Xva)
            mae = float(np.mean(np.abs(yva - pred)))
            fold_metrics[f"mae_{tgt}"] = mae
        fold_results.append(fold_metrics)
    return {"folds": fold_results}


def _eval_existing(merged: pd.DataFrame, feats: List[str]) -> Optional[Dict[str, float]]:
    """Score the persisted ROOT m2_family ensemble against the FINAL holdout
    chunk (matches the WF n_folds=4 final fold so old/new are comparable)."""
    if not os.path.isdir(ROOT_MODELS_DIR):
        return None
    try:
        import joblib
        with open(os.path.join(ROOT_MODELS_DIR, "manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
        with open(os.path.join(ROOT_MODELS_DIR, "feature_cols.json"), encoding="utf-8") as f:
            saved_feats = json.load(f)
    except Exception as e:
        return {"error": f"load_fail: {e!r}"}
    use_feats = [c for c in saved_feats if c in merged.columns]
    if not use_feats:
        return {"error": "no overlap between saved feature_cols and merged dataset"}
    if len(merged) < 200:
        return {"error": f"need >=200 rows to eval, got {len(merged)}"}
    n_folds = 4
    chunk = len(merged) // (n_folds + 1)
    val_start = chunk * n_folds
    va = merged.iloc[val_start:]
    Xva = va[use_feats].values
    out: Dict[str, float] = {
        "val_date_start": str(va["game_date"].iloc[0])[:10] if len(va) else None,
        "val_date_end":   str(va["game_date"].iloc[-1])[:10] if len(va) else None,
        "n_val": int(len(va)),
    }
    for tgt, label in TARGETS.items():
        preds = np.zeros(len(va))
        n = 0
        try:
            for lab in man["targets"][tgt]["models"]:
                p = os.path.join(ROOT_MODELS_DIR, f"{tgt}_{lab}.joblib")
                if not os.path.exists(p):
                    continue
                m = joblib.load(p)
                preds += m.predict(Xva)
                n += 1
            if n == 0:
                out[f"mae_{tgt}"] = float("nan")
            else:
                preds /= n
                out[f"mae_{tgt}"] = float(np.mean(np.abs(va[label].astype(float).values - preds)))
        except Exception as e:
            out[f"mae_{tgt}"] = float("nan")
            out[f"err_{tgt}"] = repr(e)
    return out


def main() -> int:
    t0 = time.time()
    print(f"[R24_Q3] ROOT_DIR = {ROOT_DIR}", flush=True)
    print(f"[R24_Q3] loading dataset ...", flush=True)
    merged, feats, season_counts = _load_dataset()
    n_total = int(len(merged))
    season_dist = (
        merged.groupby("season").size().to_dict() if n_total else {}
    )
    print(f"[R24_Q3] dataset: {n_total} rows, {len(feats)} features", flush=True)
    print(f"[R24_Q3] by season: {season_dist}", flush=True)
    print(f"[R24_Q3] raw season_games row counts: {season_counts}", flush=True)

    n_2025_26 = int(season_dist.get("2025-26", 0))
    blocked_on_data = n_2025_26 < 100  # need at least 100 games for a real fold

    payload: Dict = {
        "probe": "R24_Q3_m2_family_retrain",
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "root_dir": ROOT_DIR,
        "n_train_rows": n_total,
        "n_features_used": len(feats),
        "season_distribution": {str(k): int(v) for k, v in season_dist.items()},
        "raw_season_games_counts": season_counts,
        "n_2025_26_with_features_and_score": n_2025_26,
        "blocked_on_data": blocked_on_data,
        "blocked_reason": None,
        "per_target_mae_old": {},
        "per_target_mae_new": {},
        "per_target_delta_pct": {},
        "n_targets_improving": 0,
        "wf_fold_results": [],
        "n_val_rows": 0,
        "decision": "REJECT",
        "ship_gate_pass": False,
        "summary": "",
        "elapsed_seconds": 0.0,
    }

    if blocked_on_data:
        payload["blocked_reason"] = (
            f"only {n_2025_26} fully-featured 2025-26 game rows available "
            "(need >=100 for a meaningful 2025-26 holdout). R17_J8 backfilled "
            "per-PLAYER gamelogs for prop_pergame, NOT game-level pregame "
            "features (home_off_rtg / home_pace / etc.) which is what "
            "scripts/train_final_M2_family.py consumes. The 2025-26 row in "
            "linescores_all.json only has 3 game results. Existing m2_family "
            "manifest already reflects max-available data (2836 games, "
            "trained 2026-05-26)."
        )
        payload["decision"] = "REJECT"
        payload["summary"] = (
            f"BLOCKED: no fresh 2025-26 game-level data. "
            f"n_2025_26_featured={n_2025_26}; need feature build for "
            "season_games_2025-26.json + linescores backfill before retrain "
            "is meaningful."
        )

    # Run WF backtest regardless: gives reproducibility ground-truth + per-fold
    # MAE numbers for the historical seasons we DO have.
    if n_total >= 250 and feats:
        print(f"[R24_Q3] running 4-fold walk-forward backtest ...", flush=True)
        wf = _walk_forward(merged, feats, n_folds=4)
        if "folds" in wf:
            payload["wf_fold_results"] = wf["folds"]
            final_fold = wf["folds"][-1]
            payload["n_val_rows"] = final_fold["n_val"]
            payload["per_target_mae_new"] = {
                tgt: float(final_fold[f"mae_{tgt}"]) for tgt in TARGETS
            }
        else:
            payload["wf_error"] = wf.get("error", "unknown")

        # Compare against persisted root artifacts on the same final-fold slice.
        print(f"[R24_Q3] evaluating existing root m2_family artifacts ...", flush=True)
        old_eval = _eval_existing(merged, feats)
        if old_eval and "error" not in old_eval:
            payload["per_target_mae_old"] = {
                tgt: float(old_eval.get(f"mae_{tgt}", float("nan"))) for tgt in TARGETS
            }
        elif old_eval:
            payload["old_eval_error"] = old_eval["error"]

        # Per-target deltas + ship gate.
        if payload["per_target_mae_old"] and payload["per_target_mae_new"]:
            n_improving = 0
            n_regressing_over_1pct = 0
            for tgt in TARGETS:
                old = payload["per_target_mae_old"].get(tgt)
                new = payload["per_target_mae_new"].get(tgt)
                if old and old > 0 and new is not None:
                    delta_pct = 100.0 * (new - old) / old
                    payload["per_target_delta_pct"][tgt] = round(delta_pct, 3)
                    if delta_pct <= -2.0:
                        n_improving += 1
                    if delta_pct > 1.0:
                        n_regressing_over_1pct += 1
            payload["n_targets_improving"] = n_improving
            ship = (n_improving >= 3 and n_regressing_over_1pct == 0
                    and not blocked_on_data)
            payload["ship_gate_pass"] = bool(ship)
            if ship:
                payload["decision"] = "SHIP"
                payload["summary"] = (
                    f"SHIP: {n_improving}/4 targets improve >=2%, 0 regress >1%."
                )
            elif not blocked_on_data:
                payload["decision"] = "REJECT"
                payload["summary"] = (
                    f"REJECT: ship gate failed. improving={n_improving}/4 "
                    f"(need >=3), regressing>1%={n_regressing_over_1pct} "
                    f"(need 0). deltas={payload['per_target_delta_pct']}."
                )

    payload["elapsed_seconds"] = round(time.time() - t0, 2)
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"[R24_Q3] decision={payload['decision']}", flush=True)
    print(f"[R24_Q3] wrote -> {RESULTS_PATH}", flush=True)
    print(f"[R24_Q3] summary: {payload['summary']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
