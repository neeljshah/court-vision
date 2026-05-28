"""
Iter 69: Inplay Pregame Shrinkage (endQ1 / endQ2 / endQ3)

Hand-tuned shrinkage between polarity-corrected pregame_win_prob and
isotonic-calibrated in-play model predictions:

    blended = (1 - alpha) * pregame_corrected + alpha * model_pred

where pregame_corrected = 1.0 - sim_win_prob (the raw sim_win_prob is
polarity-INVERTED — global AUC vs home_won = 0.434 — so we flip it).

For each snapshot we WF-grid alpha in {0.0, 0.1, ..., 1.0} and pick the
alpha that minimizes mean WF Brier subject to no fold regressing > 0.005
vs alpha=1.0 (pure model). Ship if mean delta vs alpha=1.0 <= -0.001.

READ-ONLY:
  - data/models/inplay_winprob_endq{1,2,3}.lgb / _meta.json
  - data/models/inplay_isotonic_endq{1,2,3}.joblib
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
from sklearn.metrics import brier_score_loss

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
MODEL_DIR = os.path.join(PROJECT, "data", "models")
OUT_JSON = os.path.join(DATA_CACHE, "iter69_inplay_shrink_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)

MINUTES_PER_QUARTER = 12.0
SNAPSHOTS = ["endQ1", "endQ2", "endQ3"]
N_FOLDS = 4
SEED = 42
ALPHA_GRID = [round(x, 2) for x in np.arange(0.0, 1.0001, 0.1)]
REGRESSION_TOL = 0.005       # fold-level guardrail
SHIP_DELTA = -0.001          # mean WF Brier improvement vs alpha=1.0

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


# ── Data loading (mirrors iter62) ─────────────────────────────────────────────

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
                "pregame_win_prob": pregame_wp,   # raw (polarity-inverted)
                "home_team_won": home_team_won,
            })
    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    valid = set(df[df["snapshot"] == "endQ3"]["game_id"].tolist())
    df = df[df["game_id"].isin(valid)].copy().reset_index(drop=True)
    return df


# ── WF split (matches iter62) ──────────────────────────────────────────────────

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


# ── Per-snapshot OOS prediction generation ────────────────────────────────────

def generate_oos_preds(snapshot: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Train fresh per-fold models (same procedure as iter62), produce OOS
    raw preds, then apply Iter 62 isotonic overlay.

    Returns per-fold:
      - raw_pred, iso_pred (model_pred), pregame_corrected, y_true
    """
    feat_cols = SNAP_FEATURES[snapshot]
    sub = df[df["snapshot"] == snapshot].copy().reset_index(drop=True)
    X = sub[feat_cols].copy()
    y = sub["home_team_won"].copy().astype(int)
    # Polarity-correct sim_win_prob (raw is inverted; global AUC=0.434)
    pregame_corrected = 1.0 - sub["pregame_win_prob"].astype(float).values
    pregame_corrected = np.clip(pregame_corrected, 1e-7, 1 - 1e-7)

    cat_cols = [c for c in ["home_team_id", "season"] if c in X.columns]
    for c in cat_cols:
        X[c] = X[c].astype("category")

    # Load iter62 isotonic overlay
    iso_path = os.path.join(MODEL_DIR, f"inplay_isotonic_{snapshot.lower()}.joblib")
    iso_blob = joblib.load(iso_path)
    iso = iso_blob["isotonic"]

    n = len(X)
    splits = wf_splits(n)
    print(f"\n=== {snapshot} ===  rows={n}, WF splits={[(s[0], s[1], s[2]) for s in splits]}")

    fold_data: List[Dict[str, Any]] = []
    for fold, (train_end, test_start, test_end) in enumerate(splits):
        if train_end < 30 or test_start >= n:
            continue
        X_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        X_te, y_te = X.iloc[test_start:test_end], y.iloc[test_start:test_end]
        if len(X_te) < 10:
            continue
        pg_te = pregame_corrected[test_start:test_end]

        model = lgb.LGBMClassifier(n_jobs=4, verbose=-1, **HYPERPARAMS)
        model.fit(X_tr, y_tr,
                  categorical_feature=cat_cols if cat_cols else "auto")
        raw_te = model.predict_proba(X_te)[:, 1]
        # Apply isotonic overlay (always — Iter 62 trained on all OOS folds)
        iso_te = np.clip(iso.transform(raw_te), 1e-7, 1 - 1e-7)

        fold_data.append({
            "fold": fold,
            "n_test": int(len(X_te)),
            "y_true": y_te.values,
            "model_pred": iso_te,     # isotonic-calibrated
            "pregame_corr": pg_te,
            "raw_pred": raw_te,
        })
        b_raw = brier_score_loss(y_te.values, raw_te)
        b_iso = brier_score_loss(y_te.values, iso_te)
        b_pg = brier_score_loss(y_te.values, pg_te)
        print(f"  fold {fold}: n={len(X_te):4d}  brier_raw={b_raw:.4f}  "
              f"brier_iso={b_iso:.4f}  brier_pg_corr={b_pg:.4f}")
    return {"snapshot": snapshot, "fold_data": fold_data}


