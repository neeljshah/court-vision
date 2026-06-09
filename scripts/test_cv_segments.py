"""
test_cv_segments.py — X2b Segment Analysis for CV feature impact.

Tests whether CV signal is concentrated in high-usage / star player subsets
rather than diluted across all 100K+ rows.

Segments:
  1. high_usage   — bbref_usg_pct > 25.0
  2. heavy_mins   — l5_min > 28.0
  3. top_50/100/200/300 — top-N players by total season minutes
  4. high_cv      — cv_n_games_cv > 3 (strong CV history)
  5. full_dataset — reference (no filter)

Configs compared per segment:
  - baseline     (no CV features)
  - all_cv_28    (all 27 CV cols + cv_n_games_cv = 28 total)
  - tier1_6      (5 P1 Tier-1 cols + cv_n_games_cv = 6 total)

Stats: reb, pts, ast

Output: data/models/test_cv_segments_results.json + printed report

DO NOT modify src/ files or other test_cv_*.py files.
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
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

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

TIER1_5 = [
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

# Configs to test per segment
CONFIGS = {
    "baseline": [],
    "all_cv_28": ALL_CV_COLS,        # 27 features + cv_n_games = 28 total
    "tier1_6":   TIER1_5,            # 5 Tier-1 features + cv_n_games = 6 total
}

TARGET_STATS = ["reb", "pts", "ast"]
N_SPLITS = 4
TOP_N_LIST = [50, 100, 200, 300]

# Full-dataset reference values from test_cv_isolated_results.json (all_cv_27 = all_cv_28 in this test)
FULL_DATASET_REF = {
    "reb": {
        "baseline": 1.8768,
        "all_cv_28": 1.8741,   # all_cv_27 from isolated run
        "tier1_6":   1.8734,   # tier1_5 from isolated run
    },
    "pts": {
        "baseline": 4.5228,
        "all_cv_28": 4.5323,   # +0.0095 (hurts PTS)
        "tier1_6":   4.5284,   # +0.0056 (hurts PTS)
    },
    "ast": {
        "baseline": 1.3428,
        "all_cv_28": 1.3463,   # +0.0035 (hurts AST)
        "tier1_6":   1.3457,   # +0.0029 (hurts AST)
    },
}


# ---------------------------------------------------------------------------
# Step 1: Load game_id -> game_date map
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
    gd: Dict[str, str] = {}
    import glob as _glob
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


# ---------------------------------------------------------------------------
# Step 2: Load CV data from DB
# ---------------------------------------------------------------------------
def _load_cv_data(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, str, float]]]:
    conn = sqlite3.connect(DB_PATH)
    raw = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
    ).fetchall()
    conn.close()

    by_player: Dict[int, List[Tuple[str, str, float]]] = defaultdict(list)
    n_resolved = n_missing = 0
    for player_id, game_id, feature_name, feature_value in raw:
        gdate = game_date_map.get(game_id)
        if gdate is None:
            n_missing += 1
            continue
        by_player[player_id].append((gdate, feature_name, feature_value))
        n_resolved += 1

    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])

    print(f"  CV rows resolved: {n_resolved}  |  missing game_date: {n_missing}")
    return by_player


def _compute_last5_cv(
    player_id: int,
    row_date: str,
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[Dict[str, float], int]:
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


# ---------------------------------------------------------------------------
# Step 3: Pre-compute full CV augmentation matrix
# ---------------------------------------------------------------------------
def _build_cv_matrix(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[np.ndarray, np.ndarray]:
    n = len(rows)
    n_feats = len(ALL_CV_COLS)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, n_feats), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 10000 == 0 and i > 0:
            print(f"    CV pre-compute: {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
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
# Step 4: Build segment masks
# ---------------------------------------------------------------------------
def _build_segments(
    rows: List[dict],
    cv_n_games: np.ndarray,
    base_cols: List[str],
) -> Dict[str, np.ndarray]:
    """
    Returns dict of segment_name -> boolean mask (len = n_rows).
    """
    n = len(rows)
    masks: Dict[str, np.ndarray] = {}

    # full dataset
    masks["full_dataset"] = np.ones(n, dtype=bool)

    # Segment 1: high_usage (bbref_usg_pct > 25.0)
    usg_col = "bbref_usg_pct"
    if usg_col in base_cols:
        usg_vals = np.array([r.get(usg_col, 0.0) or 0.0 for r in rows], dtype=float)
        masks["high_usage"] = usg_vals > 25.0
    else:
        print(f"  [warn] {usg_col} not in base_cols — skipping high_usage segment")

    # Segment 2: heavy_mins (l5_min > 28.0)
    min_col = "l5_min"
    if min_col in base_cols:
        min_vals = np.array([r.get(min_col, 0.0) or 0.0 for r in rows], dtype=float)
        masks["heavy_mins"] = min_vals > 28.0
    else:
        print(f"  [warn] {min_col} not in base_cols — skipping heavy_mins segment")

    # Segment 3: top-N by total season minutes
    # For each (player_id, season), total up l5_min as proxy for minutes
    # Use n_shots_tracked or pts appearances to count games, then rank
    # More robust: count appearances per player across all seasons, rank by count
    player_season_totals: Dict[int, float] = defaultdict(float)
    for r in rows:
        pid = r.get("player_id", 0) or 0
        mins = r.get("l5_min") or 0.0
        player_season_totals[pid] += mins

    # Rank players by total minutes proxy descending
    sorted_players = sorted(player_season_totals.keys(), key=lambda p: player_season_totals[p], reverse=True)

    for top_n in TOP_N_LIST:
        top_set = set(sorted_players[:top_n])
        masks[f"top_{top_n}"] = np.array([r.get("player_id", 0) in top_set for r in rows], dtype=bool)

    # Segment 4: high_cv_coverage (cv_n_games > 3)
    masks["high_cv"] = cv_n_games > 3

    return masks


# ---------------------------------------------------------------------------
# Step 5: Single fold training
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

    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, preds))


# ---------------------------------------------------------------------------
# Step 6: Walk-forward for a given segment mask
# ---------------------------------------------------------------------------
def _run_wf_segment(
    segment_name: str,
    mask: np.ndarray,
    rows: List[dict],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
    target_stats: List[str],
) -> dict:
    """
    Run 4-fold WF for rows[mask] across target_stats × CONFIGS.

    The WF is chronological within the segment — we keep the chronological
    ordering from the sorted rows list and apply the mask, then split by
    position within the filtered sequence (not by global row index).
    """
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}

    # Extract indices in chronological order (rows already sorted by date)
    seg_indices = np.where(mask)[0]  # global indices, already in date order
    n = len(seg_indices)

    print(f"\n{'='*60}")
    print(f"Segment: {segment_name}  |  n={n} rows")

    if n < 5000:
        print(f"  [SKIP] segment too small (n={n} < 5000)")
        return {"skipped": True, "n_rows": n}

    # Build segment-local arrays
    rows_seg = [rows[i] for i in seg_indices]
    X_base_seg = X_base[seg_indices]
    cv_matrix_seg = cv_matrix[seg_indices]
    cv_n_games_seg = cv_n_games[seg_indices]

    # CV coverage within segment
    cv_covered = int((cv_n_games_seg > 0).sum())
    cv_pct = 100.0 * cv_covered / n
    print(f"  CV coverage: {cv_covered}/{n} = {cv_pct:.1f}%")

    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    results: dict = {stat: {cfg: [] for cfg in CONFIGS} for stat in target_stats}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == N_SPLITS - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 1000 or (te_end - va_end) < 300:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip")
            continue

        # Sample weights
        tr_dates = [datetime.fromisoformat(rows_seg[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n  [fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}",
            flush=True,
        )

        for stat in target_stats:
            y = np.array([r[f"target_{stat}"] for r in rows_seg], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            fold_t0 = time.time()
            for cfg_name, cv_feature_names in CONFIGS.items():
                if cv_feature_names:
                    cv_cols_idx = [feat_idx[f] for f in cv_feature_names if f in feat_idx]
                    cv_extra = cv_matrix_seg[:, cv_cols_idx]
                    cv_ngames_col = cv_n_games_seg.reshape(-1, 1).astype(float)
                    X_aug = np.hstack([X_base_seg, cv_extra, cv_ngames_col])
                else:
                    X_aug = X_base_seg

                X_tr = X_aug[:tr_end]
                X_val_f = X_aug[tr_end:va_end]
                X_ho_f = X_aug[va_end:te_end]

                mae = _train_fold(stat, X_tr, y_tr, X_val_f, y_val, X_ho_f, y_ho, sw)
                results[stat][cfg_name].append(mae)

            elapsed = time.time() - fold_t0
            base_mae = results[stat]["baseline"][-1]
            delta_all = results[stat]["all_cv_28"][-1] - base_mae if results[stat]["all_cv_28"] else float("nan")
            delta_t1 = results[stat]["tier1_6"][-1] - base_mae if results[stat]["tier1_6"] else float("nan")
            print(
                f"    {stat.upper():4s}  base={base_mae:.4f}  "
                f"all_cv_28={delta_all:+.4f}  tier1_6={delta_t1:+.4f}  ({elapsed:.1f}s)",
                flush=True,
            )

    return {
        "n_rows": n,
        "cv_coverage_pct": round(cv_pct, 2),
        "cv_covered_rows": cv_covered,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Step 7: Format report
# ---------------------------------------------------------------------------
def _format_report(
    all_seg_results: Dict[str, dict],
    masks: Dict[str, np.ndarray],
    total_rows: int,
) -> str:
    lines = [
        "",
        "## X2b Segment Analysis — Final Report",
        "",
        "### Segments defined",
        "",
        "| segment | n_rows | % of dataset | cv_coverage |",
        "|---------|-------:|-------------:|------------:|",
    ]

    for seg_name, seg_data in all_seg_results.items():
        n = seg_data.get("n_rows", 0)
        pct = 100.0 * n / total_rows if total_rows > 0 else 0.0
        cv_pct = seg_data.get("cv_coverage_pct", 0.0)
        skipped = seg_data.get("skipped", False)
        tag = " (skipped)" if skipped else ""
        lines.append(f"| {seg_name} | {n:,} | {pct:.1f}% | {cv_pct:.1f}%{tag} |")

    lines += ["", "### Per-segment results", ""]

    for stat in TARGET_STATS:
        lines += [f"#### {stat.upper()}", ""]
        lines.append(
            "| segment | n_rows | baseline | +all_cv_28 | delta | folds_better "
            "| +tier1_6 | delta | folds_better |"
        )
        lines.append(
            "|---------|-------:|---------:|-----------:|------:|:------------"
            "|---------:|------:|:-------------|"
        )

        # Full-dataset reference row first
        ref = FULL_DATASET_REF.get(stat, {})
        if ref:
            ref_base = ref.get("baseline", float("nan"))
            ref_all = ref.get("all_cv_28", float("nan"))
            ref_t1 = ref.get("tier1_6", float("nan"))
            d_all = ref_all - ref_base
            d_t1 = ref_t1 - ref_base
            lines.append(
                f"| full_dataset (ref) | {total_rows:,} | {ref_base:.4f} "
                f"| {ref_all:.4f} | {d_all:+.4f} | 4/4 "
                f"| {ref_t1:.4f} | {d_t1:+.4f} | 4/4 |"
            )

        for seg_name, seg_data in all_seg_results.items():
            if seg_data.get("skipped"):
                lines.append(f"| {seg_name} | {seg_data.get('n_rows', 0):,} | SKIPPED | - | - | - | - | - | - |")
                continue

            n = seg_data["n_rows"]
            res = seg_data.get("results", {})
            stat_res = res.get(stat, {})

            base_folds = stat_res.get("baseline", [])
            all_folds = stat_res.get("all_cv_28", [])
            t1_folds = stat_res.get("tier1_6", [])

            if not base_folds:
                lines.append(f"| {seg_name} | {n:,} | no_folds | - | - | - | - | - | - |")
                continue

            base_mean = float(np.mean(base_folds))

            # all_cv_28
            if all_folds:
                all_mean = float(np.mean(all_folds))
                d_all = all_mean - base_mean
                fb_all = sum(1 for b, a in zip(base_folds, all_folds) if a < b)
                all_str = f"{all_mean:.4f} | {d_all:+.4f} | {fb_all}/{len(base_folds)}"
            else:
                all_mean = float("nan")
                all_str = "n/a | n/a | 0/0"

            # tier1_6
            if t1_folds:
                t1_mean = float(np.mean(t1_folds))
                d_t1 = t1_mean - base_mean
                fb_t1 = sum(1 for b, t in zip(base_folds, t1_folds) if t < b)
                t1_str = f"{t1_mean:.4f} | {d_t1:+.4f} | {fb_t1}/{len(base_folds)}"
            else:
                t1_mean = float("nan")
                t1_str = "n/a | n/a | 0/0"

            lines.append(
                f"| {seg_name} | {n:,} | {base_mean:.4f} | {all_str} | {t1_str} |"
            )

        lines.append("")

    # Verdict section
    lines += ["### Verdict", ""]

    for stat in TARGET_STATS:
        lines.append(f"**{stat.upper()}**")
        best_seg = None
        best_delta = 0.0
        new_ships = []

        for seg_name, seg_data in all_seg_results.items():
            if seg_data.get("skipped"):
                continue
            res = seg_data.get("results", {})
            stat_res = res.get(stat, {})
            base_folds = stat_res.get("baseline", [])
            all_folds = stat_res.get("all_cv_28", [])
            t1_folds = stat_res.get("tier1_6", [])
            if not base_folds:
                continue

            base_mean = float(np.mean(base_folds))

            for cfg_name, cfg_folds in [("all_cv_28", all_folds), ("tier1_6", t1_folds)]:
                if not cfg_folds:
                    continue
                cfg_mean = float(np.mean(cfg_folds))
                delta = cfg_mean - base_mean
                if delta < best_delta:
                    best_delta = delta
                    best_seg = f"{seg_name}/{cfg_name}"
                n_folds = len(base_folds)
                folds_better = sum(1 for b, c in zip(base_folds, cfg_folds) if c < b)
                if folds_better == n_folds and delta < 0:
                    new_ships.append(f"{seg_name}/{cfg_name} (delta={delta:+.4f}, {folds_better}/{n_folds})")

        lines.append(f"- Best segment for CV impact: {best_seg} (delta={best_delta:+.4f})")
        if new_ships:
            lines.append(f"- NEW 4/4 SHIP candidates: {', '.join(new_ships)}")
        else:
            lines.append("- No new 4/4 SHIP found in any segment")

        # Check if stars benefit more than full dataset
        full_ref = FULL_DATASET_REF.get(stat, {})
        if full_ref:
            full_delta_all = full_ref.get("all_cv_28", float("nan")) - full_ref.get("baseline", float("nan"))
            for seg_name in ["high_usage", "top_50", "top_100"]:
                seg_data = all_seg_results.get(seg_name, {})
                if seg_data.get("skipped"):
                    continue
                stat_res = seg_data.get("results", {}).get(stat, {})
                base_folds = stat_res.get("baseline", [])
                all_folds = stat_res.get("all_cv_28", [])
                if not base_folds or not all_folds:
                    continue
                seg_delta = float(np.mean(all_folds)) - float(np.mean(base_folds))
                vs_full = seg_delta - full_delta_all
                direction = "MORE" if vs_full < 0 else "LESS"
                lines.append(
                    f"- CV helps {seg_name} {direction} than full dataset "
                    f"(seg_delta={seg_delta:+.4f} vs full_delta={full_delta_all:+.4f}, diff={vs_full:+.4f})"
                )

        lines.append("")

    lines += ["### Honest read", ""]
    lines.append(
        "- This analysis measures whether CV signal is concentrated in player subsets "
        "or uniformly distributed across all rows."
    )
    lines.append(
        "- A segment showing 4/4 SHIP while the full dataset does not would indicate "
        "a targeted deployment strategy (predict CV-augmented only for high-usage / star players)."
    )
    lines.append(
        "- If high_cv segment shows markedly better delta than others, that is the F1 "
        "finding extended: CV quality (depth of history) matters more than player tier."
    )

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
    print("Step 1: Loading base dataset ...")
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

    # ---- 4. Pre-compute CV augmentation ----
    print("\nStep 4: Pre-computing CV augmentation (last-5 rolling per row) ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    print(f"  Done in {time.time()-t0:.1f}s")
    rows_with_cv = int((cv_n_games > 0).sum())
    full_cv_pct = 100.0 * rows_with_cv / n
    print(f"  Full-dataset CV coverage: {rows_with_cv}/{n} = {full_cv_pct:.1f}%")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Build segment masks ----
    print("\nStep 6: Building segment masks ...")
    masks = _build_segments(rows, cv_n_games, base_cols)
    for seg_name, mask in masks.items():
        cv_in_seg = int((cv_n_games[mask] > 0).sum())
        seg_n = int(mask.sum())
        cv_pct = 100.0 * cv_in_seg / seg_n if seg_n > 0 else 0.0
        print(f"  {seg_name:25s}: {seg_n:7,} rows  ({100.*seg_n/n:.1f}%)  cv_coverage={cv_pct:.1f}%")

    # ---- 7. Run WF for each segment ----
    print(f"\nStep 7: Running WF for each segment × {len(TARGET_STATS)} stats × {len(CONFIGS)} configs ...")
    all_seg_results: Dict[str, dict] = {}

    segment_order = ["full_dataset", "high_usage", "heavy_mins"] + \
                    [f"top_{n}" for n in TOP_N_LIST] + ["high_cv"]

    for seg_name in segment_order:
        if seg_name not in masks:
            print(f"  [skip] {seg_name} — mask not built")
            continue
        mask = masks[seg_name]
        seg_data = _run_wf_segment(
            seg_name, mask, rows, X_base, cv_matrix, cv_n_games, TARGET_STATS
        )
        all_seg_results[seg_name] = seg_data

    # ---- 8. Print report ----
    print("\n" + "=" * 60)
    print("Step 8: Final Report")
    report_text = _format_report(all_seg_results, masks, n)

    # ---- 9. Save JSON ----
    out_path = os.path.join(MODELS_DIR, "test_cv_segments_results.json")

    # Convert numpy arrays to python types for JSON serialization
    def _to_py(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: _to_py(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_py(x) for x in obj]
        return obj

    save_data = {
        "meta": {
            "total_rows": n,
            "full_cv_pct": round(full_cv_pct, 2),
            "target_stats": TARGET_STATS,
            "configs": list(CONFIGS.keys()),
            "segments": list(all_seg_results.keys()),
            "wall_time_s": round(time.time() - t_total, 1),
        },
        "segment_results": _to_py(all_seg_results),
        "report": report_text,
    }

    with open(out_path, "w") as f:
        json.dump(save_data, f, indent=2)

    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
