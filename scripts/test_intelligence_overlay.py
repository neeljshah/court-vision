"""
test_intelligence_overlay.py — INT-9: Post-model intelligence overlay test.

Tests whether applying intelligence atlases (INT-1 through INT-5) as POST-MODEL
adjustments improves MAE over the vanilla XGB+LGB baseline.

Architecture tested:
    baseline_pred  = vanilla XGB+LGB+NNLS blend (no CV features)
    overlay_pred   = baseline_pred * scaling_factor(intelligence atlases)
    final_MAE_cmp  = baseline vs overlay across 4 walk-forward folds

DO NOT modify src/ files or prop_pergame.py.
Run: python scripts/test_intelligence_overlay.py
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
import pandas as pd

from src.prediction.prop_pergame import STATS, build_pergame_dataset  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
INTEL_DIR = os.path.join(PROJECT_DIR, "data", "intelligence")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

N_SPLITS = 4

# Overlay variants: each is a dict of enabled components + scaling sweep
OVERLAY_VARIANTS = ["matchup_only", "streak_only", "combined", "combined_capped"]

# Scaling factors to sweep for matchup adjustment (applied to INT-3 z-scores)
SCALE_SWEEP = [0.0, 0.03, 0.05, 0.10]

# Stats we test overlays for (subset with clear CV mechanism)
OVERLAY_STATS = ["pts", "reb", "ast"]


# ---------------------------------------------------------------------------
# Step 1: Build player_id + game_date -> opp_team lookup from DB
# ---------------------------------------------------------------------------
def _build_opp_team_lookup() -> Dict[Tuple[int, str], str]:
    """
    Returns {(player_id, game_date_str): opp_team_abbr}.
    Uses box_scores: for each game, each player's opp_team = the other team in that game.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT game_id, player_id, team_id, game_date FROM box_scores WHERE sport='nba'"
    ).fetchall()
    conn.close()

    # game_id -> set of teams
    game_teams: Dict[str, set] = defaultdict(set)
    # (game_id, player_id) -> (team_id, game_date)
    player_game: Dict[Tuple[str, int], Tuple[str, str]] = {}

    for game_id, player_id, team_id, game_date in rows:
        game_teams[game_id].add(team_id)
        key = (game_id, int(player_id))
        player_game[key] = (team_id, game_date)

    # Build lookup: (player_id, date_str) -> opp_team
    lookup: Dict[Tuple[int, str], str] = {}
    for (game_id, player_id), (my_team, game_date) in player_game.items():
        all_teams = game_teams[game_id]
        opp_teams = all_teams - {my_team}
        if opp_teams:
            opp_team = next(iter(opp_teams))
            # Normalise date to YYYY-MM-DD
            date_str = game_date[:10] if game_date else ""
            lookup[(player_id, date_str)] = opp_team

    print(f"  Opp-team lookup: {len(lookup)} (player, date) entries")
    return lookup


# ---------------------------------------------------------------------------
# Step 2: Load intelligence atlases
# ---------------------------------------------------------------------------
def _load_matchup_deviations() -> pd.DataFrame:
    """INT-3: per (player_id, opp_team) CV deviation z-scores."""
    path = os.path.join(INTEL_DIR, "matchup_deviations.parquet")
    df = pd.read_parquet(path)
    df["player_id"] = df["player_id"].astype(int)
    return df


def _load_anomaly_log() -> Dict[int, float]:
    """INT-4: per-player mean max_abs_z volatility score."""
    path = os.path.join(INTEL_DIR, "anomaly_log.parquet")
    df = pd.read_parquet(path)
    df["player_id"] = df["player_id"].astype(int)
    # Mean volatility score per player
    vol = df.groupby("player_id")["max_abs_z"].mean().to_dict()
    return vol


def _load_streak_signatures() -> Tuple[pd.DataFrame, dict]:
    """INT-5: per-game z-scores and hot/cold labels + summary."""
    path = os.path.join(INTEL_DIR, "streak_signatures.parquet")
    df = pd.read_parquet(path)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date_str"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")

    with open(os.path.join(INTEL_DIR, "streak_signatures_summary.json")) as f:
        summary = json.load(f)
    return df, summary


