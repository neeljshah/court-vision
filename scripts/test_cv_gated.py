"""
test_cv_gated.py — E1 Coverage-Gated Dual Model Architecture test harness.

Architecture:
  - Vanilla model: XGB+LGB trained on ALL rows with baseline features only (no CV)
  - CV-enhanced model: XGB+LGB trained on the SUBSET where cv_n_games_cv > 0,
    using baseline + CV features
  - At prediction time: route by cv_n_games > 0 → cv_model else vanilla_model

Hypothesis: each model operates on its native data domain, avoiding dilution
from sparse-CV zero-fill that degraded the single-model approach.

Run:
    python scripts/test_cv_gated.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

# --- GATE OFF: ensure cv features are not injected by the base dataset -------
os.environ.pop("PROP_USE_CV", None)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np

from src.prediction.prop_pergame import STATS, build_pergame_dataset  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# All 27 CV columns (same order as test_cv_isolated.py)
ALL_CV_COLS = [
    # Original 22 features
    "avg_defender_distance",
    "contested_shot_rate",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
    "avg_spacing",
    "made_pct",
    "avg_shot_clock_at_shot",
    "n_shots_tracked",
    "shots_per_possession",
    "possession_duration_avg",
    "play_type_transition_pct",
    "play_type_drive_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "avg_contest_arm_angle",
    "avg_closeout_speed",
    "avg_fatigue_proxy",
    "catch_shoot_pct",
    "avg_dribble_count",
    "second_chance_rate",
    "avg_shot_distance",
    # P1 Tier-1 features
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

N_SPLITS = 4


# ---------------------------------------------------------------------------
# Data loading helpers (copied from test_cv_isolated.py)
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
    """Return {game_id: 'YYYY-MM-DD'} from all season_games_*.json files."""
    import glob as _glob
    gd: Dict[str, str] = {}
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    for fpath in _glob.glob(os.path.join(nba_dir, "season_games_*.json")):
        try:
            with open(fpath) as f:
                data = json.load(f)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row and "game_date" in row:
                    gd[row["game_id"]] = row["game_date"]
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
    return gd


def _load_cv_data(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, str, float]]]:
    """Load cv_features from DB; return per-player sorted history."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
    ).fetchall()
    conn.close()

    by_player: Dict[int, List[Tuple[str, str, float]]] = defaultdict(list)
    n_resolved = 0
    n_missing_date = 0
    for player_id, game_id, feature_name, feature_value in rows:
        gdate = game_date_map.get(game_id)
        if gdate is None:
            n_missing_date += 1
            continue
        by_player[player_id].append((gdate, feature_name, feature_value))
        n_resolved += 1

    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])

    print(f"  CV rows resolved: {n_resolved}  |  missing game_date: {n_missing_date}")
    return by_player


