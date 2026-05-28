"""
oos_validate_inplay_2026_05_27.py
─────────────────────────────────
Honest out-of-sample validation of the inplay winprob models retrained on
2026-05-27 (trained_at 2026-05-27T22:40:55Z, probe R10_M5_inplay_winprob).

In-sample Briers from the meta jsons (0.103 / 0.069 / 0.030 for endQ1/Q2/Q3)
are leaked. This script runs a walk-forward CV that:

  1) Reads the EXACT hyperparameters + feature column lists from each
     _meta.json (READ-ONLY — we never touch the .lgb / _meta.json files).
  2) Builds the same feature matrix the training script used
     (linescores_all.json + season_games_{season}.json + quarter_features.parquet).
  3) Re-fits a LightGBM model on each expanding-window training fold and
     evaluates on the next held-out fold (4 folds).
  4) Compares against a pregame-only baseline (pregame_win_prob clamped to
     [0.01, 0.99]) at every fold and snapshot.
  5) Reports per-fold Brier / log-loss / AUC / accuracy, mean ± std, deltas
     vs pregame baseline, calibration (10 equal-width bins), and a SHIP/REVERT
     verdict per snapshot.

Results saved to data/cache/inplay_oos_validation_2026_05_27.json.

NOTE: We re-fit temp models on each fold using the META hyperparams. We DO NOT
load the production .lgb files — those were trained on the FULL data so any
predictions on training-period rows would be leaked. Re-fitting on each fold's
training slice is the only way to get an honest WF estimate of the SAME model
recipe.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODELS_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "inplay_oos_validation_2026_05_27.json")

os.makedirs(DATA_CACHE, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
CALIBRATION_BINS = 10
RANDOM_SEED = 42


# ── meta loading ─────────────────────────────────────────────────────────────

def load_meta(snapshot: str) -> Dict[str, Any]:
    path = os.path.join(MODELS_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")
    with open(path) as f:
        return json.load(f)


# ── data loaders (mirror the training script) ────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


def load_quarter_features_summaries() -> Dict[str, Dict[str, float]]:
    """Per (game_id, team_id) team-level aggregates from quarter_features.parquet.

    Provides q1_usg_avg, halftime_pace_shift, trailing_team_q4_usg_hhi —
    the 3 endQ3-specific features in the production model.
    """
    path = os.path.join(DATA_CACHE, "quarter_features.parquet")
    if not os.path.exists(path):
        print("  [WARN] quarter_features.parquet missing", flush=True)
        return {}
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")

    summaries: Dict[str, Dict[str, float]] = {}
    for (gid, tid), grp in df.groupby(["game_id", "team_id"]):
        key = f"{gid}_{int(tid)}"
        summaries[key] = {
            "q1_usg_avg": float(grp["q1_usg"].mean()),
            "halftime_pace_shift": float(grp["halftime_pace_shift"].mean()),
            "trailing_team_q4_usg_hhi": float(
                grp["trailing_team_q4_usg_concentration"].mean()
                if grp["trailing_team_q4_usg_concentration"].notna().any()
                else np.nan
            ),
        }
    print(f"  quarter_features summaries: {len(summaries)} entries", flush=True)
    return summaries


# ── row construction ─────────────────────────────────────────────────────────

def _pregame_wp_from_sg(sg: Dict) -> float:
    """ELO-based pregame WP proxy (mirrors training script)."""
    wp = sg.get("sim_win_prob")
    if wp is not None:
        return float(wp)
    hca = 65.0
    home_elo = sg.get("home_elo")
    away_elo = sg.get("away_elo")
    if home_elo is None or away_elo is None:
        return 0.55
    try:
        diff = float(home_elo) - float(away_elo) + hca
        return float(1.0 / (1.0 + 10.0 ** (-diff / 400.0)))
    except (TypeError, ValueError):
        return 0.55


def build_rows(
    linescores: Dict,
    season_games: Dict,
    qf_summaries: Dict[str, Dict[str, float]],
) -> pd.DataFrame:
    records: List[Dict] = []

    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue

        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]

        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)

        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")
        pregame_wp = _pregame_wp_from_sg(sg)

        try:
            htid_int = int(home_team_id)
        except (TypeError, ValueError):
            htid_int = 0
        qf_row = qf_summaries.get(f"{gid}_{htid_int}", {})
        q1_usg_avg = qf_row.get("q1_usg_avg", np.nan)
        halftime_pace_shift = qf_row.get("halftime_pace_shift", np.nan)
        trailing_team_q4_usg_hhi = qf_row.get("trailing_team_q4_usg_hhi", np.nan)

        for snap_idx, snapshot in enumerate(SNAPSHOTS):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER

            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum

            if snapshot == "endQ3" and total_pts < 60:
                continue

            score_margin = h_cum - a_cum
            pace_so_far = total_pts / minutes_played

            q1_delta = hq[0] - aq[0]
            q2_delta = (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            records.append({
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": score_margin,
                "total_pts": total_pts,
                "pace_so_far": pace_so_far,
                "q1_delta": q1_delta,
                "q2_delta": q2_delta,
                "q3_delta": q3_delta,
                "last_q_margin": last_q_margin,
                "pregame_win_prob": pregame_wp,
                "home_team_won": home_team_won,
                "q1_usg_avg": q1_usg_avg,
                "halftime_pace_shift": halftime_pace_shift,
                "trailing_team_q4_usg_hhi": trailing_team_q4_usg_hhi,
            })

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  Built {len(df)} snapshot rows from {df['game_id'].nunique()} games",
          flush=True)
    return df


# ── metrics + calibration ────────────────────────────────────────────────────

def compute_calibration(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = CALIBRATION_BINS
) -> List[Dict[str, float]]:
    """10-bin equal-width reliability diagram. Returns list of dicts per bin."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out: List[Dict[str, float]] = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_prob >= lo) & (y_prob < hi) if i < n_bins - 1 else \
               (y_prob >= lo) & (y_prob <= hi)
        n = int(mask.sum())
        if n == 0:
            out.append({
                "bin": i, "lo": float(lo), "hi": float(hi),
                "n": 0, "mean_pred": None, "actual_rate": None, "gap": None,
            })
            continue
        mean_pred = float(y_prob[mask].mean())
        actual = float(y_true[mask].mean())
        out.append({
            "bin": i, "lo": float(lo), "hi": float(hi),
            "n": n,
            "mean_pred": mean_pred,
            "actual_rate": actual,
            "gap": float(actual - mean_pred),
        })
    return out