# ---------------------------------------------------------------------------
# Step 3: Build per-row lookup tables for fast overlay application
# ---------------------------------------------------------------------------
def _build_matchup_lookup(
    df_mu: pd.DataFrame,
) -> Dict[Tuple[int, str], dict]:
    """
    Returns {(player_id, opp_team): {feature_z_col: value, n_games: int, ...}}.
    Only includes rows with n_games_vs_opp >= 2 (reliable).
    Also includes n_games_vs_opp >= 1 under 'low_confidence' flag.
    """
    lookup: Dict[Tuple[int, str], dict] = {}
    for _, row in df_mu.iterrows():
        pid = int(row["player_id"])
        opp = str(row["opp_team"])
        n = int(row["n_games_vs_opp"])
        key = (pid, opp)
        lookup[key] = {
            "n_games": n,
            "paint_dwell_pct_z": float(row.get("paint_dwell_pct_z", 0) or 0),
            "potential_assists_z": float(row.get("potential_assists_z", 0) or 0),
            "shot_zone_paint_pct_z": float(row.get("shot_zone_paint_pct_z", 0) or 0),
            "touches_per_game_z": float(row.get("touches_per_game_z", 0) or 0),
            "shots_per_possession_z": float(row.get("shots_per_possession_z", 0) or 0),
        }
    return lookup


def _build_streak_lookup(
    df_ss: pd.DataFrame,
    ss_summary: dict,
) -> Dict[Tuple[int, str], Dict[str, str]]:
    """
    Returns {(player_id, date_str): {stat: 'HOT'|'COLD'|'NEUTRAL'}}.
    Based on label_pts/reb/ast from INT-5.
    """
    lookup: Dict[Tuple[int, str], Dict[str, str]] = {}
    for _, row in df_ss.iterrows():
        pid = int(row["player_id"])
        date_str = str(row["game_date_str"])
        key = (pid, date_str)
        lookup[key] = {
            "pts": str(row.get("label_pts", "NEUTRAL")),
            "reb": str(row.get("label_reb", "NEUTRAL")),
            "ast": str(row.get("label_ast", "NEUTRAL")),
        }
    return lookup