def _compute_last5_cv(
    player_id: int,
    row_date: str,
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[Dict[str, float], int]:
    """Aggregate the player's last-5 CV games where game_date < row_date."""
    history = by_player.get(player_id, [])
    if not history:
        return {}, 0

    lo, hi = 0, len(history)
    while lo < hi:
        mid = (lo + hi) // 2
        if history[mid][0] < row_date:
            lo = mid + 1
        else:
            hi = mid
    cutoff_idx = lo

    if cutoff_idx == 0:
        return {}, 0

    feature_sums: Dict[str, float] = defaultdict(float)
    feature_counts: Dict[str, int] = defaultdict(int)
    seen_dates: list = []

    for i in range(cutoff_idx - 1, -1, -1):
        gdate, fname, fval = history[i]
        if gdate not in seen_dates:
            seen_dates.append(gdate)
        if len(seen_dates) > 5:
            break
        feature_sums[fname] += fval
        feature_counts[fname] += 1

    n_games = len(seen_dates)
    avgs = {fname: feature_sums[fname] / feature_counts[fname] for fname in feature_sums}
    return avgs, n_games


def _build_cv_matrix(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns:
        cv_matrix  — (n_rows, 27) float array
        cv_n_games — (n_rows,) int array
    """
    n = len(rows)
    n_feats = len(ALL_CV_COLS)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, n_feats), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 10000 == 0 and i > 0:
            elapsed = time.time() - t0
            print(f"    CV pre-compute: {i}/{n} ({elapsed:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        avgs, n_games = _compute_last5_cv(pid, rdate, by_player)
        cv_n_games[i] = n_games
        for fname, val in avgs.items():
            idx = feat_idx.get(fname)
            if idx is not None:
                cv_matrix[i, idx] = val

    return cv_matrix, cv_n_games


# ---------------------------------------------------------------------------
# Dual-model training helpers
# ---------------------------------------------------------------------------
def _make_xgb_vanilla(stat: str):
    """Standard vanilla XGB (400 est, same as test_cv_isolated baseline)."""
    import xgboost as xgb
    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4
    return xgb.XGBRegressor(
        n_estimators=400,
        max_depth=depth,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_lambda=2.0,
        reg_alpha=0.5,
        gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=30,
        eval_metric="mae",
        verbosity=0,
        tree_method="hist",
        device="cuda",
    )


def _make_lgb_vanilla(stat: str):
    """Standard vanilla LGB."""
    import lightgbm as lgb
    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4
    return lgb.LGBMRegressor(
        n_estimators=400,
        max_depth=depth,
        learning_rate=0.05,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1,
        verbosity=-1,
    )


def _make_xgb_cv(stat: str):
    """CV-enhanced XGB — reduced regularisation for smaller training set."""
    import xgboost as xgb
    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4
    return xgb.XGBRegressor(
        n_estimators=300,        # less than 400 — smaller dataset, overfit risk
        max_depth=depth,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,      # lower than 10 for smaller dataset
        reg_lambda=2.0,
        reg_alpha=0.5,
        gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=30,
        eval_metric="mae",
        verbosity=0,
        tree_method="hist",
        device="cuda",
    )


def _make_lgb_cv(stat: str):
    """CV-enhanced LGB — slightly looser for smaller training set."""
    import lightgbm as lgb
    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4
    return lgb.LGBMRegressor(
        n_estimators=300,
        max_depth=depth,
        learning_rate=0.05,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        min_child_samples=10,    # lower than 20 for smaller dataset
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1,
        verbosity=-1,
    )


def _blend_predict(
    xgb_m, lgb_m, X_val: np.ndarray, y_val: np.ndarray, X_ho: np.ndarray
) -> Tuple[np.ndarray, float, float]:
    """
    NNLS-blend XGB+LGB on val set; return holdout predictions and blend weights.
    Returns (preds_ho, w_xgb, w_lgb).
    """
    from sklearn.linear_model import LinearRegression

    xv = xgb_m.predict(X_val)
    lv = lgb_m.predict(X_val)
    xh = xgb_m.predict(X_ho)
    lh = lgb_m.predict(X_ho)

    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return preds, float(w[0]), float(w[1])


# ---------------------------------------------------------------------------
# Per-fold dual-model logic
# ---------------------------------------------------------------------------
def _run_fold_dual(
    stat: str,
    fold_idx: int,
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
    y: np.ndarray,
    tr_end: int,
    va_end: int,
    te_end: int,
    sw: np.ndarray,
) -> dict:
    """
    Run vanilla + CV-gated dual model for one stat on one fold.

    Returns dict with keys:
        vanilla_mae_full      — vanilla model MAE on full holdout
        gated_mae_full        — gated predictions MAE on full holdout
        delta_full            — gated_mae_full - vanilla_mae_full
        n_train_vanilla       — training rows for vanilla
        n_train_cv            — training rows for cv model (cv_n_games > 0)
        n_holdout             — holdout rows
        n_routed_cv           — holdout rows routed to cv_model
        pct_routed            — % holdout routed to cv_model
        vanilla_mae_cv_slice  — vanilla MAE on the cv-eligible holdout slice
        cv_model_mae_cv_slice — cv_model MAE on the same slice
        delta_cv_slice        — cv_model_mae_cv_slice - vanilla_mae_cv_slice
    """
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error

    # ---- Slices ----
    y_tr = y[:tr_end]
    y_val = y[tr_end:va_end]
    y_ho = y[va_end:te_end]

    # Base features only
    X_tr_base = X_base[:tr_end]
    X_val_base = X_base[tr_end:va_end]
    X_ho_base = X_base[va_end:te_end]

    # CV-augmented features (baseline + all 27 CV cols + cv_n_games_cv)
    cv_ngames_col = cv_n_games.reshape(-1, 1).astype(float)
    X_full_cv = np.hstack([X_base, cv_matrix, cv_ngames_col])
    X_tr_full = X_full_cv[:tr_end]
    X_val_full = X_full_cv[tr_end:va_end]
    X_ho_full = X_full_cv[va_end:te_end]

    # CV masks
    mask_tr_cv = cv_n_games[:tr_end] > 0
    mask_val_cv = cv_n_games[tr_end:va_end] > 0
    mask_ho_cv = cv_n_games[va_end:te_end] > 0

    n_train_cv = int(mask_tr_cv.sum())
    n_train_val_cv = int(mask_val_cv.sum())
    n_holdout = te_end - va_end
    n_routed_cv = int(mask_ho_cv.sum())

    # ---------------------------------------------------------------
    # 1. Train VANILLA model (all rows, base features only)
    # ---------------------------------------------------------------
    xgb_v = _make_xgb_vanilla(stat)
    lgb_v = _make_lgb_vanilla(stat)

    xgb_v.fit(
        X_tr_base, y_tr,
        eval_set=[(X_val_base, y_val)],
        sample_weight=sw,
        verbose=False,
    )
    lgb_v.fit(
        X_tr_base, y_tr,
        eval_set=[(X_val_base, y_val)],
        sample_weight=sw,
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )

    vanilla_preds_ho, _, _ = _blend_predict(xgb_v, lgb_v, X_val_base, y_val, X_ho_base)
    vanilla_mae_full = float(mean_absolute_error(y_ho, vanilla_preds_ho))

    # ---------------------------------------------------------------
    # 2. Train CV-ENHANCED model (cv-eligible rows only, all features)
    # ---------------------------------------------------------------
    cv_model_mae_cv_slice = None
    delta_cv_slice = None
    vanilla_mae_cv_slice = None
    gated_mae_full = vanilla_mae_full  # fallback if no cv rows

    if n_train_cv >= 50 and n_train_val_cv >= 10 and n_routed_cv >= 5:
        X_tr_cv_filt = X_tr_full[mask_tr_cv]
        y_tr_cv_filt = y_tr[mask_tr_cv]
        sw_cv_filt = sw[mask_tr_cv]

        X_val_cv_filt = X_val_full[mask_val_cv]
        y_val_cv_filt = y_val[mask_val_cv]

        xgb_c = _make_xgb_cv(stat)
        lgb_c = _make_lgb_cv(stat)

        xgb_c.fit(
            X_tr_cv_filt, y_tr_cv_filt,
            eval_set=[(X_val_cv_filt, y_val_cv_filt)],
            sample_weight=sw_cv_filt,
            verbose=False,
        )
        lgb_c.fit(
            X_tr_cv_filt, y_tr_cv_filt,
            eval_set=[(X_val_cv_filt, y_val_cv_filt)],
            sample_weight=sw_cv_filt,
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )

        # CV-model predictions on holdout cv-eligible slice
        X_ho_cv_filt = X_ho_full[mask_ho_cv]
        y_ho_cv_filt = y_ho[mask_ho_cv]

        cv_preds_slice, _, _ = _blend_predict(
            xgb_c, lgb_c, X_val_cv_filt, y_val_cv_filt, X_ho_cv_filt
        )
        cv_model_mae_cv_slice = float(mean_absolute_error(y_ho_cv_filt, cv_preds_slice))

        # Vanilla predictions on same slice (for direct comparison)
        vanilla_preds_slice = vanilla_preds_ho[mask_ho_cv]
        vanilla_mae_cv_slice = float(mean_absolute_error(y_ho_cv_filt, vanilla_preds_slice))
        delta_cv_slice = cv_model_mae_cv_slice - vanilla_mae_cv_slice

        # Build gated prediction array for FULL holdout
        gated_preds = vanilla_preds_ho.copy()
        gated_preds[mask_ho_cv] = cv_preds_slice
        gated_mae_full = float(mean_absolute_error(y_ho, gated_preds))
    else:
        print(
            f"    [{stat}] fold {fold_idx+1}: cv train too small "
            f"(n_train_cv={n_train_cv}, n_val_cv={n_train_val_cv}, "
            f"n_ho_cv={n_routed_cv}) — gated = vanilla",
            flush=True,
        )

    delta_full = gated_mae_full - vanilla_mae_full
    pct_routed = 100.0 * n_routed_cv / n_holdout if n_holdout > 0 else 0.0

    return {
        "vanilla_mae_full": vanilla_mae_full,
        "gated_mae_full": gated_mae_full,
        "delta_full": delta_full,
        "n_train_vanilla": tr_end,
        "n_train_cv": n_train_cv,
        "n_holdout": n_holdout,
        "n_routed_cv": n_routed_cv,
        "pct_routed": pct_routed,
        "vanilla_mae_cv_slice": vanilla_mae_cv_slice,
        "cv_model_mae_cv_slice": cv_model_mae_cv_slice,
        "delta_cv_slice": delta_cv_slice,
    }


# ---------------------------------------------------------------------------
# Walk-forward runner
# ---------------------------------------------------------------------------
def _run_walk_forward(
    rows: List[dict],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    """
    Run 4-fold WF for all 7 stats, dual-model gating.
    Returns: {stat: [fold_result_dict, ...]}
    """
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    results: dict = {stat: [] for stat in STATS}

    # Track training sizes across folds (stat-independent)
    fold_sizes: List[dict] = []

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == N_SPLITS - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip")
            continue

        # Sample weights — exponential decay by age in years
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        n_train_cv_this = int((cv_n_games[:tr_end] > 0).sum())
        n_ho_cv_this = int((cv_n_games[va_end:te_end] > 0).sum())
        n_ho = te_end - va_end
        fold_sizes.append({
            "fold": fold_idx + 1,
            "n_train_vanilla": tr_end,
            "n_train_cv": n_train_cv_this,
            "pct_cv_train": 100.0 * n_train_cv_this / tr_end if tr_end > 0 else 0.0,
            "n_holdout": n_ho,
            "n_routed_cv": n_ho_cv_this,
            "pct_routed": 100.0 * n_ho_cv_this / n_ho if n_ho > 0 else 0.0,
        })

        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] "
            f"tr={tr_end} (cv={n_train_cv_this}, {100.*n_train_cv_this/tr_end:.1f}%) "
            f"val={va_end-tr_end} ho={n_ho} (cv_eligible={n_ho_cv_this})",
            flush=True,
        )

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)

            fold_t0 = time.time()
            fold_result = _run_fold_dual(
                stat, fold_idx,
                X_base, cv_matrix, cv_n_games,
                y, tr_end, va_end, te_end, sw,
            )
            elapsed = time.time() - fold_t0

            results[stat].append(fold_result)

            v_mae = fold_result["vanilla_mae_full"]
            g_mae = fold_result["gated_mae_full"]
            delta = fold_result["delta_full"]
            marker = "**" if delta < 0 else "  "
            print(
                f"  {marker}{stat.upper():4s}  vanilla={v_mae:.4f}  "
                f"gated={g_mae:.4f}  delta={delta:+.4f}"
                f"  ({elapsed:.1f}s){marker}",
                flush=True,
            )

    return results, fold_sizes


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------
def _print_report(results: dict, fold_sizes: List[dict]) -> None:
    """Print the E1 final report to stdout."""

    print("\n" + "=" * 70)
    print("## E1 Coverage Gating — Final Report")
    print("=" * 70)
    print()
    print("### Setup")
    print("- New tester: scripts/test_cv_gated.py")
    print("- Architecture: dual-model with cv_n_games > 0 gating")
    print("- 4 folds, 7 stats, XGB GPU + LGB")
    print()

    # ---- Training data sizes ----
    print("### Training data sizes")
    print("| fold | n_train (vanilla) | n_train_cv (enhanced) | % of train |")
    print("|------|------------------:|----------------------:|-----------:|")
    for fs in fold_sizes:
        print(
            f"| {fs['fold']} | {fs['n_train_vanilla']:,} | "
            f"{fs['n_train_cv']:,} | {fs['pct_cv_train']:.1f}% |"
        )
    print()

    # ---- Holdout routing ----
    print("### Holdout routing per fold")
    print("| fold | n_holdout | n_routed_to_cv | % routed |")
    print("|------|----------:|---------------:|---------:|")
    for fs in fold_sizes:
        print(
            f"| {fs['fold']} | {fs['n_holdout']:,} | "
            f"{fs['n_routed_cv']:,} | {fs['pct_routed']:.1f}% |"
        )
    print()

    # ---- Per-stat summary ----
    print("### Results per stat")
    print("| stat | vanilla MAE | gated MAE | delta | folds_better | verdict |")
    print("|------|------------:|----------:|------:|:------------:|:-------:|")

    ship_candidates = []
    stat_summaries = {}

    for stat in STATS:
        folds = results[stat]
        if not folds:
            print(f"| {stat} | n/a | n/a | n/a | — | — |")
            continue

        v_maes = [f["vanilla_mae_full"] for f in folds]
        g_maes = [f["gated_mae_full"] for f in folds]

        v_mean = float(np.mean(v_maes))
        g_mean = float(np.mean(g_maes))
        delta_mean = g_mean - v_mean
        folds_better = sum(1 for v, g in zip(v_maes, g_maes) if g < v)
        n_folds = len(folds)

        if folds_better == n_folds:
            verdict = "SHIP"
            ship_candidates.append(stat)
        elif folds_better >= n_folds // 2:
            verdict = "mixed"
        else:
            verdict = "REJECT"

        stat_summaries[stat] = {
            "v_mean": v_mean,
            "g_mean": g_mean,
            "delta_mean": delta_mean,
            "folds_better": folds_better,
            "n_folds": n_folds,
            "verdict": verdict,
        }

        delta_str = f"{delta_mean:+.4f}"
        print(
            f"| {stat} | {v_mean:.4f} | {g_mean:.4f} | {delta_str} "
            f"| {folds_better}/{n_folds} | {verdict} |"
        )

    print()

    # ---- Per-fold detail for 4/4 stats ----
    for stat in ship_candidates:
        folds = results[stat]
        print(f"### Per-fold detail for {stat.upper()} (4/4)")
        print(
            "| fold | vanilla_full | vanilla_cv_slice | cv_model_slice "
            "| delta_slice | n_routed |"
        )
        print("|------|-------------:|-----------------:|---------------:|------------:|---------:|")
        for i, fd in enumerate(folds):
            v_slice = fd["vanilla_mae_cv_slice"]
            c_slice = fd["cv_model_mae_cv_slice"]
            d_slice = fd["delta_cv_slice"]
            v_s = f"{v_slice:.4f}" if v_slice is not None else "n/a"
            c_s = f"{c_slice:.4f}" if c_slice is not None else "n/a"
            d_s = f"{d_slice:+.4f}" if d_slice is not None else "n/a"
            print(
                f"| {i+1} | {fd['vanilla_mae_full']:.4f} | {v_s} | {c_s} "
                f"| {d_s} | {fd['n_routed_cv']} |"
            )
        print()

    # ---- Honest read ----
    print("### Honest read")

    n_improved = sum(1 for s in stat_summaries.values() if s["delta_mean"] < 0)
    n_ship = len(ship_candidates)

    print(f"- Stats with mean gated MAE improvement: {n_improved}/7")
    print(f"- Stats qualifying at 4/4: {n_ship}/7")

    if ship_candidates:
        print(f"- SHIP candidates: {', '.join(ship_candidates)}")
    else:
        print("- No stat passed the 4/4 gate")

    # Compare to existing all_cv_27 result (REB -0.0037 at 4/4 from test_cv_isolated)
    print()
    print("Comparison to single-model all_cv_27 (reference: test_cv_isolated.py):")
    print("  Reference: REB shipped at 4/4 with delta -0.0037 (single model, all_cv_27)")
    print()

    for stat in STATS:
        if stat not in stat_summaries:
            continue
        s = stat_summaries[stat]
        line = (
            f"  {stat.upper():4s}  gated_delta={s['delta_mean']:+.4f}  "
            f"folds_better={s['folds_better']}/{s['n_folds']}"
        )
        if stat == "reb":
            line += "  [vs single-model -0.0037 @ 4/4]"
        if stat in ("ast", "pts"):
            line += "  [AST/PTS — historically hardest]"
        print(line)

    print()

    # Overfit check
    print("Overfit risk assessment (cv_model on small training set):")
    for stat in STATS:
        folds = results[stat]
        if not folds:
            continue
        slice_deltas = [
            f["delta_cv_slice"] for f in folds if f["delta_cv_slice"] is not None
        ]
        if not slice_deltas:
            print(f"  {stat.upper():4s}: no cv-slice data (routing too sparse)")
            continue
        mean_slice_delta = float(np.mean(slice_deltas))
        # If cv_model slice is worse than vanilla on its own domain, likely overfit
        if mean_slice_delta > 0.01:
            print(
                f"  {stat.upper():4s}: cv_model WORSE on cv_slice by {mean_slice_delta:+.4f} "
                f"— possible overfit / underfitting on small train set"
            )
        elif mean_slice_delta < -0.005:
            print(
                f"  {stat.upper():4s}: cv_model genuinely better on cv_slice "
                f"by {mean_slice_delta:+.4f} — healthy signal"
            )
        else:
            print(
                f"  {stat.upper():4s}: cv_model near-parity on cv_slice "
                f"({mean_slice_delta:+.4f}) — marginal"
            )

    print()
    if ship_candidates:
        print(
            "OVERALL: Gated architecture IMPROVES on the 4/4 gate for: "
            + ", ".join(ship_candidates)
        )
    else:
        print(
            "OVERALL: Gated architecture did NOT improve on the 4/4 gate for any stat. "
            "Single-model with all_cv_27 remains the reference."
        )

    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    print("=" * 70)
    print("E1 Coverage-Gated Dual Model Architecture — Walk-Forward Test")
    print("=" * 70)

    # ---- 1. Load dataset ----
    print("\nStep 1: Loading base dataset ...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # ---- 2. Load game_date map ----
    print("\nStep 2: Loading game_date map ...")
    game_date_map = _load_game_date_map()
    print(f"  {len(game_date_map)} game_ids mapped to dates")

    # ---- 3. Load CV data ----
    print("\nStep 3: Loading CV feature data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} distinct players have CV history")

    # ---- 4. Pre-compute CV augmentation matrix ----
    print("\nStep 4: Pre-computing CV augmentation (last-5 rolling per row) ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    elapsed = time.time() - t0
    rows_with_cv = int((cv_n_games > 0).sum())
    pct = 100.0 * rows_with_cv / n
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Total rows: {n}  |  rows with cv_n > 0: {rows_with_cv}  |  coverage: {pct:.2f}%")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Run walk-forward ----
    print(f"\nStep 6: Running {N_SPLITS}-fold dual-model walk-forward for {len(STATS)} stats ...")
    print("  (Each fold trains 2 models per stat: vanilla + cv-enhanced)\n")
    results, fold_sizes = _run_walk_forward(rows, X_base, cv_matrix, cv_n_games)

    # ---- 7. Report ----
    _print_report(results, fold_sizes)

    # ---- 8. Save JSON ----
    out_path = os.path.join(MODELS_DIR, "test_cv_gated_results.json")

    # Serialize results (replace None values for JSON)
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if obj is None:
            return None
        if isinstance(obj, float) and (obj != obj):  # NaN
            return None
        return obj

    with open(out_path, "w") as f:
        json.dump(
            _clean({
                "cv_coverage": {
                    "total_rows": n,
                    "rows_with_cv": rows_with_cv,
                    "pct_covered": round(pct, 4),
                },
                "fold_sizes": fold_sizes,
                "results": {
                    stat: folds for stat, folds in results.items()
                },
                "wall_time_s": round(time.time() - t_total, 1),
            }),
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
