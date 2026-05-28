"""
Iter 67: Inplay Dual-Stage Calibration (Platt + Isotonic) on endQ1/Q2/Q3

Hypothesis: A Platt sigmoid first + isotonic adjuster on Platt output
preserves monotonicity AND de-noises small tail bins (n=10-40). May beat
pure isotonic on endQ2/Q3 where Iter 62 pure isotonic over-corrects.

Production .lgb models at data/models/inplay_winprob_endq{1,2,3}.lgb are
READ-ONLY (same as Iter 62). Iter 62 joblibs are also READ-ONLY.

Ship gate (per snapshot):
  - Dual beats the BEST of (raw, iso) by >= 0.001 mean Brier on >=1 snapshot
  - AND >=2/3 cal folds improved vs that best
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "iter67_inplay_dualcal_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42
EPS = 1e-7

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


# ── Data loading (mirrors Iter 62 exactly) ────────────────────────────────────

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
    valid = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid)].copy().reset_index(drop=True)
    return df


# ── Walk-forward split (matches Iter 62 exactly) ──────────────────────────────

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


# ── pkl integrity check (CRLF-safe load) ──────────────────────────────────────

def verify_meta_integrity(snapshot: str) -> Dict:
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
        n_feat_booster = None
        for line in model_text.splitlines()[:200]:
            if line.startswith("max_feature_idx="):
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


# ── Calibration helpers ───────────────────────────────────────────────────────

def fit_platt(p: np.ndarray, y: np.ndarray) -> LogisticRegression:
    """Platt scaling: LR(C=1.0, lbfgs) on raw logit -> labels."""
    p_clip = np.clip(p, EPS, 1 - EPS)
    logit = np.log(p_clip / (1.0 - p_clip)).reshape(-1, 1)
    lr = LogisticRegression(C=1.0, solver="lbfgs")
    lr.fit(logit, y)
    return lr


def apply_platt(lr: LogisticRegression, p: np.ndarray) -> np.ndarray:
    p_clip = np.clip(p, EPS, 1 - EPS)
    logit = np.log(p_clip / (1.0 - p_clip)).reshape(-1, 1)
    return lr.predict_proba(logit)[:, 1]


def fit_dual(p: np.ndarray, y: np.ndarray) -> Tuple[LogisticRegression, IsotonicRegression]:
    """Dual: Platt first, then isotonic on Platt output."""
    platt = fit_platt(p, y)
    platt_out = apply_platt(platt, p)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(platt_out, y)
    return platt, iso


def apply_dual(platt: LogisticRegression, iso: IsotonicRegression,
               p: np.ndarray) -> np.ndarray:
    platt_out = apply_platt(platt, p)
    return iso.transform(platt_out)


# ── Reliability (10-bin) ──────────────────────────────────────────────────────

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
    meta_extras = [c for c in meta["feature_cols"] if c not in feat_cols]
    missing = [c for c in feat_cols if c not in meta["feature_cols"]]
    if missing:
        raise RuntimeError(
            f"Probe feature(s) MISSING from meta [{snapshot}]: {missing}"
        )
    if meta_extras:
        print(f"  [note {snapshot}] meta has extras vs probe: {meta_extras} "
              "(prod model uses superset; cal overlay is feature-agnostic)")

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

        model = lgb.LGBMClassifier(n_jobs=4, verbose=-1, **HYPERPARAMS)
        model.fit(X_tr, y_tr,
                  categorical_feature=cat_cols if cat_cols else "auto")
        raw_te = model.predict_proba(X_te)[:, 1]
        y_te_arr = y_te.values

        brier_raw = float(brier_score_loss(y_te_arr, raw_te))
        ll_raw = float(log_loss(y_te_arr, np.clip(raw_te, EPS, 1 - EPS)))

        if all_raw_preds:
            cal_train_p = np.concatenate(all_raw_preds)
            cal_train_y = np.concatenate(all_labels)

            # Pure isotonic (Iter 62 baseline)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(cal_train_p, cal_train_y)
            iso_te = np.clip(iso.transform(raw_te), EPS, 1 - EPS)
            brier_iso = float(brier_score_loss(y_te_arr, iso_te))
            ll_iso = float(log_loss(y_te_arr, iso_te))

            # Dual: Platt + isotonic
            platt, iso2 = fit_dual(cal_train_p, cal_train_y)
            dual_te = np.clip(apply_dual(platt, iso2, raw_te), EPS, 1 - EPS)
            brier_dual = float(brier_score_loss(y_te_arr, dual_te))
            ll_dual = float(log_loss(y_te_arr, dual_te))

            cal_applied = True
            cal_train_n = int(len(cal_train_p))
        else:
            brier_iso = brier_raw
            ll_iso = ll_raw
            iso_te = raw_te.copy()
            brier_dual = brier_raw
            ll_dual = ll_raw
            dual_te = raw_te.copy()
            cal_applied = False
            cal_train_n = 0

        best_baseline = min(brier_raw, brier_iso)
        delta_dual_vs_best = brier_dual - best_baseline
        improved_dual = bool(delta_dual_vs_best < 0)

        rec = {
            "fold": fold,
            "train_n": int(len(X_tr)),
            "test_n": int(len(X_te)),
            "cal_applied": cal_applied,
            "cal_train_n": cal_train_n,
            "brier_raw": brier_raw,
            "brier_isotonic": brier_iso,
            "brier_dual": brier_dual,
            "best_baseline_brier": best_baseline,
            "delta_dual_vs_best": delta_dual_vs_best,
            "log_loss_raw": ll_raw,
            "log_loss_isotonic": ll_iso,
            "log_loss_dual": ll_dual,
            "improved_dual_vs_best": improved_dual,
        }
        fold_records.append(rec)
        print(f"  Fold {fold}: raw={brier_raw:.4f}, iso={brier_iso:.4f}, "
              f"dual={brier_dual:.4f}, delta_dual_vs_best={delta_dual_vs_best:+.4f}, "
              f"cal={cal_applied}, n_te={len(X_te)}")

        all_raw_preds.append(raw_te)
        all_labels.append(y_te_arr)

    # Fit FINAL dual on all accumulated OOS predictions
    final_p = np.concatenate(all_raw_preds) if all_raw_preds else np.array([])
    final_y = np.concatenate(all_labels) if all_labels else np.array([])
    if len(final_p) > 0:
        final_platt, final_iso = fit_dual(final_p, final_y)
    else:
        final_platt = LogisticRegression(C=1.0, solver="lbfgs")
        final_iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)

    out_path = os.path.join(MODEL_DIR, f"inplay_dualcal_{snapshot.lower()}.joblib")
    joblib.dump({
        "platt": final_platt,
        "isotonic": final_iso,
        "snapshot": snapshot,
        "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_oos_train": int(len(final_p)),
        "iter": "67",
        "note": ("Dual-stage calibrator: apply Platt (LR C=1.0 on logit) then "
                 "isotonic on Platt output. Fit on accumulated OOS WF preds."),
    }, out_path)
    print(f"  Saved final dual calibrator to {out_path}")

    cal_folds = [r for r in fold_records if r["cal_applied"]]
    mean_brier_raw_all = float(np.mean([r["brier_raw"] for r in fold_records])) if fold_records else None
    mean_brier_iso_all = float(np.mean([r["brier_isotonic"] for r in fold_records])) if fold_records else None
    mean_brier_dual_all = float(np.mean([r["brier_dual"] for r in fold_records])) if fold_records else None

    mean_brier_raw_cal = float(np.mean([r["brier_raw"] for r in cal_folds])) if cal_folds else None
    mean_brier_iso_cal = float(np.mean([r["brier_isotonic"] for r in cal_folds])) if cal_folds else None
    mean_brier_dual_cal = float(np.mean([r["brier_dual"] for r in cal_folds])) if cal_folds else None

    # Best-of-(raw,iso) reference
    best_baseline_cal = (
        min(mean_brier_raw_cal, mean_brier_iso_cal)
        if (mean_brier_raw_cal is not None and mean_brier_iso_cal is not None)
        else None
    )
    delta_dual_vs_best_cal = (
        mean_brier_dual_cal - best_baseline_cal
        if (mean_brier_dual_cal is not None and best_baseline_cal is not None)
        else None
    )
    n_improved_dual_cal = int(sum(r["improved_dual_vs_best"] for r in cal_folds))
    n_cal = len(cal_folds)

    return {
        "snapshot": snapshot,
        "n_folds_total": len(fold_records),
        "n_folds_cal_applied": n_cal,
        "n_folds_improved_dual_vs_best": n_improved_dual_cal,
        "mean_brier_raw_all_folds": mean_brier_raw_all,
        "mean_brier_iso_all_folds": mean_brier_iso_all,
        "mean_brier_dual_all_folds": mean_brier_dual_all,
        "mean_brier_raw_cal_folds": mean_brier_raw_cal,
        "mean_brier_iso_cal_folds": mean_brier_iso_cal,
        "mean_brier_dual_cal_folds": mean_brier_dual_cal,
        "best_baseline_brier_cal_folds": best_baseline_cal,
        "delta_dual_vs_best_cal_folds": delta_dual_vs_best_cal,
        "dual_calibrator_path": out_path,
        "final_oos_n": int(len(final_p)),
        "fold_records": fold_records,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 67: Inplay Dual-Stage Calibration (Platt + Isotonic) ===")

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
    print("    Gate: dual beats best-of-(raw,iso) by >= 0.001 mean Brier "
          "AND >=2/3 cal folds improved.")
    ship_summary = {}
    any_snap_ships = False
    for snap, res in snapshots_out.items():
        n_cal = res["n_folds_cal_applied"]
        n_imp = res["n_folds_improved_dual_vs_best"]
        delta = res["delta_dual_vs_best_cal_folds"]
        delta_gate = (delta is not None and delta <= -0.001)
        folds_gate = (n_imp >= 2 and n_cal >= 3) or (n_cal == 2 and n_imp >= 2)
        ship = bool(delta_gate and folds_gate)
        if ship:
            any_snap_ships = True
        ship_summary[snap] = {
            "n_folds_cal_applied": n_cal,
            "n_folds_improved_dual_vs_best": n_imp,
            "mean_brier_raw_cal_folds": res["mean_brier_raw_cal_folds"],
            "mean_brier_iso_cal_folds": res["mean_brier_iso_cal_folds"],
            "mean_brier_dual_cal_folds": res["mean_brier_dual_cal_folds"],
            "best_baseline_brier_cal_folds": res["best_baseline_brier_cal_folds"],
            "delta_dual_vs_best_cal_folds": delta,
            "delta_gate_passed": delta_gate,
            "folds_gate_passed": folds_gate,
            "ship": ship,
        }
        print(f"  {snap}: cal_folds={n_cal}, improved_dual={n_imp}, "
              f"raw={res['mean_brier_raw_cal_folds']:.4f}, "
              f"iso={res['mean_brier_iso_cal_folds']:.4f}, "
              f"dual={res['mean_brier_dual_cal_folds']:.4f}, "
              f"delta_dual_vs_best={delta:+.4f}, ship={ship}")

    deltas = [r["delta_dual_vs_best_cal_folds"] for r in snapshots_out.values()
              if r["delta_dual_vs_best_cal_folds"] is not None]
    agg_delta = float(np.mean(deltas)) if deltas else None

    result = {
        "iter": "67",
        "name": "inplay_dual_stage_platt_isotonic_calibration",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models_source": "data/models/inplay_winprob_endq{1,2,3}.lgb (READ-ONLY)",
        "iter62_isotonic_source": "data/models/inplay_isotonic_endq{1,2,3}.joblib (READ-ONLY reference)",
        "n_folds": N_FOLDS,
        "random_seed": SEED,
        "n_games_total": int(n_games),
        "snapshots": snapshots_out,
        "ship_summary": ship_summary,
        "aggregate_mean_delta_dual_vs_best_cal_folds": agg_delta,
        "any_snap_ships": any_snap_ships,
        "elapsed_s": float(time.time() - t0),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[5] Results written to {OUT_JSON}")
    if agg_delta is not None:
        print(f"  aggregate mean delta_dual_vs_best (cal folds): {agg_delta:+.4f}")
    print(f"  any snapshot ships: {any_snap_ships}")
    print(f"  elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
