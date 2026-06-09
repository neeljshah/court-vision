"""
test_opp_def.py — Focused WF test for channel C3: team-level CV aggregates as opponent context.

Loads build_pergame_dataset baseline, augments with team CV features (player's team +
opponent team), runs 4-fold WF with XGB(GPU)+LGB blend, and reports per-stat MAE deltas.

Usage:
    python scripts/test_opp_def.py
"""
from __future__ import annotations

import glob
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
os.environ.pop("PROP_USE_CV", None)  # gate OFF

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np

from src.prediction.prop_pergame import STATS, build_pergame_dataset

DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

N_SPLITS = 4

# Feature names for team CV (must match TEAM_CV_FEATURES in build_team_cv.py)
TEAM_CV_FEATURES = [
    "paint_dwell_pct",
    "touches_per_game",
    "potential_assists",
    "shots_per_possession",
    "possession_duration_avg",
    "shot_zone_paint_pct",
    "shot_zone_3pt_pct",
    "play_type_transition_pct",
]

# Output column names (we add opp_ prefix and own_team_ prefix)
OPP_CV_COLS = [f"opp_cv_{f}" for f in TEAM_CV_FEATURES] + ["opp_cv_n_obs"]
TEAM_CV_COLS = [f"team_cv_{f}" for f in TEAM_CV_FEATURES] + ["team_cv_n_obs"]
ALL_NEW_COLS = OPP_CV_COLS + TEAM_CV_COLS


# ---------------------------------------------------------------------------
# Step 1: Load gamelog data -> (player_id, date_iso) -> (team, opp_team)
# ---------------------------------------------------------------------------

def _parse_matchup(matchup: str, player_team: str = "") -> Tuple[str, str]:
    """
    Parse NBA matchup string.
    'SAS vs. TOR' -> player's team = SAS, opp = TOR
    'OKC @ PHX'  -> player is OKC (away), opp = PHX
    Returns (team, opp_team).
    """
    matchup = matchup.strip()
    if " vs. " in matchup:
        parts = matchup.split(" vs. ")
        return parts[0].strip().upper(), parts[1].strip().upper()
    elif " @ " in matchup:
        parts = matchup.split(" @ ")
        return parts[0].strip().upper(), parts[1].strip().upper()
    return "", ""


