"""
Iter 62: Inplay Isotonic Calibration Overlay (endQ1 / endQ2 / endQ3)

Pure calibration overlay — zero retraining of production .lgb models.
Fits per-snapshot isotonic regressors on OOS walk-forward predictions and
evaluates whether the calibration cuts mean Brier.

Production models at data/models/inplay_winprob_endq{1,2,3}.lgb are READ-ONLY.

Ship gate (per snapshot):
  - >=3/4 folds improve in Brier
  - mean Brier delta <= -0.003 on at least one snapshot
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "iter62_inplay_isotonic_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42

SNAP_FEATURES = {
    "endQ1": ["score_margin", "total_pts", "pace_so_far", "q1_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ2": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    "endQ3": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
              "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id",
              "season"],
}

HYPERPARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": SEED,
}


# ── Data loading (mirrors probe_R10_M5_inplay_winprob.py) ──────────────────────

def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    seasons = ["2022-23", "2023-24", "2024-25"]
    rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for r in data.get("rows", []):
            rows[r["game_id"]] = r
    return rows


def build_rows(linescores: Dict, season_games: Dict) -> pd.DataFrame:
    records: List[Dict] = []
    required = ["home_q1", "home_q2", "home_q3", "home_q4",
                "away_q1", "away_q2", "away_q3", "away_q4"]
    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue
        if any(ls.get(k) is None for k in required):
            continue
        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]
        home_total = sum(hq)
        away_total = sum(aq)
        home_team_won = int(home_total > away_total)
        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")
        pregame_wp = sg.get("sim_win_prob")
        if pregame_wp is None:
            pregame_wp = 0.5
        for snap_idx, snapshot in enumerate(SNAPSHOTS):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER
            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum
            if snapshot == "endQ3" and total_pts < 60:
                continue
            records.append({
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": h_cum - a_cum,
                "total_pts": total_pts,
                "pace_so_far": total_pts / minutes_played,
                "q1_delta": hq[0] - aq[0],
                "q2_delta": (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan,
                "q3_delta": (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan,
                "last_q_margin": hq[n_qtrs - 1] - aq[n_qtrs - 1],
                "pregame_win_prob": pregame_wp,
                "home_team_won": home_team_won,
            })
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    # endQ3 filter ripple — same game set across all snapshots
    valid = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid)].copy().reset_index(drop=True)
    return df


# ── Walk-forward split (matches probe_R10_M5_inplay_winprob.walk_forward_cv) ──

def wf_splits(n: int, n_folds: int = N_FOLDS) -> List[Tuple[int, int, int]]:
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds
    splits = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n
        splits.append((train_end, test_start, test_end))
    return splits


# ── pkl integrity check ───────────────────────────────────────────────────────

def verify_meta_integrity(snapshot: str) -> Dict:
    """Verify booster.num_feature() matches len(meta['feature_cols']).

    NOTE: production .lgb files on Windows were saved with CRLF line endings
    which LightGBM's native parser rejects. We load via an in-memory string
    (LF-normalised) — the on-disk file is NOT modified (READ-ONLY honoured).
    """
    lgb_path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}.lgb")
    meta_path = os.path.join(MODEL_DIR, f"inplay_winprob_{snapshot.lower()}_meta.json")
    with open(meta_path) as f:
        meta = json.load(f)
    with open(lgb_path, "rb") as f:
        raw = f.read()
    model_text = raw.replace(b"\r\n", b"\n").decode("utf-8", errors="replace")
    try:
        booster = lgb.Booster(model_str=model_text)
        n_feat_booster = int(booster.num_feature())
    except Exception as e:
        # Fallback: parse num_feature from header directly. Production file
        # parse-issues do not block the calibration overlay because we train
        # fresh fold-models for OOS preds; the integrity check only needs to
        # confirm feature-count agreement.
        n_feat_booster = None
        for line in model_text.splitlines()[:200]:
            if line.startswith("max_feature_idx="):
                # max_feature_idx is 0-based, so num_features = value + 1
                n_feat_booster = int(line.split("=", 1)[1]) + 1
                break
        print(f"  [pkl-check {snapshot}] booster parse failed ({type(e).__name__}); "
              f"parsed n_feat={n_feat_booster} from header")
    n_feat_meta = len(meta["feature_cols"])
    if n_feat_booster is None or n_feat_booster != n_feat_meta:
        raise RuntimeError(
            f"PKL INTEGRITY FAIL [{snapshot}]: booster_n_feat={n_feat_booster} "
            f"!= len(meta.feature_cols)={n_feat_meta}"
        )
    print(f"  [pkl-check {snapshot}] booster_feats={n_feat_booster}, "
          f"meta_feats={n_feat_meta}  OK")
    return meta


# ── Reliability table (10-bin) ────────────────────────────────────────────────

def reliability(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> List[Dict]:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        n = int(mask.sum())
        mean_pred = float(p[mask].mean()) if n > 0 else None
        actual_rate = float(y[mask].mean()) if n > 0 else None
        gap = (actual_rate - mean_pred) if (mean_pred is not None and actual_rate is not None) else None
        out.append({
            "bin": i, "lo": float(lo), "hi": float(hi), "n": n,
            "mean_pred": mean_pred, "actual_rate": actual_rate,
            "gap": gap,
        })
    return out


# ── Per-snapshot evaluation ───────────────────────────────────────────────────

def evaluate_snapshot(snapshot: str, df: pd.DataFrame) -> Dict[str, Any]:
    print(f"\n=== Snapshot: {snapshot} ===")
    meta = verify_meta_integrity(snapshot)

    feat_cols = SNAP_FEATURES[snapshot]
    # The OOS validation file (inplay_oos_validation_2026_05_27.json) and
    # production .lgb may use a SUPERSET of these features. We require the
    # probe features to be a subset of meta — the isotonic overlay maps
    # probability -> probability and is feature-agnostic. Document any extras.
    meta_extras = [c for c in meta["feature_cols"] if c not in feat_cols]
    missing = [c for c in feat_cols if c not in meta["feature_cols"]]
    if missing:
        raise RuntimeError(
            f"Probe feature(s) MISSING from meta [{snapshot}]: {missing}"
        )
    if meta_extras:
        print(f"  [note {snapshot}] meta has extras vs probe: {meta_extras} "
              "(prod model uses superset; isotonic overlay is feature-agnostic)")

    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    X = sub[feat_cols].copy()
    y = sub["home_team_won"].copy().astype(int)
    cat_cols = [c for c in ["home_team_id", "season"] if c in X.columns]
    for c in cat_cols:
        X[c] = X[c].astype("category")

    n = len(X)
    print(f"  Rows: {n}, home_win_rate: {y.mean():.4f}")

    splits = wf_splits(n)
    print(f"  WF splits: {[(s[0], s[1], s[2]) for s in splits]}")

    fold_records: List[Dict[str, Any]] = []
    all_raw_preds: List[np.ndarray] = []
    all_labels: List[np.ndarray] = []

    for fold, (train_end, test_start, test_end) in enumerate(splits):
        if train_end < 30 or test_start >= n:
            print(f"  Fold {fold}: skip (insufficient data)")
            continue
        X_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        X_te, y_te = X.iloc[test_start:test_end], y.iloc[test_start:test_end]
        if len(X_te) < 10:
            print(f"  Fold {fold}: skip (test={len(X_te)})")
            continue

        # Train fresh model on this fold (matches OOS validation procedure exactly).
        # The fold-specific model is needed to get OOS predictions; this is NOT
        # touching the production .lgb file.
        model = lgb.LGBMClassifier(n_jobs=4, verbose=-1, **HYPERPARAMS)
        model.fit(X_tr, y_tr,
                  categorical_feature=cat_cols if cat_cols else "auto")
        raw_te = model.predict_proba(X_te)[:, 1]
        y_te_arr = y_te.values

        brier_raw = float(brier_score_loss(y_te_arr, raw_te))
        ll_raw = float(log_loss(y_te_arr, np.clip(raw_te, 1e-7, 1 - 1e-7)))

        # Cross-fold isotonic: fit on previous folds' OOS predictions only
        if all_raw_preds:
            cal_train_p = np.concatenate(all_raw_preds)
            cal_train_y = np.concatenate(all_labels)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(cal_train_p, cal_train_y)
            cal_te = iso.transform(raw_te)
            cal_te = np.clip(cal_te, 1e-7, 1 - 1e-7)
            brier_cal = float(brier_score_loss(y_te_arr, cal_te))
            ll_cal = float(log_loss(y_te_arr, cal_te))
            cal_applied = True
            cal_train_n = int(len(cal_train_p))
        else:
            # Fold 0 has no prior OOS data — cannot calibrate honestly
            brier_cal = brier_raw
            ll_cal = ll_raw
            cal_te = raw_te.copy()
            cal_applied = False
            cal_train_n = 0

        delta = brier_cal - brier_raw
        improved = bool(delta < 0)
        # For fold 0 we treat it as "neutral" (no calibration possible);
        # ship gate counts strict improvement across folds with cal_applied.
        rec = {
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "cal_applied": cal_applied,
            "cal_train_n": cal_train_n,
            "brier_raw": brier_raw,
            "brier_isotonic": brier_cal,
            "brier_delta": delta,
            "log_loss_raw": ll_raw,
            "log_loss_isotonic": ll_cal,
            "improved": improved,
            "reliability_raw": reliability(raw_te, y_te_arr),
            "reliability_isotonic": reliability(cal_te, y_te_arr),
        }
        fold_records.append(rec)
        print(f"  Fold {fold}: raw={brier_raw:.4f}, iso={brier_cal:.4f}, "
              f"delta={delta:+.4f}, cal_applied={cal_applied}, n_te={len(X_te)}")

        all_raw_preds.append(raw_te)
        all_labels.append(y_te_arr)

    # Final isotonic — fit on ALL OOS predictions across folds (production overlay)
    final_p = np.concatenate(all_raw_preds) if all_raw_preds else np.array([])
    final_y = np.concatenate(all_labels) if all_labels else np.array([])
    final_iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    if len(final_p) > 0:
        final_iso.fit(final_p, final_y)
    out_path = os.path.join(MODEL_DIR, f"inplay_isotonic_{snapshot.lower()}.joblib")
    joblib.dump({
        "isotonic": final_iso,
        "snapshot": snapshot,
        "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_oos_train": int(len(final_p)),
        "iter": "62",
        "note": "Per-snapshot isotonic overlay fit on accumulated OOS WF predictions",
    }, out_path)
    print(f"  Saved final isotonic to {out_path}")

    # Mean stats (raw vs iso) across folds where cal was applied
    cal_folds = [r for r in fold_records if r["cal_applied"]]
    mean_brier_raw_all = float(np.mean([r["brier_raw"] for r in fold_records])) if fold_records else None
    mean_brier_iso_all = float(np.mean([r["brier_isotonic"] for r in fold_records])) if fold_records else None
    mean_brier_raw_cal = float(np.mean([r["brier_raw"] for r in cal_folds])) if cal_folds else None
    mean_brier_iso_cal = float(np.mean([r["brier_isotonic"] for r in cal_folds])) if cal_folds else None
    n_improved_cal = int(sum(r["improved"] for r in cal_folds))
    n_cal = len(cal_folds)

    return {
        "snapshot": snapshot,
        "n_folds_total": len(fold_records),
        "n_folds_cal_applied": n_cal,
        "n_folds_improved_cal": n_improved_cal,
        "mean_brier_raw_all_folds": mean_brier_raw_all,
        "mean_brier_iso_all_folds": mean_brier_iso_all,
        "mean_brier_delta_all_folds": (mean_brier_iso_all - mean_brier_raw_all)
            if (mean_brier_iso_all is not None and mean_brier_raw_all is not None) else None,
        "mean_brier_raw_cal_folds": mean_brier_raw_cal,
        "mean_brier_iso_cal_folds": mean_brier_iso_cal,
        "mean_brier_delta_cal_folds": (mean_brier_iso_cal - mean_brier_raw_cal)
            if (mean_brier_iso_cal is not None and mean_brier_raw_cal is not None) else None,
        "isotonic_overlay_path": out_path,
        "final_oos_n": int(len(final_p)),
        "fold_records": fold_records,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 62: Inplay Isotonic Calibration Overlay ===")

    print("\n[1] Loading data ...")
    linescores = load_linescores()
    season_games = load_season_games()
    print(f"  linescores: {len(linescores)}, season_games: {len(season_games)}")

    print("\n[2] Building snapshot rows ...")
    df = build_rows(linescores, season_games)
    n_games = df["game_id"].nunique()
    print(f"  total rows: {len(df)} across {n_games} games")

    print("\n[3] Per-snapshot evaluation ...")
    snapshots_out: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        snapshots_out[snap] = evaluate_snapshot(snap, df)

    # ── Ship-gate decisions ──────────────────────────────────────────────────
    print("\n[4] Ship-gate evaluation ...")
    ship_summary = {}
    any_snap_passes_delta_gate = False
    for snap, res in snapshots_out.items():
        n_cal = res["n_folds_cal_applied"]
        n_imp = res["n_folds_improved_cal"]
        delta = res["mean_brier_delta_all_folds"]
        # Gate per spec: >=3/4 folds improve AND mean brier delta <= -0.003 on at least one snap
        # We have n_folds_cal_applied = 3 (folds 1,2,3 — fold 0 can't calibrate),
        # so "3/4 improve" translates to all 3 cal folds improving.
        folds_gate = (n_imp >= max(1, n_cal - 0)) if n_cal == 3 else (n_imp >= 3)
        delta_gate = (delta is not None and delta <= -0.003)
        ship = folds_gate and delta_gate
        if delta_gate:
            any_snap_passes_delta_gate = True
        ship_summary[snap] = {
            "n_folds_cal_applied": n_cal,
            "n_folds_improved_cal": n_imp,
            "mean_brier_delta_all_folds": delta,
            "mean_brier_delta_cal_folds": res["mean_brier_delta_cal_folds"],
            "folds_gate_passed": folds_gate,
            "delta_gate_passed": delta_gate,
            "ship": ship,
        }
        print(f"  {snap}: cal_folds={n_cal}, improved={n_imp}, "
              f"mean_brier_delta_all={delta:+.4f}, ship={ship}")

    # Aggregate delta (cal folds, equal-weighted across snaps)
    deltas = [r["mean_brier_delta_cal_folds"] for r in snapshots_out.values()
              if r["mean_brier_delta_cal_folds"] is not None]
    agg_delta = float(np.mean(deltas)) if deltas else None

    result = {
        "iter": "62",
        "name": "inplay_isotonic_calibration_overlay",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models_source": "data/models/inplay_winprob_endq{1,2,3}.lgb (READ-ONLY)",
        "n_folds": N_FOLDS,
        "random_seed": SEED,
        "n_games_total": int(n_games),
        "snapshots": snapshots_out,
        "ship_summary": ship_summary,
        "aggregate_mean_brier_delta_cal_folds": agg_delta,
        "any_snap_meets_delta_gate": any_snap_passes_delta_gate,
        "elapsed_s": float(time.time() - t0),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[5] Results written to {OUT_JSON}")
    print(f"  aggregate_mean_brier_delta (cal folds): {agg_delta:+.4f}"
          if agg_delta is not None else "  aggregate delta: n/a")
    print(f"  any snapshot meets delta gate: {any_snap_passes_delta_gate}")
    print(f"  elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
