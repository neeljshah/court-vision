"""
test_archetypes.py — B3 Focused Walk-Forward Test for Player Archetypes

Compares baseline (129 features) vs baseline + cv_archetype one-hot columns
across 4-fold WF using XGB (GPU) + LGB blend for all 7 stats.

Run:
    python scripts/test_archetypes.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")

# Number of archetypes (from build_archetypes.py output)
N_ARCHETYPES = 4  # K=4 was chosen by silhouette


def load_archetype_map() -> dict:
    """Load player_id -> archetype_id map from JSON."""
    path = os.path.join(MODEL_DIR, "player_archetype_map.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"player_archetype_map.json not found at {path}. "
            "Run scripts/build_archetypes.py first."
        )
    with open(path) as f:
        raw = json.load(f)
    # Keys are strings in JSON, values are ints
    return {int(k): int(v) for k, v in raw.items()}


def add_archetype_features(rows: list, archetype_map: dict, n_archetypes: int) -> list:
    """Add one-hot archetype columns + n_games_archetype column to rows.

    One-hot encodes arch_0 through arch_{n_archetypes-1}.
    arch_n_games = number of distinct games the player has in cv_features
    (as a quality weight signal).

    Players without an archetype get all-zero one-hots and n_games=0.
    Returns the list of new column names added.
    """
    arch_cols = [f"arch_{i}" for i in range(n_archetypes)]
    new_cols = arch_cols + ["arch_n_games"]

    # Precompute player game counts from DB for arch_n_games
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT player_id, COUNT(DISTINCT game_id) as n_games "
        "FROM cv_features WHERE feature_name='cv_archetype' "
        "GROUP BY player_id"
    )
    player_ngames = {int(r[0]): int(r[1]) for r in c.fetchall()}
    conn.close()

    for row in rows:
        pid = int(row.get("player_id") or 0)
        arch_id = archetype_map.get(pid, None)
        # One-hot
        for col in arch_cols:
            row[col] = 0.0
        if arch_id is not None:
            row[f"arch_{arch_id}"] = 1.0
        # n_games quality weight
        row["arch_n_games"] = float(player_ngames.get(pid, 0))

    return new_cols


def _train_one_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB (GPU) + LGB blend for one stat. Return MAE + R2."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    is_log = stat in ("stl", "blk", "tov", "fg3m", "reb", "ast")

    # Apply log1p transform (same as production)
    if is_log:
        y_tr_t = np.log1p(y_tr)
        y_val_t = np.log1p(y_val)
    else:
        y_tr_t = y_tr
        y_val_t = y_val

    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=3 if stat in ("stl", "blk") else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
        device="cuda",
        tree_method="hist",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if stat in ("stl", "blk") else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    # Validation predictions for NNLS blend
    xv = xgb_m.predict(X_val)
    lv = lgb_m.predict(X_val)
    xh = xgb_m.predict(X_ho)
    lh = lgb_m.predict(X_ho)

    # NNLS blend weights fit on val
    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val_t)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    blend_h = w[0] * xh + w[1] * lh

    # Back-transform
    if is_log:
        blend_h = np.expm1(blend_h)

    mae = float(mean_absolute_error(y_ho, blend_h))
    r2 = float(r2_score(y_ho, blend_h))
    return mae, r2


def walk_forward(n_splits: int = 4) -> None:
    from src.prediction.prop_pergame import STATS, build_pergame_dataset, feature_columns

    print(f"Loading dataset (n_splits={n_splits}) ...")
    rows, fc_base = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  rows={n}, base_features={len(fc_base)}")

    # Load archetype map + add archetype columns to rows
    print("  Loading archetype map ...")
    archetype_map = load_archetype_map()
    n_mapped = sum(1 for r in rows if int(r.get("player_id") or 0) in archetype_map)
    print(f"  Rows with archetype: {n_mapped}/{n} ({100*n_mapped/n:.1f}%)")

    arch_cols = add_archetype_features(rows, archetype_map, N_ARCHETYPES)
    fc_arch = fc_base + arch_cols
    print(f"  Arch feature columns: {arch_cols}")
    print(f"  Total features with arch: {len(fc_arch)}")

    # Build feature matrices
    X_base = np.array([[r.get(c, 0.0) or 0.0 for c in fc_base] for r in rows], dtype=float)
    X_arch = np.array([[r.get(c, 0.0) or 0.0 for c in fc_arch] for r in rows], dtype=float)

    # Replace NaN / inf
    X_base = np.nan_to_num(X_base, nan=0.0, posinf=0.0, neginf=0.0)
    X_arch = np.nan_to_num(X_arch, nan=0.0, posinf=0.0, neginf=0.0)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]

    # Per-stat fold results: {stat: [(baseline_mae, arch_mae, baseline_r2, arch_r2), ...]}
    results: dict = {s: [] for s in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, te={te_end-tr_end}) -- skip")
            continue

        # Time-decay sample weights
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} ho={te_end-va_end}",
              flush=True)
        t0 = time.time()

        for stat in STATS:
            y = np.array([r.get(f"target_{stat}", 0.0) or 0.0 for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            # Baseline
            b_mae, b_r2 = _train_one_stat(
                stat,
                X_base[:tr_end], y_tr,
                X_base[tr_end:va_end], y_val,
                X_base[va_end:te_end], y_ho,
                sw,
            )
            # +Archetype
            a_mae, a_r2 = _train_one_stat(
                stat,
                X_arch[:tr_end], y_tr,
                X_arch[tr_end:va_end], y_val,
                X_arch[va_end:te_end], y_ho,
                sw,
            )
            results[stat].append((b_mae, a_mae, b_r2, a_r2))

            d_mae = a_mae - b_mae
            sign = "BETTER" if d_mae < 0 else "worse"
            print(
                f"  {stat.upper():4s}  base={b_mae:.4f}  arch={a_mae:.4f}  "
                f"delta={d_mae:+.4f}  [{sign}]",
                flush=True,
            )

        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    # Summary
    print("\n" + "=" * 70)
    print("WALK-FORWARD SUMMARY (mean across completed folds)")
    print("=" * 70)
    print(f"  {'stat':6s}  {'baseline':>10s}  {'arch':>10s}  {'delta':>8s}  {'folds_better':>12s}")
    print("  " + "-" * 55)

    verdicts_ship = []
    verdicts_reject = []

    for stat in STATS:
        folds = results[stat]
        if not folds:
            print(f"  {stat.upper():6s}  (no folds completed)")
            continue
        b_maes = [f[0] for f in folds]
        a_maes = [f[1] for f in folds]
        deltas = [a - b for a, b in zip(a_maes, b_maes)]
        n_better = sum(1 for d in deltas if d < 0)
        mean_b = np.mean(b_maes)
        mean_a = np.mean(a_maes)
        mean_d = np.mean(deltas)

        verdict = "SHIP" if n_better >= 4 else ("MARGINAL" if n_better >= 3 else "REJECT")
        print(
            f"  {stat.upper():6s}  {mean_b:10.4f}  {mean_a:10.4f}  {mean_d:+8.4f}  "
            f"{n_better}/{len(folds)} folds  [{verdict}]"
        )
        if verdict == "SHIP":
            verdicts_ship.append(stat)
        else:
            verdicts_reject.append(stat)

    print()
    print(f"  SHIP:   {verdicts_ship or 'none'}")
    print(f"  REJECT: {verdicts_reject}")

    # Full report
    print("\n" + "=" * 70)
    print("B3 Player Archetypes -- Final Report")
    print("=" * 70)
    print()
    print("Data + clustering")
    print(f"  Players with >=2 games used: 230")
    print(f"  K chosen: {N_ARCHETYPES} (best silhouette=0.1999 in K=4..8 sweep)")
    print(f"  Silhouette at K=4: 0.1999   Inertia: 1373.4")
    print()
    print("Archetype interpretation")
    print(f"  ID   N    Label                   Top features (z-scores)")
    print("  " + "-" * 72)
    print(f"  0    41   perimeter_shooter        3pt_pct=+1.62 shots/poss=+0.71 transition=+0.67")
    print(f"  1    59   ball_handler             mid_pct=+1.10 assists=+0.65 touches=+0.63")
    print(f"  2   101   low_usage_role           poss_dur=-0.71 transition=-0.64 shots/poss=-0.57")
    print(f"  3    29   paint_big                paint_shot=+2.14 shots/poss=+0.52 mid_pct=-0.44")
    print()
    print("DB writes")
    print(f"  cv_archetype values written: 1056")
    print(f"  Players unclustered: 86 (< 2 games)")
    print()
    print("Focused WF results")
    print(f"  {'stat':6s}  {'baseline':>10s}  {'+archetype':>10s}  {'delta':>8s}  folds_better")
    print("  " + "-" * 58)
    for stat in STATS:
        folds = results[stat]
        if not folds:
            continue
        b_maes = [f[0] for f in folds]
        a_maes = [f[1] for f in folds]
        deltas = [a - b for a, b in zip(a_maes, b_maes)]
        n_better = sum(1 for d in deltas if d < 0)
        mean_b = np.mean(b_maes)
        mean_a = np.mean(a_maes)
        mean_d = np.mean(deltas)
        print(f"  {stat.upper():6s}  {mean_b:10.4f}  {mean_a:10.4f}  {mean_d:+8.4f}  {n_better}/{len(folds)}")


if __name__ == "__main__":
    walk_forward(n_splits=4)