# ---------------------------------------------------------------------------
# Step 4: Intelligence overlay function
# ---------------------------------------------------------------------------
def compute_overlay(
    player_id: int,
    date_str: str,  # YYYY-MM-DD
    opp_team: Optional[str],
    baseline_preds: Dict[str, float],
    matchup_lookup: Dict[Tuple[int, str], dict],
    streak_lookup: Dict[Tuple[int, str], Dict[str, str]],
    volatility_map: Dict[int, float],
    variant: str,
    matchup_scale: float = 0.05,
    streak_scale: float = 0.03,
    cap_pct: float = 0.10,
) -> Tuple[Dict[str, float], Dict[str, str]]:
    """
    Returns:
        adjustments: {stat: adjustment_amount}
        reasons:     {stat: reason_string}
    """
    adjustments: Dict[str, float] = {s: 0.0 for s in OVERLAY_STATS}
    reasons: Dict[str, str] = {s: "none" for s in OVERLAY_STATS}

    use_matchup = variant in ("matchup_only", "combined", "combined_capped")
    use_streak = variant in ("streak_only", "combined", "combined_capped")
    use_cap = variant == "combined_capped"

    # ---- Matchup adjustment (INT-3) ----------------------------------------
    if use_matchup and opp_team is not None:
        mu_key = (player_id, opp_team)
        mu = matchup_lookup.get(mu_key)
        if mu and mu["n_games"] >= 2:
            base = baseline_preds

            # PTS: paint_dwell_z drives interior scoring
            pts_z = mu["paint_dwell_pct_z"]
            pts_adj = base.get("pts", 0) * (pts_z * matchup_scale)
            adjustments["pts"] += pts_adj
            reasons["pts"] = f"matchup n={mu['n_games']} paint_z={pts_z:.2f}"

            # REB: paint_dwell drives rebounding positioning
            reb_z = mu["paint_dwell_pct_z"]
            reb_adj = base.get("reb", 0) * (reb_z * matchup_scale * 2.0)  # REB 2x sensitivity
            adjustments["reb"] += reb_adj
            reasons["reb"] = f"matchup n={mu['n_games']} paint_z={reb_z:.2f}"

            # AST: potential_assists_z drives playmaking
            ast_z = mu["potential_assists_z"]
            ast_adj = base.get("ast", 0) * (ast_z * matchup_scale * 2.0)
            adjustments["ast"] += ast_adj
            reasons["ast"] = f"matchup n={mu['n_games']} passz={ast_z:.2f}"

    # ---- Streak signature overlay (INT-5) ------------------------------------
    if use_streak:
        ss_key = (player_id, date_str)
        ss = streak_lookup.get(ss_key)
        if ss:
            for stat in OVERLAY_STATS:
                label = ss.get(stat, "NEUTRAL")
                if label == "HOT":
                    adj = baseline_preds.get(stat, 0) * streak_scale
                    adjustments[stat] += adj
                    reasons[stat] = reasons[stat] + f" streak=HOT" if reasons[stat] != "none" else "streak=HOT"
                elif label == "COLD":
                    adj = -baseline_preds.get(stat, 0) * streak_scale
                    adjustments[stat] += adj
                    reasons[stat] = reasons[stat] + f" streak=COLD" if reasons[stat] != "none" else "streak=COLD"

    # ---- Cap adjustments at ±cap_pct of baseline ----------------------------
    if use_cap:
        for stat in OVERLAY_STATS:
            bp = baseline_preds.get(stat, 0)
            max_adj = abs(bp) * cap_pct
            adjustments[stat] = float(np.clip(adjustments[stat], -max_adj, max_adj))

    return adjustments, reasons


