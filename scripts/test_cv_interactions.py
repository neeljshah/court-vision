"""
test_cv_interactions.py - Channel D3: CV x coverage interaction features.

Hypothesis: CV features are sparse (11-12% rows). Adding feature x cv_n_games_cv
interactions lets trees conditionally trust CV signals only when coverage is non-zero.

Configs tested:
  baseline             - no CV cols
  cv_only              - 27 raw CV cols + cv_n_games (same as all_cv_27 in isolated tester)
  interactions_only    - 27 interaction cols + cv_n_games (NO raw CV cols)
  cv_plus_interactions - 27 raw CV + 27 interaction cols + cv_n_games (55 CV columns total)

Run:
    python scripts/test_cv_interactions.py
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime

# Force UTF-8 stdout so Unicode delta signs (minus, multiplication) don't crash on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

# GATE OFF: ensure CV features are NOT injected by the base dataset loader
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

ALL_CV_COLS = [
    # Original 22 features (P0/P0.5)
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
    # P1 Tier-1 features (per-frame mining)
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

N_CV_COLS = len(ALL_CV_COLS)  # 27
N_SPLITS = 4

# Configs for D3 interaction test
#   Each entry is a dict with keys:
#     use_raw     (bool) — include the 27 raw CV cols
#     use_inter   (bool) — include the 27 interaction cols (col × cv_n_games)
#     use_ngames  (bool) — include cv_n_games_cv scalar (always True when non-baseline)
CONFIGS = {
    "baseline":             {"use_raw": False, "use_inter": False, "use_ngames": False},
    "cv_only":              {"use_raw": True,  "use_inter": False, "use_ngames": True},
    "interactions_only":    {"use_raw": False, "use_inter": True,  "use_ngames": True},
    "cv_plus_interactions": {"use_raw": True,  "use_inter": True,  "use_ngames": True},
}


# ---------------------------------------------------------------------------
# Step 1: Load game_id -> game_date map from season_games JSON files
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
    """Return {game_id: 'YYYY-MM-DD'} from all season_games_*.json files."""
    gd: Dict[str, str] = {}
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    import glob as _glob
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


# ---------------------------------------------------------------------------
# Step 2: Bulk-load cv_features from DB, aggregate per (player_id, date)
# ---------------------------------------------------------------------------
def _load_cv_data(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, str, float]]]:
    """
    Returns by_player: {player_id: [(game_date, feature_name, value), ...]}
    sorted by game_date ascending (leakage-safe last-5 lookup).
    """
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
    """
    Aggregate the player's last-5 CV games where game_date < row_date (leakage-safe).
    Returns ({feature_name: mean_value, ...}, n_games_contributed).
    """
    history = by_player.get(player_id, [])
    if not history:
        return {}, 0

    # Binary search for cutoff: all entries with date < row_date
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
    avgs = {fname: feature_sums[fname] / feature_counts[fname]
            for fname in feature_sums}
    return avgs, n_games


# ---------------------------------------------------------------------------
# Step 3: Pre-compute CV augmentation matrix + interaction matrix
# ---------------------------------------------------------------------------
def _build_cv_matrix(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
        cv_matrix      — (n_rows, 27) float array, one column per ALL_CV_COLS feature
        cv_interactions— (n_rows, 27) float array, cv_matrix[:, i] * cv_n_games (as float)
        cv_n_games     — (n_rows,)   int array, number of CV games contributing
    """
    n = len(rows)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, N_CV_COLS), dtype=float)
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

    # Interaction columns: raw_col × cv_n_games (scalar broadcast)
    cv_interactions = cv_matrix * cv_n_games.reshape(-1, 1).astype(float)

    return cv_matrix, cv_interactions, cv_n_games