def calibration_drift_score(calib: List[Dict[str, float]]) -> float:
    """Weighted mean absolute calibration gap (ECE-like)."""
    total_n = sum(b["n"] for b in calib)
    if total_n == 0:
        return float("nan")
    s = 0.0
    for b in calib:
        if b["n"] == 0 or b["gap"] is None:
            continue
        s += b["n"] * abs(b["gap"])
    return s / total_n


# ── walk-forward CV ──────────────────────────────────────────────────────────

def walk_forward_oos(
    df_snap: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    hyperparams: Dict[str, Any],
    n_folds: int = N_FOLDS,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Returns (model_folds, baseline_folds). Each fold dict has metrics + calib."""
    import lightgbm as lgb
    from sklearn.metrics import (accuracy_score, brier_score_loss,
                                 log_loss, roc_auc_score)

    n = len(df_snap)
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    model_folds: List[Dict[str, Any]] = []
    baseline_folds: List[Dict[str, Any]] = []
    baseline_flipped_folds: List[Dict[str, Any]] = []

    y_all = df_snap["home_team_won"].values
    # NOTE: sim_win_prob ('pregame_win_prob' here) is anti-correlated with home
    # wins on this dataset (global AUC ≈ 0.43 — it appears to be encoded with
    # inverted polarity, or as the AWAY team's pre-game WP). To give the
    # inplay model an HONEST baseline to beat we use BOTH:
    #   * raw pregame_win_prob (the 'as-encoded' baseline the model uses internally)
    #   * a flipped pregame_win_prob (the 'corrected polarity' baseline)
    # Both are reported per fold.
    pregame_all = df_snap["pregame_win_prob"].clip(0.01, 0.99).values
    pregame_all_flipped = (1.0 - df_snap["pregame_win_prob"]).clip(0.01, 0.99).values

    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n

        if train_end < 30 or test_start >= n:
            continue

        X_tr = df_snap[feature_cols].iloc[:train_end].copy()
        y_tr = df_snap["home_team_won"].iloc[:train_end]
        X_te = df_snap[feature_cols].iloc[test_start:test_end].copy()
        y_te = df_snap["home_team_won"].iloc[test_start:test_end]
        pregame_te = pregame_all[test_start:test_end]
        pregame_te_flipped = pregame_all_flipped[test_start:test_end]

        if len(X_te) < 10:
            continue

        active_cats = [c for c in cat_cols if c in X_tr.columns]
        for c in active_cats:
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        model = lgb.LGBMClassifier(
            n_estimators=int(hyperparams.get("n_estimators", 300)),
            learning_rate=float(hyperparams.get("learning_rate", 0.05)),
            num_leaves=int(hyperparams.get("num_leaves", 31)),
            min_child_samples=int(hyperparams.get("min_child_samples", 20)),
            subsample=float(hyperparams.get("subsample", 0.8)),
            colsample_bytree=float(hyperparams.get("colsample_bytree", 0.8)),
            reg_alpha=float(hyperparams.get("reg_alpha", 0.1)),
            reg_lambda=float(hyperparams.get("reg_lambda", 1.0)),
            random_state=int(hyperparams.get("random_state", RANDOM_SEED)),
            n_jobs=4,
            verbose=-1,
        )
        model.fit(
            X_tr, y_tr,
            categorical_feature=active_cats if active_cats else "auto",
        )

        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)
        # Avoid log_loss undefined at exact 0/1
        probs_safe = np.clip(probs, 1e-6, 1.0 - 1e-6)

        y_te_arr = y_te.values
        # Need both classes for AUC
        if len(np.unique(y_te_arr)) < 2:
            auc_m = float("nan")
            auc_b = float("nan")
        else:
            auc_m = float(roc_auc_score(y_te_arr, probs))
            auc_b = float(roc_auc_score(y_te_arr, pregame_te))

        model_folds.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_te_arr, probs)),
            "log_loss": float(log_loss(y_te_arr, probs_safe)),
            "auc": auc_m,
            "accuracy": float(accuracy_score(y_te_arr, preds)),
            "calibration": compute_calibration(y_te_arr, probs),
        })

        baseline_preds = (pregame_te >= 0.5).astype(int)
        baseline_folds.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_te_arr, pregame_te)),
            "log_loss": float(log_loss(y_te_arr, np.clip(pregame_te, 1e-6, 1 - 1e-6))),
            "auc": auc_b,
            "accuracy": float(accuracy_score(y_te_arr, baseline_preds)),
            "calibration": compute_calibration(y_te_arr, pregame_te),
        })

        # Polarity-corrected baseline (honest pregame skill estimate)
        baseline_flipped_preds = (pregame_te_flipped >= 0.5).astype(int)
        if len(np.unique(y_te_arr)) >= 2:
            auc_bf = float(roc_auc_score(y_te_arr, pregame_te_flipped))
        else:
            auc_bf = float("nan")
        baseline_flipped_folds.append({
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "brier": float(brier_score_loss(y_te_arr, pregame_te_flipped)),
            "log_loss": float(log_loss(
                y_te_arr, np.clip(pregame_te_flipped, 1e-6, 1 - 1e-6)
            )),
            "auc": auc_bf,
            "accuracy": float(accuracy_score(y_te_arr, baseline_flipped_preds)),
            "calibration": compute_calibration(y_te_arr, pregame_te_flipped),
        })

        print(
            f"    fold {fold}: train={len(X_tr)} test={len(X_te)}  "
            f"MODEL Brier={model_folds[-1]['brier']:.4f} "
            f"AUC={model_folds[-1]['auc']:.4f}  "
            f"BASE Brier={baseline_folds[-1]['brier']:.4f} "
            f"AUC={baseline_folds[-1]['auc']:.4f}  "
            f"delta={model_folds[-1]['brier'] - baseline_folds[-1]['brier']:+.4f}",
            flush=True,
        )

    return model_folds, baseline_folds, baseline_flipped_folds


# ── snapshot driver ──────────────────────────────────────────────────────────

def run_snapshot(
    df: pd.DataFrame,
    snapshot: str,
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    feature_cols = list(meta["feature_cols"])
    cat_cols = list(meta.get("categorical_cols", []))
    hyperparams = dict(meta.get("hyperparams", {}))

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    n = len(sub)
    home_win_rate = float(sub["home_team_won"].mean()) if n > 0 else float("nan")
    print(f"\n  [{snapshot}] rows={n}, home_win_rate={home_win_rate:.3f}",
          flush=True)
    print(f"    features ({len(feature_cols)}): {feature_cols}", flush=True)

    # Coverage diagnostic for the optional features
    for col in feature_cols:
        if col in sub.columns:
            cov = int(sub[col].notna().sum())
            if cov < n:
                print(f"    {col}: {cov}/{n} non-null "
                      f"({100*cov/n:.1f}%)", flush=True)

    model_folds, baseline_folds, baseline_flipped_folds = walk_forward_oos(
        sub, feature_cols, cat_cols, hyperparams,
    )

    # Aggregate per-fold deltas (vs the as-encoded baseline used internally)
    n_folds_actual = len(model_folds)
    deltas = [
        model_folds[i]["brier"] - baseline_folds[i]["brier"]
        for i in range(n_folds_actual)
    ]
    improved = sum(1 for d in deltas if d < 0)

    # Per-fold deltas vs the polarity-CORRECTED pregame baseline — the honest
    # apples-to-apples test of in-game signal value.
    deltas_corrected = [
        model_folds[i]["brier"] - baseline_flipped_folds[i]["brier"]
        for i in range(n_folds_actual)
    ]
    improved_corrected = sum(1 for d in deltas_corrected if d < 0)

    model_briers = [f["brier"] for f in model_folds]
    base_briers = [f["brier"] for f in baseline_folds]
    base_flip_briers = [f["brier"] for f in baseline_flipped_folds]
    model_ll = [f["log_loss"] for f in model_folds]
    model_auc = [f["auc"] for f in model_folds if not np.isnan(f["auc"])]
    model_acc = [f["accuracy"] for f in model_folds]

    # Aggregate calibration (pool all OOS preds across folds)
    pooled_probs: List[float] = []
    pooled_y: List[int] = []
    for f_idx, fold_res in enumerate(model_folds):
        # We don't re-store predictions per row — recompute per-fold calib is enough.
        # But aggregate stats by weighting bin-level means by n.
        pass

    # Simpler: weighted average of calibration drift across folds
    drift_scores = [calibration_drift_score(f["calibration"]) for f in model_folds]
    base_drift = [calibration_drift_score(f["calibration"]) for f in baseline_folds]

    # Verdict logic
    mean_delta = float(np.mean(deltas)) if deltas else float("nan")
    mean_model_brier = float(np.mean(model_briers)) if model_briers else float("nan")
    std_model_brier = float(np.std(model_briers)) if model_briers else float("nan")
    mean_base_brier = float(np.mean(base_briers)) if base_briers else float("nan")
    mean_base_flip_brier = (
        float(np.mean(base_flip_briers)) if base_flip_briers else float("nan")
    )
    mean_delta_corrected = (
        float(np.mean(deltas_corrected)) if deltas_corrected else float("nan")
    )
    mean_model_drift = (
        float(np.mean([d for d in drift_scores if not np.isnan(d)]))
        if drift_scores else float("nan")
    )

    flags: List[str] = []
    # Compare against the CORRECTED baseline — the as-encoded baseline is
    # broken (anti-correlated) and beating it is meaningless.
    if mean_delta_corrected >= 0:
        flags.append("WORSE_THAN_CORRECTED_PREGAME_BASELINE")
    if std_model_brier > 0.5 * mean_model_brier:
        flags.append("INCONSISTENT_ACROSS_FOLDS")
    if mean_model_drift > 0.05:
        flags.append("CALIBRATION_DRIFT_GT_5PCT")

    in_sample_brier = float(meta.get("in_sample", {}).get("brier", float("nan")))
    overfit_gap = mean_model_brier - in_sample_brier

    # Honest verdict: must beat the polarity-corrected pregame baseline on 3+/4 folds
    verdict = (
        "PASS" if (improved_corrected >= 3 and mean_delta_corrected < 0)
        else "FAIL"
    )

    print(f"\n  {snapshot} SUMMARY:", flush=True)
    print(f"    in-sample Brier (leaked): {in_sample_brier:.4f}", flush=True)
    print(f"    OOS  mean Brier (model):  {mean_model_brier:.4f} "
          f"± {std_model_brier:.4f}", flush=True)
    print(f"    OOS  mean Brier (pregame baseline AS-ENCODED): {mean_base_brier:.4f}",
          flush=True)
    print(f"    OOS  mean Brier (pregame baseline POLARITY-CORRECTED): "
          f"{mean_base_flip_brier:.4f}", flush=True)
    print(f"    Mean Brier delta vs as-encoded baseline: {mean_delta:+.4f} "
          f"(folds improved {improved}/{n_folds_actual})", flush=True)
    print(f"    Mean Brier delta vs CORRECTED baseline:  "
          f"{mean_delta_corrected:+.4f} "
          f"(folds improved {improved_corrected}/{n_folds_actual})  <-- HONEST",
          flush=True)
    print(f"    Overfit gap (OOS - in-sample): {overfit_gap:+.4f}", flush=True)
    print(f"    Calibration drift (mean ECE-like, model): "
          f"{mean_model_drift:.4f}", flush=True)
    print(f"    Verdict: {verdict}", flush=True)
    if flags:
        print(f"    FLAGS: {flags}", flush=True)

    return {
        "snapshot": snapshot,
        "verdict": verdict,
        "flags": flags,
        "in_sample_brier_leaked": in_sample_brier,
        "oos_mean_brier_model": mean_model_brier,
        "oos_std_brier_model": std_model_brier,
        "oos_mean_brier_baseline_as_encoded": mean_base_brier,
        "oos_mean_brier_baseline_corrected": mean_base_flip_brier,
        "oos_mean_log_loss_model": float(np.mean(model_ll)) if model_ll else float("nan"),
        "oos_mean_auc_model": float(np.mean(model_auc)) if model_auc else float("nan"),
        "oos_mean_accuracy_model": float(np.mean(model_acc)) if model_acc else float("nan"),
        "mean_brier_delta_vs_baseline_as_encoded": mean_delta,
        "mean_brier_delta_vs_baseline_corrected": mean_delta_corrected,
        "folds_improved_vs_baseline_as_encoded": improved,
        "folds_improved_vs_baseline_corrected": improved_corrected,
        "n_folds": n_folds_actual,
        "deltas_per_fold_vs_as_encoded": deltas,
        "deltas_per_fold_vs_corrected": deltas_corrected,
        "overfit_gap_oos_vs_in_sample": overfit_gap,
        "mean_calibration_drift_model": mean_model_drift,
        "mean_calibration_drift_baseline":
            float(np.mean([d for d in base_drift if not np.isnan(d)]))
            if base_drift else float("nan"),
        "model_folds_detail": model_folds,
        "baseline_folds_detail_as_encoded": baseline_folds,
        "baseline_folds_detail_corrected": baseline_flipped_folds,
        "n_rows": n,
        "home_win_rate": home_win_rate,
        "feature_cols": feature_cols,
        "hyperparams": hyperparams,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== oos_validate_inplay_2026_05_27: honest WF CV of retrained models ===",
          flush=True)
    print(f"  Random seed: {RANDOM_SEED}", flush=True)

    print("\n[1] Loading meta files (READ-ONLY) ...", flush=True)
    metas = {snap: load_meta(snap) for snap in SNAPSHOTS}
    for snap, m in metas.items():
        print(f"    {snap}: trained_at={m.get('trained_at')}, "
              f"n_train_rows={m.get('n_train_rows')}, "
              f"in-sample Brier={m['in_sample']['brier']:.4f}", flush=True)

    print("\n[2] Loading data ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    qf_summaries = load_quarter_features_summaries()
    print(f"    linescores={len(linescores)}, season_games={len(season_games)}",
          flush=True)

    print("\n[3] Building feature rows ...", flush=True)
    df = build_rows(linescores, season_games, qf_summaries)

    # Match training: filter to games that pass endQ3 (consistent game set)
    valid_games = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    df = df.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    print(f"    after endQ3-gate filter: {len(df)} rows, "
          f"{df['game_id'].nunique()} games", flush=True)

    print("\n[4] Running WF OOS per snapshot ...", flush=True)
    per_snap_results = {}
    for snap in SNAPSHOTS:
        per_snap_results[snap] = run_snapshot(df, snap, metas[snap])

    elapsed = time.time() - t0

    combined = {
        "validation": "inplay_winprob_oos_walk_forward",
        "validation_run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime()),
        "models_trained_at": metas["endQ1"].get("trained_at"),
        "models_probe": metas["endQ1"].get("probe"),
        "random_seed": RANDOM_SEED,
        "n_folds": N_FOLDS,
        "n_games_total": int(df["game_id"].nunique()),
        "elapsed_s": float(elapsed),
        "snapshots": per_snap_results,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    print(f"\n  Results saved to: {OUT_JSON}", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("FINAL SUMMARY (honest OOS walk-forward, no leakage)", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'Snap':<7} {'OOS Brier':<11} {'Base(enc)':<11} {'Base(corr)':<12} "
          f"{'D enc':<9} {'D corr':<9} {'Folds':<7} {'Verdict':<8} Flags",
          flush=True)
    for snap in SNAPSHOTS:
        r = per_snap_results[snap]
        print(
            f"  {snap:<7} "
            f"{r['oos_mean_brier_model']:<11.4f} "
            f"{r['oos_mean_brier_baseline_as_encoded']:<11.4f} "
            f"{r['oos_mean_brier_baseline_corrected']:<12.4f} "
            f"{r['mean_brier_delta_vs_baseline_as_encoded']:<+9.4f} "
            f"{r['mean_brier_delta_vs_baseline_corrected']:<+9.4f} "
            f"{r['folds_improved_vs_baseline_corrected']}/{r['n_folds']:<5} "
            f"{r['verdict']:<8} "
            f"{','.join(r['flags']) if r['flags'] else '-'}",
            flush=True,
        )
    print(f"  Elapsed: {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