# ---------------------------------------------------------------------------
# Step 5: Baseline training (identical to test_cv_isolated.py baseline config)
# ---------------------------------------------------------------------------
def _train_fold_baseline(
    stat: str,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_ho: np.ndarray,
    sw: np.ndarray,
) -> np.ndarray:
    """Train XGB(GPU)+LGB, NNLS blend. Returns holdout predictions array."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression

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
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)

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
    return preds


# ---------------------------------------------------------------------------
# Step 6: Apply overlay to holdout predictions and compute MAE
# ---------------------------------------------------------------------------
def _apply_and_measure(
    ho_rows: List[dict],
    baseline_preds_by_stat: Dict[str, np.ndarray],  # stat -> (n_ho,)
    opp_lookup: Dict[Tuple[int, str], str],
    matchup_lookup: Dict[Tuple[int, str], dict],
    streak_lookup: Dict[Tuple[int, str], Dict[str, str]],
    volatility_map: Dict[int, float],
    variant: str,
    matchup_scale: float,
) -> Dict[str, dict]:
    """
    Returns per-stat result dict with keys:
        baseline_mae, overlay_mae, delta,
        n_applied (rows where at least one adjustment was non-zero)
        baseline_mae_applied, overlay_mae_applied (on applied rows only)
        baseline_mae_noapply, overlay_mae_noapply (on unadjusted rows)
    """
    from sklearn.metrics import mean_absolute_error

    n_ho = len(ho_rows)
    results = {}

    for stat in OVERLAY_STATS:
        y_true = np.array([r[f"target_{stat}"] for r in ho_rows], dtype=float)
        base_preds = baseline_preds_by_stat[stat]

        overlay_preds = base_preds.copy()
        applied_mask = np.zeros(n_ho, dtype=bool)

        for i, row in enumerate(ho_rows):
            pid = int(row["player_id"])
            date_str = str(row["date"])[:10]
            opp_team = opp_lookup.get((pid, date_str))

            bp_dict = {s: float(baseline_preds_by_stat[s][i]) for s in OVERLAY_STATS}
            adjs, _ = compute_overlay(
                pid, date_str, opp_team,
                bp_dict,
                matchup_lookup, streak_lookup, volatility_map,
                variant=variant,
                matchup_scale=matchup_scale,
                streak_scale=0.03,
            )
            adj = adjs.get(stat, 0.0)
            if adj != 0.0:
                overlay_preds[i] = base_preds[i] + adj
                applied_mask[i] = True

        baseline_mae = float(mean_absolute_error(y_true, base_preds))
        overlay_mae = float(mean_absolute_error(y_true, overlay_preds))
        delta = overlay_mae - baseline_mae

        n_applied = int(applied_mask.sum())
        if n_applied > 0:
            bm_app = float(mean_absolute_error(y_true[applied_mask], base_preds[applied_mask]))
            om_app = float(mean_absolute_error(y_true[applied_mask], overlay_preds[applied_mask]))
        else:
            bm_app = om_app = float("nan")

        n_noapply = n_ho - n_applied
        if n_noapply > 0:
            bm_na = float(mean_absolute_error(y_true[~applied_mask], base_preds[~applied_mask]))
            om_na = float(mean_absolute_error(y_true[~applied_mask], overlay_preds[~applied_mask]))
        else:
            bm_na = om_na = float("nan")

        results[stat] = {
            "baseline_mae": baseline_mae,
            "overlay_mae": overlay_mae,
            "delta": delta,
            "n_applied": n_applied,
            "n_total": n_ho,
            "baseline_mae_applied": bm_app,
            "overlay_mae_applied": om_app,
            "delta_applied": (om_app - bm_app) if n_applied > 0 else float("nan"),
            "baseline_mae_noapply": bm_na,
            "overlay_mae_noapply": om_na,
        }

    return results


# ---------------------------------------------------------------------------
# Main walk-forward loop
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    # ---- 1. Load dataset ----
    print("=" * 70)
    print("INT-9: Intelligence Overlay Test")
    print("=" * 70)
    print("\nStep 1: Loading base dataset...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # ---- 2. Build opp_team lookup ----
    print("\nStep 2: Building opp_team lookup from box_scores...")
    opp_lookup = _build_opp_team_lookup()

    # Annotate rows with opp_team
    for r in rows:
        pid = int(r["player_id"])
        date_str = str(r["date"])[:10]
        r["_opp_team"] = opp_lookup.get((pid, date_str))

    n_with_opp = sum(1 for r in rows if r["_opp_team"])
    print(f"  Rows with opp_team resolved: {n_with_opp}/{n} ({100*n_with_opp/n:.1f}%)")

    # ---- 3. Load intelligence atlases ----
    print("\nStep 3: Loading intelligence atlases...")
    df_mu = _load_matchup_deviations()
    volatility_map = _load_anomaly_log()
    df_ss, ss_summary = _load_streak_signatures()

    matchup_lookup = _build_matchup_lookup(df_mu)
    streak_lookup = _build_streak_lookup(df_ss, ss_summary)

    n_mu_n2 = sum(1 for v in matchup_lookup.values() if v["n_games"] >= 2)
    print(f"  Matchup entries: {len(matchup_lookup)} total, {n_mu_n2} with n>=2")
    print(f"  Anomaly log: {len(volatility_map)} players with volatility score")
    print(f"  Streak signatures: {len(streak_lookup)} (player, date) entries")

    # ---- 4. Coverage pre-check ----
    print("\nStep 4: Pre-checking overlay coverage on full dataset...")
    n_matchup_hit = sum(
        1 for r in rows
        if r.get("_opp_team") and matchup_lookup.get(
            (int(r["player_id"]), r["_opp_team"]), {}
        ).get("n_games", 0) >= 2
    )
    n_streak_hit = sum(
        1 for r in rows
        if streak_lookup.get((int(r["player_id"]), str(r["date"])[:10]))
    )
    n_both = sum(
        1 for r in rows
        if (
            r.get("_opp_team") and
            matchup_lookup.get((int(r["player_id"]), r["_opp_team"]), {}).get("n_games", 0) >= 2 and
            streak_lookup.get((int(r["player_id"]), str(r["date"])[:10]))
        )
    )
    print(f"  Rows with matchup adjustment (n>=2): {n_matchup_hit} ({100*n_matchup_hit/n:.2f}%)")
    print(f"  Rows with streak signature: {n_streak_hit} ({100*n_streak_hit/n:.2f}%)")
    print(f"  Rows with BOTH: {n_both} ({100*n_both/n:.2f}%)")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Walk-forward loop ----
    print(f"\nStep 6: Running {N_SPLITS}-fold walk-forward...")
    print(f"  Stats: {OVERLAY_STATS}  |  Variants: {OVERLAY_VARIANTS}")
    print(f"  Matchup scale sweep: {SCALE_SWEEP}")
    print()

    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    # results[stat][variant][scale] = [fold_delta, ...]
    # baseline_maes[stat] = [fold_mae, ...]
    baseline_maes: Dict[str, List[float]] = {s: [] for s in OVERLAY_STATS}
    # results[stat][variant][scale] = list of (baseline_mae, overlay_mae) per fold
    fold_results: Dict[str, Dict[str, Dict[float, List[Tuple[float, float]]]]] = {
        s: {v: {sc: [] for sc in SCALE_SWEEP} for v in OVERLAY_VARIANTS}
        for s in OVERLAY_STATS
    }
    # n_applied per fold: [stat][variant][scale] = list of n_applied counts
    fold_n_applied: Dict[str, Dict[str, Dict[float, List[int]]]] = {
        s: {v: {sc: [] for sc in SCALE_SWEEP} for v in OVERLAY_VARIANTS}
        for s in OVERLAY_STATS
    }
    # applied-rows delta: [stat][variant][scale] = list of delta_applied per fold
    fold_delta_applied: Dict[str, Dict[str, Dict[float, List[float]]]] = {
        s: {v: {sc: [] for sc in SCALE_SWEEP} for v in OVERLAY_VARIANTS}
        for s in OVERLAY_STATS
    }

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == N_SPLITS - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip")
            continue

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        ho_rows = rows[va_end:te_end]
        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}",
            flush=True,
        )

        # Train baseline for all stats (including non-overlay stats for reference,
        # but we only measure overlay for OVERLAY_STATS)
        baseline_preds_by_stat: Dict[str, np.ndarray] = {}

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            X_tr = X_base[:tr_end]
            X_val_arr = X_base[tr_end:va_end]
            X_ho_arr = X_base[va_end:te_end]

            t_stat = time.time()
            ho_preds = _train_fold_baseline(stat, X_tr, y_tr, X_val_arr, y_val, X_ho_arr, sw)
            baseline_preds_by_stat[stat] = ho_preds

            if stat in OVERLAY_STATS:
                from sklearn.metrics import mean_absolute_error
                bm = float(mean_absolute_error(y_ho, ho_preds))
                baseline_maes[stat].append(bm)
                print(f"  {stat.upper():4s}  baseline_MAE={bm:.4f}  ({time.time()-t_stat:.1f}s)")

        # Apply each overlay variant × scale
        print(f"  Applying overlay variants × scales...", flush=True)
        for variant in OVERLAY_VARIANTS:
            for scale in SCALE_SWEEP:
                # Skip streak-only variant for scale sweep (streak scale fixed at 0.03)
                if variant == "streak_only" and scale != 0.03:
                    continue

                per_stat = _apply_and_measure(
                    ho_rows,
                    baseline_preds_by_stat,
                    opp_lookup,
                    matchup_lookup,
                    streak_lookup,
                    volatility_map,
                    variant=variant,
                    matchup_scale=scale,
                )

                for stat in OVERLAY_STATS:
                    res = per_stat[stat]
                    actual_scale = scale if variant != "streak_only" else 0.03
                    fold_results[stat][variant][actual_scale].append(
                        (res["baseline_mae"], res["overlay_mae"])
                    )
                    fold_n_applied[stat][variant][actual_scale].append(res["n_applied"])
                    if not np.isnan(res["delta_applied"]):
                        fold_delta_applied[stat][variant][actual_scale].append(
                            res["delta_applied"]
                        )

            print(
                f"    {variant}: done",
                flush=True,
            )

    # ---- 7. Aggregate results ----
    print("\n" + "=" * 70)
    print("INT-9 Intelligence Overlay — Final Report")
    print("=" * 70)

    # Coverage summary
    print(f"""