# ── Per-snapshot alpha sweep ──────────────────────────────────────────────────

def sweep_alpha(snap_blob: Dict[str, Any]) -> Dict[str, Any]:
    fold_data = snap_blob["fold_data"]
    snapshot = snap_blob["snapshot"]

    # Per-alpha mean Brier and per-fold Brier
    per_alpha: List[Dict[str, Any]] = []
    for alpha in ALPHA_GRID:
        per_fold_brier = []
        for fd in fold_data:
            blended = (1.0 - alpha) * fd["pregame_corr"] + alpha * fd["model_pred"]
            blended = np.clip(blended, 1e-7, 1 - 1e-7)
            per_fold_brier.append(float(brier_score_loss(fd["y_true"], blended)))
        per_alpha.append({
            "alpha": alpha,
            "per_fold_brier": per_fold_brier,
            "mean_brier": float(np.mean(per_fold_brier)),
        })

    # Baseline = alpha=1.0 (pure isotonic-calibrated model)
    baseline = next(r for r in per_alpha if abs(r["alpha"] - 1.0) < 1e-9)
    base_per_fold = baseline["per_fold_brier"]
    base_mean = baseline["mean_brier"]

    # Filter alphas that pass guardrail (no fold regresses by > REGRESSION_TOL)
    candidates = []
    for r in per_alpha:
        delta_per_fold = [r["per_fold_brier"][i] - base_per_fold[i]
                          for i in range(len(base_per_fold))]
        worst_fold_regress = max(delta_per_fold)  # >0 = regression vs baseline
        mean_delta = r["mean_brier"] - base_mean
        r["delta_per_fold"] = delta_per_fold
        r["worst_fold_regress"] = worst_fold_regress
        r["mean_delta"] = mean_delta
        # alpha=1.0 always candidate (delta=0)
        if r["alpha"] == 1.0 or worst_fold_regress <= REGRESSION_TOL:
            candidates.append(r)

    # Pick alpha that minimizes mean Brier among candidates
    best = min(candidates, key=lambda r: r["mean_brier"])
    chosen_alpha = best["alpha"]
    mean_delta = best["mean_delta"]
    ship = (chosen_alpha != 1.0) and (mean_delta <= SHIP_DELTA)

    print(f"\n  [{snapshot}] alpha sweep:")
    for r in per_alpha:
        guard_ok = (r["alpha"] == 1.0) or (r["worst_fold_regress"] <= REGRESSION_TOL)
        marker = "  <-- CHOSEN" if r["alpha"] == chosen_alpha else ""
        print(f"    a={r['alpha']:.2f}  mean_brier={r['mean_brier']:.4f}  "
              f"mean_delta_vs_a1={r['mean_delta']:+.4f}  "
              f"worst_fold_regress={r['worst_fold_regress']:+.4f}  "
              f"guard={'PASS' if guard_ok else 'FAIL'}{marker}")
    print(f"  [{snapshot}] chosen alpha={chosen_alpha}, "
          f"mean_delta_vs_a1.0={mean_delta:+.4f}, ship={ship}")

    return {
        "snapshot": snapshot,
        "alpha_grid": ALPHA_GRID,
        "per_alpha": per_alpha,
        "chosen_alpha": chosen_alpha,
        "baseline_alpha1_mean_brier": base_mean,
        "baseline_alpha1_per_fold_brier": base_per_fold,
        "shrink_mean_brier": best["mean_brier"],
        "shrink_per_fold_brier": best["per_fold_brier"],
        "mean_brier_delta": mean_delta,
        "worst_fold_regress": best["worst_fold_regress"],
        "delta_per_fold": best["delta_per_fold"],
        "regression_tol": REGRESSION_TOL,
        "ship_delta_gate": SHIP_DELTA,
        "ship": bool(ship),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Iter 69: Inplay Pregame Shrinkage ===")
    print(f"  alpha grid: {ALPHA_GRID}")
    print(f"  regression tol: {REGRESSION_TOL}, ship delta: {SHIP_DELTA}")

    print("\n[1] Loading data ...")
    linescores = load_linescores()
    season_games = load_season_games()
    print(f"  linescores: {len(linescores)}, season_games: {len(season_games)}")

    print("\n[2] Building snapshot rows ...")
    df = build_rows(linescores, season_games)
    n_games = df["game_id"].nunique()
    print(f"  total rows: {len(df)} across {n_games} games")

    print("\n[3] Generating OOS preds + alpha sweep per snapshot ...")
    snapshots_out: Dict[str, Any] = {}
    for snap in SNAPSHOTS:
        oos = generate_oos_preds(snap, df)
        sweep = sweep_alpha(oos)
        snapshots_out[snap] = sweep
        # Write per-snapshot alpha JSON
        per_snap_path = os.path.join(
            MODEL_DIR, f"inplay_pregame_shrink_{snap.lower()}.json")
        per_snap = {
            "snapshot": snap,
            "alpha": sweep["chosen_alpha"],
            "baseline_brier": sweep["baseline_alpha1_mean_brier"],
            "shrink_brier": sweep["shrink_mean_brier"],
            "delta": sweep["mean_brier_delta"],
            "per_fold_baseline": sweep["baseline_alpha1_per_fold_brier"],
            "per_fold_shrink": sweep["shrink_per_fold_brier"],
            "per_fold_delta": sweep["delta_per_fold"],
            "worst_fold_regress": sweep["worst_fold_regress"],
            "regression_tol": REGRESSION_TOL,
            "ship": sweep["ship"],
            "iter": "69",
            "trained_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "formula": "blended = (1 - alpha) * (1 - sim_win_prob) + alpha * iso_model_pred",
            "model_source": "data/models/inplay_winprob_{snap}.lgb (READ-ONLY) + "
                            "data/models/inplay_isotonic_{snap}.joblib (READ-ONLY)",
        }
        with open(per_snap_path, "w") as f:
            json.dump(per_snap, f, indent=2)
        print(f"  wrote {per_snap_path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    ship_any = any(s["ship"] for s in snapshots_out.values())
    agg_delta = float(np.mean([s["mean_brier_delta"] for s in snapshots_out.values()]))
    result = {
        "iter": "69",
        "name": "inplay_pregame_shrinkage",
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models_source": "inplay_winprob_endq{1,2,3}.lgb + inplay_isotonic_endq{1,2,3}.joblib (READ-ONLY)",
        "n_folds": N_FOLDS,
        "random_seed": SEED,
        "n_games_total": int(n_games),
        "alpha_grid": ALPHA_GRID,
        "regression_tol": REGRESSION_TOL,
        "ship_delta_gate": SHIP_DELTA,
        "snapshots": snapshots_out,
        "ship_any_snapshot": ship_any,
        "aggregate_mean_brier_delta": agg_delta,
        "elapsed_s": float(time.time() - t0),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n[4] Results written to {OUT_JSON}")
    print("\n=== SUMMARY ===")
    for snap, s in snapshots_out.items():
        print(f"  {snap}: alpha={s['chosen_alpha']}  "
              f"baseline_brier={s['baseline_alpha1_mean_brier']:.4f}  "
              f"shrink_brier={s['shrink_mean_brier']:.4f}  "
              f"delta={s['mean_brier_delta']:+.4f}  "
              f"ship={s['ship']}")
    print(f"  aggregate delta: {agg_delta:+.4f}")
    print(f"  ship any snapshot: {ship_any}")
    print(f"  elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
