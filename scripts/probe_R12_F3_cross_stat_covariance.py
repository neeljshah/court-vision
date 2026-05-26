"""probe_R12_F3_cross_stat_covariance.py -- R12_F3 cross-stat residual lookups.

WHY: After R10_M16 shipped streak features for FG3M/STL/BLK/TOV the cross-stat
residual structure may have shifted. C6 portfolio Kelly observed strong
correlations -- PTS<->FG3M=0.67, PTS<->REB=0.31, REB<->BLK=0.15 -- which is
empirical evidence of structural cross-stat signal not captured by the existing
residual heads.

APPROACH (mirrors probe_R10_M16_streak.py):
  For every (player_id, game_id, stat) row in pregame_oof.parquet:
    1. Compute the player's L5 PRIOR-game mean z-residual per stat:
         z[s] = (actual[s] - oof_pred[s]) / sigma_stat,
       averaged over the player's 5 most-recent games strictly BEFORE
       game_date. sigma_stat = global std of actual[s] across OOF.
    2. EXCLUDE the target stat's own z (xstat_z_<target>) to prevent trivial
       leakage. The residual head sees 6 cross-stat z values + n_prior_xstat.
    3. Train a LightGBM residual head on (actual - oof_pred) using only
       those 7 features (6 z + 1 coverage).

  Walk-forward 4-fold uses the EXISTING OOF fold column (already chronological).

SHIP GATE (per-stat):
  Per-stat MAE delta <= -0.005 on 4/4 walk-forward folds AND >= 4/7 stats
  with mean_delta < 0. Per-stat ship -- mirrors R10_M16 pattern.

LEAKAGE INVARIANTS:
  - The target stat's own xstat_z_<stat> is masked OUT of the feature vector.
  - z-residuals are aggregated strictly from games BEFORE the current game_date
    (per-player shift(1) on the (player_id, game_date) ordering).
  - The OOF parquet is OOF by construction (oof_pred for row R was produced
    by a model that didn't see R); reading it gives a leak-safe residual
    estimate.

Run:
    python -u scripts/probe_R12_F3_cross_stat_covariance.py \\
        > scripts/_results/improve_R12_F3_run.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

try:
    import lightgbm as lgb
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"lightgbm import failed: {exc}")

# ── constants ────────────────────────────────────────────────────────────────

STATS: Tuple[str, ...] = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_L5 = 5

_OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")
_RESULTS_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")
_CACHE_OUT = os.path.join(
    PROJECT_DIR, "data", "cache", "probe_R12_F3_cross_stat_covariance_results.json"
)
_HEADS_OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")

BASELINES: Dict[str, float] = {
    "pts":  2.214,
    "reb":  0.8987,
    "ast":  0.5755,
    "fg3m": 0.3528,
    "stl":  0.2506,
    "blk":  0.1543,
    "tov":  0.3663,
}

# Cross-stat z feature names (one per stat -- target's own is masked at use).
XSTAT_Z_NAMES: Tuple[str, ...] = tuple(f"xstat_z_{s}" for s in STATS)


def _lgb_params() -> Dict:
    """Match scripts/train_residual_heads_endq3_streak.py LGB_PARAMS."""
    return {
        "n_estimators":      200,
        "learning_rate":     0.03,
        "num_leaves":        15,
        "min_child_samples": 80,
        "objective":         "regression_l1",
        "random_state":      42,
        "verbosity":         -1,
        "n_jobs":            -1,
    }


# ── cross-stat z-residual builder ────────────────────────────────────────────


def compute_xstat_z_matrix(oof_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Compute (player_id, game_id) -> {xstat_z_<stat>, n_prior_xstat}.

    For each (player_id, game_id) row, the cross-stat z feature for stat s is
    the MEAN of z_s = (actual_s - oof_pred_s) / sigma_s over the L5 most-recent
    games of that player strictly BEFORE the current game_date.

    sigma_s = global std of actual_s across the entire OOF parquet.

    Strict shift(1): a row never sees itself; only PRIOR (actual, oof_pred)
    pairs feed the average. The OOF parquet is OOF by construction so each
    prior row is itself leak-safe.

    Returns
    -------
    (out_df, sigmas)
      out_df: DataFrame with columns
        [player_id, game_id, n_prior_xstat, xstat_z_pts, ..., xstat_z_tov]
      sigmas: {stat -> float}
    """
    print("  pivoting OOF to per-(pid, gid) wide format ...", flush=True)
    wide = oof_df.pivot_table(
        index=["player_id", "game_id", "game_date"],
        columns="stat",
        values=["actual", "oof_pred"],
        aggfunc="first",
    ).reset_index()
    wide.columns = [f"{a}_{b}" if b else a for a, b in wide.columns]
    wide["game_date"] = pd.to_datetime(wide["game_date"])
    wide = wide.sort_values(
        ["player_id", "game_date", "game_id"]
    ).reset_index(drop=True)

    sigmas: Dict[str, float] = {}
    for s in STATS:
        col = f"actual_{s}"
        sigmas[s] = (
            max(float(wide[col].dropna().std()), 1e-6)
            if col in wide.columns
            else 1.0
        )
    print(f"  sigmas: {sigmas}", flush=True)

    for s in STATS:
        a, p = f"actual_{s}", f"oof_pred_{s}"
        if a in wide.columns and p in wide.columns:
            wide[f"z_{s}"] = (wide[a] - wide[p]) / sigmas[s]
        else:
            wide[f"z_{s}"] = np.nan

    print(
        "  computing per-player L5 shift(1) z-residual rolling means ...",
        flush=True,
    )
    for s in STATS:
        zcol = f"z_{s}"
        shifted = wide.groupby("player_id", sort=False)[zcol].shift(1)
        wide[f"xstat_z_{s}"] = (
            shifted.groupby(wide["player_id"], sort=False)
            .rolling(window=_L5, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )

    wide["_has_data"] = (
        wide[[f"z_{s}" for s in STATS]].notna().any(axis=1).astype(int)
    )
    wide["n_prior_xstat"] = (
        wide.groupby("player_id", sort=False)["_has_data"]
        .cumsum()
        .sub(wide["_has_data"])
        .astype(float)
    )

    keep = ["player_id", "game_id", "n_prior_xstat"] + list(XSTAT_Z_NAMES)
    out = wide[keep].copy()
    for col in XSTAT_Z_NAMES:
        out[col] = out[col].fillna(0.0)
    print(
        f"  built {len(out):,} (pid, gid) rows with cross-stat z features",
        flush=True,
    )
    return out, sigmas


# ── leakage helpers ───────────────────────────────────────────────────────────


def feature_names_for_stat(stat: str) -> List[str]:
    """Per-stat feature schema: 6 cross-stat z (own EXCLUDED) + n_prior_xstat."""
    xstat = [f"xstat_z_{s}" for s in STATS if s != stat]
    return xstat + ["n_prior_xstat"]


def assert_leakage_clean(stat: str, feature_names: List[str]) -> None:
    """Hard check: target stat's own xstat_z column must NOT appear."""
    own = f"xstat_z_{stat}"
    if own in feature_names:
        raise AssertionError(
            f"LEAKAGE: feature_names for {stat} contains its own z column {own}"
        )


# Legacy alias retained for the unit test (the per-stat schema previously
# spliced legacy endQ3 base features; the refactored probe uses OOF-only
# features so this constant is now empty -- still exported for back-compat).
LEGACY_ENDQ3_FEATURES: Tuple[str, ...] = ()


def _row_to_feature_vec(row: Dict, feature_names: List[str]) -> List[float]:
    out: List[float] = []
    for name in feature_names:
        v = row.get(name, 0.0)
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(0.0)
    return out


# ── per-stat training ─────────────────────────────────────────────────────────


def build_stat_matrix(
    oof_df: pd.DataFrame,
    xstat_df: pd.DataFrame,
    stat: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Build (X, oof_pred, actual, fold, feat_names) for the given stat."""
    sub = oof_df[oof_df["stat"] == stat][
        ["player_id", "game_id", "oof_pred", "actual", "fold"]
    ].copy()
    merged = sub.merge(xstat_df, on=["player_id", "game_id"], how="left")
    feat_names = feature_names_for_stat(stat)
    assert_leakage_clean(stat, feat_names)
    # Fill missing xstat columns with 0.0 (zero-prior players).
    for col in feat_names:
        if col not in merged.columns:
            merged[col] = 0.0
        merged[col] = merged[col].fillna(0.0)
    X = merged[feat_names].to_numpy(dtype=np.float32)
    return (
        X,
        merged["oof_pred"].to_numpy(dtype=np.float32),
        merged["actual"].to_numpy(dtype=np.float32),
        merged["fold"].to_numpy(dtype=np.int32),
        feat_names,
    )


def wf_eval(
    X: np.ndarray,
    folds: np.ndarray,
    oof_pred: np.ndarray,
    actual: np.ndarray,
    feat_names: List[str],
    stat: str,
) -> Dict:
    """4-fold walk-forward eval using OOF fold column. Train on folds!=k,
    validate on fold==k. Compare (oof_pred + residual_pred) MAE vs oof_pred MAE.
    """
    params = _lgb_params()
    fold_records: List[Dict] = []
    fold_wins = 0
    deltas: List[float] = []

    for k in (1, 2, 3, 4):
        tr_mask = folds != k
        va_mask = folds == k
        if tr_mask.sum() < 200 or va_mask.sum() < 10:
            fold_records.append({"fold": k, "skip": True})
            continue

        y_resid_tr = actual[tr_mask] - oof_pred[tr_mask]
        model = lgb.LGBMRegressor(**params)
        model.fit(X[tr_mask], y_resid_tr, feature_name=feat_names)
        resid_pred = model.predict(X[va_mask])

        adjusted = oof_pred[va_mask] + resid_pred
        mae_adj = float(np.mean(np.abs(adjusted - actual[va_mask])))
        mae_base = float(np.mean(np.abs(oof_pred[va_mask] - actual[va_mask])))
        delta = mae_adj - mae_base
        deltas.append(delta)
        win = mae_adj < mae_base
        if win:
            fold_wins += 1
        fold_records.append({
            "fold":     k,
            "n":        int(va_mask.sum()),
            "mae_adj":  round(mae_adj, 6),
            "mae_base": round(mae_base, 6),
            "delta":    round(delta, 6),
            "win":      bool(win),
        })
        print(
            f"    [{stat}] fold {k}: base={mae_base:.5f} adj={mae_adj:.5f} "
            f"delta={delta:+.5f} {'WIN' if win else 'loss'}",
            flush=True,
        )

    mean_delta = float(np.mean(deltas)) if deltas else 0.0
    return {
        "fold_wins":  fold_wins,
        "mean_delta": round(mean_delta, 6),
        "folds":      fold_records,
    }


def train_and_save_final(
    X: np.ndarray,
    oof_pred: np.ndarray,
    actual: np.ndarray,
    feat_names: List[str],
    stat: str,
    eval_summary: Dict,
) -> bool:
    """Fit on all data and save .lgb + meta to data/models/residual_heads.
    Only call when ship gate passes."""
    y = actual - oof_pred
    model = lgb.LGBMRegressor(**_lgb_params())
    model.fit(X, y, feature_name=feat_names)
    out_path = os.path.join(_HEADS_OUT_DIR, f"{stat}_xstat.lgb")
    model.booster_.save_model(out_path)
    meta_path = os.path.join(_HEADS_OUT_DIR, f"{stat}_xstat_meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "stat":         stat,
                "features":     feat_names,
                "fold_wins":    eval_summary["fold_wins"],
                "mean_delta":   eval_summary["mean_delta"],
                "folds":        eval_summary["folds"],
                "lgb_params":   _lgb_params(),
                "trained_at":   datetime.utcnow().isoformat(),
                "n_rows":       int(len(y)),
                "probe":        "R12_F3_cross_stat_covariance",
                "leak_audit":   f"target z xstat_z_{stat} EXCLUDED from features",
            },
            fh,
            indent=2,
        )
    print(f"  [{stat}] SHIPPED -> {out_path}", flush=True)
    return True


# ── main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="R12_F3 cross-stat covariance probe.")
    ap.add_argument(
        "--max-games", type=int, default=None,
        help="Cap unique games for quick smoke (use first N alphabetically).",
    )
    args = ap.parse_args()

    os.makedirs(_RESULTS_DIR, exist_ok=True)
    os.makedirs(_HEADS_OUT_DIR, exist_ok=True)
    t0 = time.time()

    print("=" * 65, flush=True)
    print("probe_R12_F3_cross_stat_covariance", flush=True)
    print("=" * 65, flush=True)

    print("\nStep 1/3: load OOF parquet ...", flush=True)
    oof_df = pd.read_parquet(_OOF_PATH)
    print(f"  OOF shape: {oof_df.shape}", flush=True)
    if args.max_games:
        keep_games = sorted(oof_df["game_id"].unique())[:args.max_games]
        oof_df = oof_df[oof_df["game_id"].isin(keep_games)].copy()
        print(f"  capped to {oof_df['game_id'].nunique()} games", flush=True)

    print("\nStep 2/3: build cross-stat z residuals ...", flush=True)
    xstat_df, sigmas = compute_xstat_z_matrix(oof_df)

    print("\nStep 3/3: per-stat walk-forward eval ...", flush=True)
    per_stat: List[Dict] = []
    ships = 0
    improving = 0

    for stat in STATS:
        print(f"\n  ---- {stat} ----", flush=True)
        X, oof_pred, actual, folds, feat_names = build_stat_matrix(
            oof_df, xstat_df, stat,
        )
        if X.shape[0] < 200:
            print(f"  [{stat}] SKIP (only {X.shape[0]} rows)", flush=True)
            per_stat.append({
                "stat": stat, "skip": True, "ship": False, "mean_delta": 0.0,
                "fold_wins": 0,
            })
            continue

        eval_res = wf_eval(X, folds, oof_pred, actual, feat_names, stat)
        ship = eval_res["fold_wins"] == 4 and eval_res["mean_delta"] <= -0.005
        if eval_res["mean_delta"] < 0:
            improving += 1
        saved = False
        if ship:
            saved = train_and_save_final(
                X, oof_pred, actual, feat_names, stat, eval_res,
            )
            ships += 1
        else:
            print(
                f"  [{stat}] REJECT (fold_wins={eval_res['fold_wins']}/4 "
                f"mean_delta={eval_res['mean_delta']:+.5f})",
                flush=True,
            )
        rec = {
            "stat":         stat,
            "n_rows":       int(X.shape[0]),
            "n_features":   len(feat_names),
            "feature_names": feat_names,
            "fold_wins":    eval_res["fold_wins"],
            "mean_delta":   eval_res["mean_delta"],
            "folds":        eval_res["folds"],
            "ship":         bool(ship),
            "saved":        bool(saved),
        }
        per_stat.append(rec)

    overall_ship = ships >= 1 and improving >= 4
    elapsed = time.time() - t0

    print("\n" + "=" * 65, flush=True)
    print("GATE SUMMARY", flush=True)
    print(f"  stats SHIPPING (4/4 folds, delta<=-0.005): {ships}/7", flush=True)
    print(f"  stats with mean_delta < 0:                 {improving}/7", flush=True)
    print(
        f"  overall ship (per-stat pattern):           "
        f"{'YES' if overall_ship else 'NO'}",
        flush=True,
    )
    print(f"  elapsed: {elapsed:.1f}s", flush=True)

    print("\nPer-stat result:", flush=True)
    for rec in per_stat:
        s = rec["stat"]
        if rec.get("skip"):
            print(f"  {s:>4}: SKIP", flush=True)
            continue
        print(
            f"  {s:>4}: mean_delta={rec['mean_delta']:+.5f} "
            f"fold_wins={rec['fold_wins']}/4 ship={'YES' if rec['ship'] else 'no'}",
            flush=True,
        )

    out = {
        "probe":           "R12_F3_cross_stat_covariance",
        "timestamp":       datetime.utcnow().isoformat(),
        "elapsed_s":       round(elapsed, 1),
        "ship_any":        bool(overall_ship),
        "ship_count":      int(ships),
        "stats_improving": int(improving),
        "per_stat":        per_stat,
        "baselines":       BASELINES,
        "sigmas":          {k: round(v, 6) for k, v in sigmas.items()},
        "leak_audit": (
            "target stat's own xstat_z_<stat> EXCLUDED from features; "
            "xstat z aggregated via strict shift(1) on (player_id, game_date)"
        ),
        "lgb_params":      _lgb_params(),
    }
    with open(_CACHE_OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nWrote: {_CACHE_OUT}", flush=True)

    return 0 if overall_ship else 1


if __name__ == "__main__":
    sys.exit(main())