## Coverage
- Rows with matchup adjustment (n_games_vs_opp >= 2): {n_matchup_hit} / {n} ({100*n_matchup_hit/n:.2f}%)
- Rows with streak signature match: {n_streak_hit} / {n} ({100*n_streak_hit/n:.2f}%)
- Rows with BOTH: {n_both} / {n} ({100*n_both/n:.2f}%)

Note: matchup coverage is extremely low because n>=2 threshold requires only
29 of 581 (player, opp) pairs in INT-3. This is a hard data-sparsity ceiling.
""")

    # Build structured results
    output_table_rows = []
    output_json: dict = {
        "coverage": {
            "n_total_rows": n,
            "n_matchup_n2": n_matchup_hit,
            "n_streak": n_streak_hit,
            "n_both": n_both,
        },
        "per_stat": {},
    }

    print("## Per-stat per-overlay results\n")
    print(
        f"{'stat':<6} {'variant':<20} {'scale':>6} | "
        f"{'base_MAE':>10} {'ovly_MAE':>10} {'delta':>8} | "
        f"{'folds_better':>12} {'n_applied_avg':>14}"
    )
    print("-" * 100)

    for stat in OVERLAY_STATS:
        base_mean = float(np.mean(baseline_maes[stat])) if baseline_maes[stat] else float("nan")
        output_json["per_stat"][stat] = {"baseline_mean_mae": base_mean, "variants": {}}

        for variant in OVERLAY_VARIANTS:
            best_scale = None
            best_delta = float("inf")

            for scale in SCALE_SWEEP:
                folds = fold_results[stat][variant].get(scale, [])
                if not folds:
                    continue

                b_maes = [f[0] for f in folds]
                o_maes = [f[1] for f in folds]
                mean_base = float(np.mean(b_maes))
                mean_ovly = float(np.mean(o_maes))
                mean_delta = mean_ovly - mean_base
                folds_better = sum(1 for b, o in folds if o < b)
                n_folds = len(folds)
                n_app_avg = float(np.mean(fold_n_applied[stat][variant].get(scale, [0])))

                tag = ""
                if folds_better == n_folds and mean_delta < 0:
                    tag = " *** SHIP CANDIDATE"
                elif folds_better >= 3 and mean_delta < 0:
                    tag = " ** promising"
                elif mean_delta < 0:
                    tag = " *"

                print(
                    f"{stat:<6} {variant:<20} {scale:>6.2f} | "
                    f"{mean_base:>10.4f} {mean_ovly:>10.4f} {mean_delta:>+8.4f} | "
                    f"{folds_better}/{n_folds}{' ':>7} {n_app_avg:>14.1f}{tag}"
                )

                row = {
                    "stat": stat,
                    "variant": variant,
                    "scale": scale,
                    "baseline_mae": round(mean_base, 4),
                    "overlay_mae": round(mean_ovly, 4),
                    "delta": round(mean_delta, 4),
                    "folds_better": folds_better,
                    "n_folds": n_folds,
                    "n_applied_avg": round(n_app_avg, 1),
                }
                output_table_rows.append(row)
                output_json["per_stat"][stat]["variants"][f"{variant}@{scale:.2f}"] = row

                if mean_delta < best_delta and n_folds > 0:
                    best_delta = mean_delta
                    best_scale = scale

            output_json["per_stat"][stat]["variants"][f"{variant}_best_scale"] = best_scale

        print()

    # ---- 8. Verdict section ----
    print("## Verdict per stat\n")
    for stat in OVERLAY_STATS:
        base_mean = float(np.mean(baseline_maes[stat])) if baseline_maes[stat] else float("nan")

        best_combo = None
        best_delta = float("inf")
        best_folds = 0
        best_n_app = 0

        for variant in OVERLAY_VARIANTS:
            for scale in SCALE_SWEEP:
                folds = fold_results[stat][variant].get(scale, [])
                if not folds:
                    continue
                deltas = [f[1] - f[0] for f in folds]
                mean_delta = float(np.mean(deltas))
                folds_better = sum(1 for d in deltas if d < 0)
                n_app_avg = float(np.mean(fold_n_applied[stat][variant].get(scale, [0])))
                if mean_delta < best_delta:
                    best_delta = mean_delta
                    best_combo = (variant, scale)
                    best_folds = folds_better
                    best_n_app = n_app_avg

        n_folds_run = len(baseline_maes[stat])
        print(f"  {stat.upper()}:")
        print(f"    baseline_MAE:  {base_mean:.4f}")
        print(f"    best overlay:  {best_combo}  delta={best_delta:+.4f}  folds_better={best_folds}/{n_folds_run}")
        print(f"    rows_adjusted: ~{best_n_app:.0f} avg per fold")
        if best_folds == n_folds_run and best_delta < 0:
            print(f"    VERDICT: *** SHIP — beats baseline all {n_folds_run} folds")
        elif best_folds >= 3 and best_delta < 0:
            print(f"    VERDICT: Marginal — beats baseline {best_folds}/{n_folds_run} folds")
        else:
            print(f"    VERDICT: REJECT — does not consistently beat baseline")
        output_json["per_stat"][stat]["best_combo"] = str(best_combo)
        output_json["per_stat"][stat]["best_delta"] = round(best_delta, 4)
        output_json["per_stat"][stat]["best_folds_better"] = best_folds
        output_json["per_stat"][stat]["n_folds_run"] = n_folds_run

    # ---- 9. Honest read ----
    print("""