# ---------------------------------------------------------------------------
# Step 4: Walk-forward training (XGB + LGB only, no MLP)
# ---------------------------------------------------------------------------
def _train_fold(
    stat: str,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_ho: np.ndarray,
    y_ho: np.ndarray,
    sw: np.ndarray,
) -> float:
    """Train XGB+LGB, NNLS blend on val, return holdout MAE."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4

    xgb_m = xgb.XGBRegressor(
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
    xgb_m.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        sample_weight=sw,
        verbose=False,
    )

    lgb_m = lgb.LGBMRegressor(
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
    lgb_m.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        sample_weight=sw,
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )

    xv = xgb_m.predict(X_val)
    lv = lgb_m.predict(X_val)
    xh = xgb_m.predict(X_ho)
    lh = lgb_m.predict(X_ho)

    # NNLS blend fit on val
    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, preds))


def _build_X_aug(
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_interactions: np.ndarray,
    cv_n_games: np.ndarray,
    cfg: dict,
) -> np.ndarray:
    """Assemble the full feature matrix for a given config dict."""
    parts = [X_base]
    if cfg["use_raw"]:
        parts.append(cv_matrix)
    if cfg["use_inter"]:
        parts.append(cv_interactions)
    if cfg["use_ngames"]:
        parts.append(cv_n_games.reshape(-1, 1).astype(float))
    return np.hstack(parts)


def _run_walk_forward(
    rows: List[dict],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_interactions: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    """
    Run 4-fold WF for each (stat, config).
    Returns nested dict: results[stat][config_name] = [fold_mae, ...]
    """
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    results: dict = {
        stat: {cfg: [] for cfg in CONFIGS}
        for stat in STATS
    }

    # Pre-build augmented matrices per config (avoid rebuilding inside fold loop)
    X_by_cfg: dict = {
        cfg_name: _build_X_aug(X_base, cv_matrix, cv_interactions, cv_n_games, cfg_dict)
        for cfg_name, cfg_dict in CONFIGS.items()
    }
    for cfg_name, Xfull in X_by_cfg.items():
        print(f"  Config '{cfg_name}': X shape = {Xfull.shape}")

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == N_SPLITS - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) - skip")
            continue

        # Exponential sample weights (decay by age in years)
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}",
            flush=True,
        )

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr  = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho  = y[va_end:te_end]

            fold_t0 = time.time()
            for cfg_name, X_aug in X_by_cfg.items():
                X_tr  = X_aug[:tr_end]
                X_val_fold = X_aug[tr_end:va_end]
                X_ho  = X_aug[va_end:te_end]

                mae = _train_fold(
                    stat, X_tr, y_tr, X_val_fold, y_val, X_ho, y_ho, sw
                )
                results[stat][cfg_name].append(mae)

            fold_elapsed = time.time() - fold_t0
            baseline_mae = results[stat]["baseline"][-1]
            deltas = {
                cfg: results[stat][cfg][-1] - baseline_mae
                for cfg in CONFIGS if cfg != "baseline"
            }
            delta_str = "  ".join(
                f"{cfg}={d:+.4f}" for cfg, d in deltas.items()
            )
            print(
                f"  {stat.upper():4s}  baseline={baseline_mae:.4f}  {delta_str}"
                f"  ({fold_elapsed:.1f}s)",
                flush=True,
            )

    return results


# ---------------------------------------------------------------------------
# Step 5: Format and print D3 summary report
# ---------------------------------------------------------------------------
def _print_summary(
    results: dict,
    cv_coverage_pct: float,
    inter_nonzero_pct: float,
) -> str:
    """Print the D3 markdown report, return as string."""
    cfg_names = list(CONFIGS.keys())
    non_base = [c for c in cfg_names if c != "baseline"]

    header = (
        "| stat | baseline | "
        + " | ".join(f"{c}" for c in non_base)
        + " | best | folds_better |"
    )
    sep = (
        "|------|--------:|"
        + "".join("---------:|" for _ in non_base)
        + ":-------------|:------------:|"
    )

    lines = [
        "",
        "## D3 CV x Coverage Interactions - Final Report",
        "",
        "### Setup",
        f"- New tester: scripts/test_cv_interactions.py",
        f"- Configs: {', '.join(cfg_names)}",
        f"- 27 CV features x {{raw, interaction-with-n_games}} = up to 55 CV columns in cv_plus_interactions",
        "",
        "### Coverage / sparsity check (interaction columns)",
        f"- Rows with cv_n_games > 0 (raw CV coverage):  {cv_coverage_pct:.2f}%",
        f"- Rows where interaction col is non-zero (paint_dwell_pct x n_games): {inter_nonzero_pct:.2f}%",
        f"  NOTE: interaction non-zero only where raw_feature != 0 AND cv_n_games > 0",
        "",
        "### WF results (4-fold, XGB+LGB NNLS blend, MAE - lower is better)",
        "",
        "Delta shown as config_mean - baseline_mean (negative = better than baseline)",
        "",
        header,
        sep,
    ]

    per_stat_best: Dict[str, str] = {}
    per_stat_base_mean: Dict[str, float] = {}
    per_stat_folds_better: Dict[str, str] = {}

    for stat in STATS:
        stat_res = results[stat]
        base_maes = stat_res.get("baseline", [])
        if not base_maes:
            lines.append(f"| {stat} | no folds | - | - | - | - | - |")
            continue
        base_mean = float(np.mean(base_maes))
        per_stat_base_mean[stat] = base_mean

        cfg_means: Dict[str, float] = {}
        col_vals = [f"{base_mean:.4f}"]

        for cfg in non_base:
            cfg_maes = stat_res.get(cfg, [])
            if cfg_maes:
                cm = float(np.mean(cfg_maes))
                delta = cm - base_mean
                cfg_means[cfg] = cm
                if delta < 0:
                    col_vals.append(f"**{cm:.4f} ({delta:+.4f})**")
                else:
                    col_vals.append(f"{cm:.4f} ({delta:+.4f})")
            else:
                cfg_means[cfg] = float("inf")
                col_vals.append("n/a")

        # Best non-baseline config
        best_cfg = min(cfg_means, key=lambda c: cfg_means[c])
        if cfg_means[best_cfg] < base_mean:
            per_stat_best[stat] = best_cfg
        else:
            best_cfg = "baseline"
            per_stat_best[stat] = "baseline"

        # Count folds where best non-baseline beats baseline
        best_non_base = min(cfg_means, key=lambda c: cfg_means[c])
        if best_non_base != "baseline" and cfg_means[best_non_base] < base_mean:
            fold_wins = sum(
                1 for bm, cm in zip(base_maes, stat_res.get(best_non_base, []))
                if cm < bm
            )
            per_stat_folds_better[stat] = f"{fold_wins}/{len(base_maes)}"
        else:
            per_stat_folds_better[stat] = "0/-"

        row = (
            f"| {stat} | "
            + " | ".join(col_vals)
            + f" | {best_cfg} | {per_stat_folds_better[stat]} |"
        )
        lines.append(row)

    lines.append("")

    # --- Verdict section ---
    lines.append("### Verdict")

    # Did interactions help where raw CV failed?
    stats_inter_better_than_cv = []
    stats_cvplus_better_than_cv = []
    stats_inter_degraded = []

    for stat in STATS:
        base_maes = results[stat].get("baseline", [])
        cv_maes = results[stat].get("cv_only", [])
        inter_maes = results[stat].get("interactions_only", [])
        cvplus_maes = results[stat].get("cv_plus_interactions", [])

        if not base_maes:
            continue

        base_mean = per_stat_base_mean[stat]
        cv_mean = float(np.mean(cv_maes)) if cv_maes else float("inf")
        inter_mean = float(np.mean(inter_maes)) if inter_maes else float("inf")
        cvplus_mean = float(np.mean(cvplus_maes)) if cvplus_maes else float("inf")

        # interactions_only beats cv_only
        if inter_mean < cv_mean:
            stats_inter_better_than_cv.append(stat)
        # cv_plus_interactions beats cv_only
        if cvplus_mean < cv_mean:
            stats_cvplus_better_than_cv.append(stat)
        # interactions degrade vs baseline
        if inter_mean > base_mean:
            stats_inter_degraded.append(stat)

    lines.append(
        f"- Stats where interactions_only beats cv_only: "
        + (", ".join(stats_inter_better_than_cv) if stats_inter_better_than_cv else "none")
    )
    lines.append(
        f"- Stats where cv_plus_interactions beats cv_only: "
        + (", ".join(stats_cvplus_better_than_cv) if stats_cvplus_better_than_cv else "none")
    )
    lines.append(
        f"- Stats where interactions_only DEGRADES vs baseline: "
        + (", ".join(stats_inter_degraded) if stats_inter_degraded else "none")
    )
    lines.append("")

    # Ship candidates (beat baseline all 4 folds)
    ship_candidates = []
    for stat in STATS:
        base_maes = results[stat].get("baseline", [])
        for cfg in non_base:
            cfg_maes = results[stat].get(cfg, [])
            if base_maes and cfg_maes:
                wins = sum(1 for b, c in zip(base_maes, cfg_maes) if c < b)
                if wins == len(base_maes):
                    ship_candidates.append(f"{stat}={cfg}")

    if ship_candidates:
        lines.append(f"SHIP CANDIDATES (beat baseline ALL folds): {', '.join(ship_candidates)}")
    else:
        lines.append("No config beat baseline on all folds for any stat.")
    lines.append("")

    # --- Honest read ---
    lines.append("### Honest read")
    lines.append(
        "- Trees CAN learn conditional splits (feature > X AND n_games > 0) without explicit interactions."
    )
    lines.append(
        "- Explicit interactions help only when n_games signal is rare enough that the tree "
        "never gets a clean AND-node - at ~11% sparsity this is plausible but marginal."
    )
    lines.append(
        "- If interactions_only is flat/regresses vs cv_only: the raw feature values are "
        "already zero when n_games=0, so the interaction adds no new information."
    )
    lines.append("")

    # --- Per-fold fold-wins summary ---
    lines.append(
        "Per-stat best config (folds-better / N): "
        + " | ".join(
            f"{stat}={per_stat_best.get(stat,'baseline')} {per_stat_folds_better.get(stat,'0/-')}"
            for stat in STATS
        )
    )
    lines.append("")

    output = "\n".join(lines)
    print(output)
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    # ---- 1. Load dataset ----
    print("=" * 60)
    print("Step 1: Loading base dataset (may take ~30s) ...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # ---- 2. Load game_date map ----
    print("\nStep 2: Loading game_date map from season_games JSON ...")
    game_date_map = _load_game_date_map()
    print(f"  {len(game_date_map)} game_ids mapped to dates")

    # ---- 3. Bulk-load CV data ----
    print("\nStep 3: Loading CV feature data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} distinct players have CV history")

    # ---- 4. Pre-compute CV augmentation + interaction matrices ----
    print("\nStep 4: Pre-computing CV matrix + interaction matrix ...")
    t0 = time.time()
    cv_matrix, cv_interactions, cv_n_games = _build_cv_matrix(rows, by_player)
    elapsed = time.time() - t0

    rows_with_cv = int((cv_n_games > 0).sum())
    cv_coverage_pct = 100.0 * rows_with_cv / n

    # Sparsity of interaction column for paint_dwell_pct (index 24)
    paint_dwell_idx = ALL_CV_COLS.index("paint_dwell_pct")
    inter_nonzero = int((cv_interactions[:, paint_dwell_idx] != 0).sum())
    inter_nonzero_pct = 100.0 * inter_nonzero / n

    print(f"  Done in {elapsed:.1f}s")
    print(f"\n=== CV Coverage Debug ===")
    print(f"  Total rows:                             {n}")
    print(f"  Rows with cv_n_games > 0:               {rows_with_cv}")
    print(f"  Coverage (%):                           {cv_coverage_pct:.2f}%")
    print(f"  cv_interactions shape:                  {cv_interactions.shape}")
    print(f"  paint_dwell_pct x n_games non-zero rows: {inter_nonzero} ({inter_nonzero_pct:.2f}%)")
    print(f"  (should match CV coverage ~{cv_coverage_pct:.1f}%)")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Run walk-forward ----
    print(f"\nStep 6: Running {N_SPLITS}-fold WF for {len(STATS)} stats x {len(CONFIGS)} configs ...")
    results = _run_walk_forward(rows, X_base, cv_matrix, cv_interactions, cv_n_games)

    # ---- 7. Print + save report ----
    print("\nStep 7: D3 Report")
    report_str = _print_summary(results, cv_coverage_pct, inter_nonzero_pct)

    # Save JSON results
    out_json = os.path.join(MODELS_DIR, "test_cv_interactions_results.json")
    with open(out_json, "w") as f:
        json.dump(
            {
                "channel": "D3",
                "cv_coverage": {
                    "total_rows": n,
                    "rows_with_cv": rows_with_cv,
                    "pct_covered": round(cv_coverage_pct, 4),
                    "paint_dwell_inter_nonzero_pct": round(inter_nonzero_pct, 4),
                },
                "configs": {k: v for k, v in CONFIGS.items()},
                "results": results,
                "wall_time_s": round(time.time() - t_total, 1),
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_json}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