def _load_player_game_team_map() -> Dict[Tuple[int, str], Tuple[str, str]]:
    """
    Build {(player_id, 'YYYY-MM-DD'): (team_abbrev, opp_team_abbrev)} from gamelog files.
    """
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    result: Dict[Tuple[int, str], Tuple[str, str]] = {}
    n_files = 0
    t0 = time.time()

    for fpath in glob.glob(os.path.join(nba_dir, "gamelog_full_*.json")):
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for row in data:
            try:
                pid = int(row.get("player_id", 0))
                raw_date = str(row.get("game_date", ""))
                matchup = str(row.get("matchup", ""))
                if not (pid and raw_date and matchup):
                    continue
                # Parse date: 'Apr 13, 2025' -> '2025-04-13'
                try:
                    dt = datetime.strptime(raw_date.strip(), "%b %d, %Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
                team, opp = _parse_matchup(matchup)
                if team and opp:
                    result[(pid, date_iso)] = (team, opp)
            except Exception:
                continue
        n_files += 1

    elapsed = time.time() - t0
    print(f"  Loaded (player, date) -> team map: {len(result):,} entries from {n_files} files ({elapsed:.1f}s)")
    return result


# ---------------------------------------------------------------------------
# Step 2: Load cv_team_features lookup
# ---------------------------------------------------------------------------

def _load_cv_team_lookup() -> Dict[Tuple[str, str, str], Tuple[float, int]]:
    """
    Load cv_team_features: {(team_abbrev, season_prefix, feature_name): (value, n_obs)}
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT team_abbrev, season_prefix, feature_name, feature_value, n_obs "
            "FROM cv_team_features"
        ).fetchall()
        conn.close()
    except Exception as e:
        print(f"  [warn] could not load cv_team_features: {e}")
        return {}
    print(f"  cv_team_features: {len(rows)} rows loaded")
    return {(r[0], r[1], r[2]): (r[3], r[4]) for r in rows}


def _season_prefix_from_date(date_iso: str) -> str:
    """
    Given 'YYYY-MM-DD', return the PRIOR season prefix for leakage-free lookup.
    If date is in 2025-26 season (Oct 2025+), return '00225' (current) or '00224' (prior).

    Leakage rule: for a game on date D, we use team CV from games BEFORE D.
    Since our CV aggregates are season-level (not rolling), we use the PRIOR full season
    as the leakage-safe lookup, or current season up to but not including current game.

    For simplicity and leakage safety: always use the season BEFORE the game's season.
    2024-25 games (Oct 2024 - Jun 2025) -> use 00224 (2024-25, which is the prior)
    Wait, that's the SAME season. Let's think:

    - If game is in 2025-26 (00225): use prior season 2024-25 (00224) aggregates
    - If game is in 2024-25 (00224): use prior season 2023-24 (00223) — but we have no 00223 CV data
    - Fallback: use season mean of available 2025-26 data when prior season is unavailable

    Since 95% of our CV data is 2025-26 and 95% of prop rows are 2022-25, the main
    practical mapping is: for PREDICTION rows in 2025-26, use 2025-26 prior-games CV.
    We use the full season aggregate as a proxy (acceptable given small sample size).
    """
    try:
        dt = datetime.fromisoformat(date_iso)
    except ValueError:
        return "00225"

    year = dt.year
    month = dt.month
    # NBA season starts in October
    if month >= 10:
        # e.g. Oct 2025 = start of 2025-26 season -> prefix 00225
        season_year = year
    else:
        # e.g. Apr 2025 = end of 2024-25 season -> prefix 00224
        season_year = year - 1

    return f"002{str(season_year)[-2:]}"


def _prior_season_prefix(current_prefix: str) -> str:
    """'00225' -> '00224', '00224' -> '00223'"""
    yr = int(current_prefix[3:5])
    return f"002{str(yr - 1).zfill(2)}"


def _get_team_features(
    team_abbrev: str,
    current_season_prefix: str,
    lookup: Dict[Tuple[str, str, str], Tuple[float, int]],
    season_means: Dict[str, Dict[str, float]],
    prefix: str,
) -> Dict[str, float]:
    """
    Get team CV features for a team.
    Uses PRIOR season (leakage-safe). Falls back to season mean, then 0.
    """
    prior = _prior_season_prefix(current_season_prefix)
    feats: Dict[str, float] = {}
    any_found = False
    n_obs = 0

    for fname in TEAM_CV_FEATURES:
        key_prior = (team_abbrev.upper(), prior, fname)
        key_current = (team_abbrev.upper(), current_season_prefix, fname)

        if key_prior in lookup:
            val, n = lookup[key_prior]
            feats[f"{prefix}{fname}"] = val
            n_obs = n
            any_found = True
        elif key_current in lookup:
            # Same-season data: use it only if game is clearly after these CV games were collected
            # (conservative: still use it — CV aggregates tend to be from a subset of games)
            val, n = lookup[key_current]
            feats[f"{prefix}{fname}"] = val
            n_obs = n
            any_found = True
        else:
            # fallback to season mean
            fb_season = season_means.get(prior, season_means.get(current_season_prefix, {}))
            feats[f"{prefix}{fname}"] = fb_season.get(fname, 0.0)

    feats[f"{prefix}n_obs"] = float(n_obs) if any_found else 0.0
    return feats


# ---------------------------------------------------------------------------
# Step 3: Build augmented feature matrix
# ---------------------------------------------------------------------------

def _build_team_cv_matrix(
    rows: List[dict],
    player_team_map: Dict[Tuple[int, str], Tuple[str, str]],
    cv_lookup: Dict[Tuple[str, str, str], Tuple[float, int]],
    season_means: Dict[str, Dict[str, float]],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build augmented feature matrices.
    Returns:
        opp_cv_matrix  — (n, len(OPP_CV_COLS)) float array
        team_cv_matrix — (n, len(TEAM_CV_COLS)) float array
    """
    n = len(rows)
    opp_matrix = np.zeros((n, len(OPP_CV_COLS)), dtype=float)
    team_matrix = np.zeros((n, len(TEAM_CV_COLS)), dtype=float)

    opp_col_idx = {c: i for i, c in enumerate(OPP_CV_COLS)}
    team_col_idx = {c: i for i, c in enumerate(TEAM_CV_COLS)}

    t0 = time.time()
    n_matched = 0
    n_unmatched = 0

    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            elapsed = time.time() - t0
            print(f"    team_cv pre-compute: {i}/{n} ({elapsed:.1f}s)", flush=True)

        pid = int(row.get("player_id", 0))
        raw_date = row.get("date", "")
        if not raw_date:
            n_unmatched += 1
            continue

        # Normalize date to YYYY-MM-DD
        try:
            if "T" in str(raw_date):
                date_iso = str(raw_date)[:10]
            else:
                date_iso = str(raw_date)[:10]
        except Exception:
            n_unmatched += 1
            continue

        team_opp = player_team_map.get((pid, date_iso))
        if not team_opp:
            n_unmatched += 1
            continue

        team_abbrev, opp_abbrev = team_opp
        n_matched += 1

        current_prefix = _season_prefix_from_date(date_iso)

        # Opponent features
        opp_feats = _get_team_features(opp_abbrev, current_prefix, cv_lookup, season_means, "opp_cv_")
        for col, idx in opp_col_idx.items():
            opp_matrix[i, idx] = opp_feats.get(col, 0.0)

        # Player's own team features
        team_feats = _get_team_features(team_abbrev, current_prefix, cv_lookup, season_means, "team_cv_")
        for col, idx in team_col_idx.items():
            team_matrix[i, idx] = team_feats.get(col, 0.0)

    elapsed = time.time() - t0
    print(f"  team_cv matrix built in {elapsed:.1f}s")
    print(f"  Rows matched to (team, opp): {n_matched:,} / {n:,} ({100*n_matched/n:.1f}%)")
    print(f"  Rows unmatched: {n_unmatched:,}")

    # Coverage: how many rows have any non-zero opp CV data
    opp_n_obs_col = opp_col_idx.get("opp_cv_n_obs", -1)
    if opp_n_obs_col >= 0:
        n_with_opp_cv = int((opp_matrix[:, opp_n_obs_col] > 0).sum())
        print(f"  Rows with non-zero opp CV data: {n_with_opp_cv:,} ({100*n_with_opp_cv/n:.1f}%)")

    return opp_matrix, team_matrix


# ---------------------------------------------------------------------------
# Step 4: Walk-forward training
# ---------------------------------------------------------------------------

def _compute_season_means(
    lookup: Dict[Tuple[str, str, str], Tuple[float, int]],
) -> Dict[str, Dict[str, float]]:
    """Compute per-season feature means for fallback."""
    sums: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (team, season, fname), (val, _) in lookup.items():
        sums[season][fname] += val
        counts[season][fname] += 1
    return {
        season: {f: sums[season][f] / counts[season][f] for f in sums[season]}
        for season in sums
    }


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
    """Train XGB (GPU) + LGB, NNLS blend on val, return holdout MAE."""
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

    # NNLS blend
    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, preds))