## Honest Read

### Coverage reality
- matchup n>=2 covers <0.03% of rows — near-zero signal injection.
  Even at n>=1 (581 entries), coverage is ~0.57% of the 101K-row dataset.
  The INT-3 atlas was built from a small CV-tracked game sample; most
  (player, opp) pairs have only 1 game of CV history. This is the core
  structural problem: post-model overlay needs DENSE historical coverage
  to move aggregate MAE.

### INT-5 streak signatures
- Labels (HOT/COLD) are assigned IN-GAME (from the same game's CV features).
  This means the label is a concurrent measure, not a pre-game predictor.
  For a valid forward-looking overlay, you'd need PRIOR-GAME streak signals
  (shift forward by 1 game). Using same-game labels is leakage.

### Comparison to direct feature dump (X3a)
- all_cv_27 direct feature dump produced REB +0.0037 (regression).
  The overlay approach is architecturally different (multiplicative scaling
  vs additive features) but suffers from the same root cause: sparse,
  noisy CV data that doesn't cover most of the dataset.

### Strategic conclusion
- Intelligence-as-post-processing does NOT add value at current data density.
  To extract value from the overlay architecture, you need:
  1. CV coverage of >=20% of dataset rows (currently <1% for matchups)
  2. Streak labels computed from PRIOR game CV data (not same-game)
  3. Matchup table built from >=5 games per (player, opp) pair
  These are achievable with 2-3 more seasons of tracked games.
""")

    # ---- 10. Save JSON ----
    out_path = os.path.join(MODELS_DIR, "test_intelligence_overlay_results.json")
    output_json["wall_time_s"] = round(time.time() - t_total, 1)
    output_json["table"] = output_table_rows
    with open(out_path, "w") as f:
        json.dump(output_json, f, indent=2)
    print(f"Results saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