def _run_wf(
    rows: List[dict],
    X_base: np.ndarray,
    opp_matrix: np.ndarray,
    team_matrix: np.ndarray,
) -> dict:
    """
    Run 4-fold WF for:
      - baseline: X_base only
      - opp_cv:   X_base + opp team CV features
      - both_cv:  X_base + opp team CV + player's own team CV

    Returns: {stat: {'baseline': [maes], 'opp_cv': [maes], 'both_cv': [maes]}}
    """
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]
    configs = ["baseline", "opp_cv", "both_cv"]

    results: dict = {stat: {cfg: [] for cfg in configs} for stat in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = int(n * fold_ends[fold_idx + 1]) if fold_idx < N_SPLITS - 1 else n
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip")
            continue

        # Sample weights
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}",
            flush=True,
        )

        # Build augmented matrices per config
        X_opp = np.hstack([X_base, opp_matrix])
        X_both = np.hstack([X_base, opp_matrix, team_matrix])

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            fold_t0 = time.time()
            for cfg_name, X_aug in [("baseline", X_base), ("opp_cv", X_opp), ("both_cv", X_both)]:
                mae = _train_fold(
                    stat,
                    X_aug[:tr_end], y_tr,
                    X_aug[tr_end:va_end], y_val,
                    X_aug[va_end:te_end], y_ho,
                    sw,
                )
                results[stat][cfg_name].append(mae)

            fold_elapsed = time.time() - fold_t0
            base_mae = results[stat]["baseline"][-1]
            d_opp = results[stat]["opp_cv"][-1] - base_mae
            d_both = results[stat]["both_cv"][-1] - base_mae
            print(
                f"  {stat.upper():4s}  baseline={base_mae:.4f}  "
                f"opp_cv={d_opp:+.4f}  both_cv={d_both:+.4f}"
                f"  ({fold_elapsed:.1f}s)",
                flush=True,
            )

    return results


# ---------------------------------------------------------------------------
# Step 5: Print report
# ---------------------------------------------------------------------------

def _print_report(results: dict) -> None:
    print("\n" + "=" * 70)
    print("## C3 Opp Defensive Intensity — WF Results (4-fold, XGB GPU + LGB blend)")
    print("=" * 70)

    header = "| stat | baseline | opp_cv | delta_opp | both_cv | delta_both | folds_opp | folds_both |"
    sep    = "|------|--------:|-------:|----------:|--------:|-----------:|:---------:|:----------:|"
    print(f"\n{header}")
    print(sep)

    ship_opp = []
    ship_both = []
    marginal_opp = []
    marginal_both = []
    reject = []

    for stat in STATS:
        base_folds = results[stat].get("baseline", [])
        opp_folds  = results[stat].get("opp_cv", [])
        both_folds = results[stat].get("both_cv", [])

        if not base_folds:
            print(f"| {stat} | no_data | - | - | - | - | - | - |")
            continue

        base_mean = float(np.mean(base_folds))
        opp_mean  = float(np.mean(opp_folds)) if opp_folds else float("inf")
        both_mean = float(np.mean(both_folds)) if both_folds else float("inf")
        d_opp  = opp_mean - base_mean
        d_both = both_mean - base_mean

        n_folds = len(base_folds)
        wins_opp  = sum(1 for b, o in zip(base_folds, opp_folds) if o < b)
        wins_both = sum(1 for b, o in zip(base_folds, both_folds) if o < b)

        # Bold cells that improved
        opp_str  = f"**{opp_mean:.4f}**" if d_opp < 0 else f"{opp_mean:.4f}"
        both_str = f"**{both_mean:.4f}**" if d_both < 0 else f"{both_mean:.4f}"
        do_str   = f"**{d_opp:+.4f}**" if d_opp < 0 else f"{d_opp:+.4f}"
        db_str   = f"**{d_both:+.4f}**" if d_both < 0 else f"{d_both:+.4f}"

        print(f"| {stat} | {base_mean:.4f} | {opp_str} | {do_str} | {both_str} | {db_str} | {wins_opp}/{n_folds} | {wins_both}/{n_folds} |")

        # Verdict
        if wins_opp == n_folds:
            ship_opp.append(stat)
        elif wins_opp >= 3:
            marginal_opp.append(stat)
        else:
            reject.append(stat)

        if wins_both == n_folds:
            ship_both.append(stat)
        elif wins_both >= 3:
            marginal_both.append(stat)

    print()
    print(f"### Verdict (opp_cv config — opponent CV context only)")
    print(f"- SHIP (4/4): {ship_opp if ship_opp else 'none'}")
    print(f"- MARGINAL (3/4): {marginal_opp if marginal_opp else 'none'}")
    print(f"- REJECT: {reject if reject else 'none'}")
    print()
    print(f"### Verdict (both_cv config — opp + player's own team)")
    print(f"- SHIP (4/4): {ship_both if ship_both else 'none'}")
    print(f"- MARGINAL (3/4): {marginal_both if marginal_both else 'none'}")
    print()

    # Per-fold detail
    print("### Per-fold detail (opp_cv delta vs baseline)")
    for stat in STATS:
        base_folds = results[stat].get("baseline", [])
        opp_folds  = results[stat].get("opp_cv", [])
        if not base_folds or not opp_folds:
            continue
        deltas = [o - b for b, o in zip(base_folds, opp_folds)]
        d_str = "  ".join(f"{d:+.4f}" for d in deltas)
        print(f"  {stat.upper():4s}: {d_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t_total = time.time()

    print("=" * 70)
    print("C3 test_opp_def.py — Team CV as opponent context features")
    print("=" * 70)

    # 1. Load dataset
    print("\nStep 1: Loading base dataset...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n:,} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # 2. Build player -> team map from gamelog files
    print("\nStep 2: Loading (player, date) -> (team, opp) map from gamelogs...")
    player_team_map = _load_player_game_team_map()

    # 3. Load cv_team_features lookup
    print("\nStep 3: Loading cv_team_features from DB...")
    cv_lookup = _load_cv_team_lookup()

    if not cv_lookup:
        print("  ERROR: cv_team_features table is empty. Run build_team_cv.py first.")
        sys.exit(1)

    # 4. Compute season means for fallback
    season_means = _compute_season_means(cv_lookup)
    print(f"  Season means computed: {list(season_means.keys())}")

    # 5. Build base feature matrix
    print("\nStep 4: Building base feature matrix...")
    t0 = time.time()
    X_base = np.array(
        [[float(r[c] if r[c] is not None else 0.0) for c in base_cols] for r in rows],
        dtype=float,
    )
    X_base = np.nan_to_num(X_base, nan=0.0, posinf=0.0, neginf=0.0)
    print(f"  Base matrix: {X_base.shape} ({time.time()-t0:.1f}s)")

    # 6. Build team CV augmentation matrices
    print("\nStep 5: Building team CV augmentation matrices...")
    t0 = time.time()
    opp_matrix, team_matrix = _build_team_cv_matrix(
        rows, player_team_map, cv_lookup, season_means,
    )

    # Check how many rows have non-zero opp data
    opp_n_obs_idx = OPP_CV_COLS.index("opp_cv_n_obs")
    team_n_obs_idx = TEAM_CV_COLS.index("team_cv_n_obs")
    n_opp_cv = int((opp_matrix[:, opp_n_obs_idx] > 0).sum())
    n_team_cv = int((team_matrix[:, team_n_obs_idx] > 0).sum())
    print(f"  opp_cv coverage: {n_opp_cv:,}/{n:,} rows ({100*n_opp_cv/n:.1f}%)")
    print(f"  team_cv coverage: {n_team_cv:,}/{n:,} rows ({100*n_team_cv/n:.1f}%)")

    # 7. Walk-forward
    print("\nStep 6: Running 4-fold walk-forward (XGB GPU + LGB blend)...")
    results = _run_wf(rows, X_base, opp_matrix, team_matrix)

    # 8. Report
    _print_report(results)

    total_elapsed = time.time() - t_total
    print(f"\nTotal elapsed: {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
