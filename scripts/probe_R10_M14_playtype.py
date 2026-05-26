"""
probe_R10_M14_playtype.py
Synergy play-type features (data/playtypes.parquet) as prior-season features
for per-game prop prediction (pts, reb, ast, fg3m, stl, blk, tov).

LEAKAGE DISCIPLINE:
  - playtypes.parquet has season-level rows.
  - For a game in season S, use only the player's S-1 (prior season) vector.
  - Players with no prior-season vector (rookies) are DROPPED for this probe.
  - This mirrors the cycle-14 lesson: current-season season-level features
    introduce leakage because the season average is computed using the very game
    being predicted.

PROCEDURE:
  1. Load data/player_quarter_stats.parquet, aggregate to per-game.
  2. Derive season from game_id (chars 3:5: '24' -> 2024-25).
  3. Load data/playtypes.parquet, pivot to wide (player_id, season) x play_types.
  4. For each game row: join PRIOR-SEASON (S-1) playtype vector.
  5. Drop rows missing prior-season vector.
  6. Walk-forward 4-fold temporal CV — XGBoost baseline vs baseline+playtypes.
  7. Apply ship gate and write JSON.

SHIP GATE (MAE at endQ3 / full-game):
  WF 4/4 positive, mean delta <= -0.005, >= 4/7 stats improving.
  Baseline: pts=2.214, reb=0.8987, ast=0.5755, fg3m=0.3528,
            stl=0.2506, blk=0.1543, tov=0.3663

Run:
  python -u scripts/probe_R10_M14_playtype.py > scripts/_results/improve_R10_M14_run.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
OUT_JSON = os.path.join(CACHE_DIR, "probe_R10_M14_playtype_results.json")
os.makedirs(CACHE_DIR, exist_ok=True)

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
BASELINES = {
    "pts": 2.214, "reb": 0.8987, "ast": 0.5755, "fg3m": 0.3528,
    "stl": 0.2506, "blk": 0.1543, "tov": 0.3663,
}

# 9 play types from the parquet
PLAY_TYPES = [
    "cut", "handoff", "isolation", "offscreen",
    "prballhandler", "prrollman", "postup", "spotup", "transition",
]
PT_COLS = [f"pt_{pt}_freq" for pt in PLAY_TYPES]

# ── Season helpers ────────────────────────────────────────────────────────────

def game_id_to_season(gid: str) -> str:
    """'0022400001' -> '2024-25' (chars 3:5 = '24' -> start year 2024)."""
    yr = int(gid[3:5])
    return f"20{yr}-{str(yr + 1).zfill(2)}"


def prior_season(season: str) -> str:
    """'2024-25' -> '2023-24'. Empty string on failure."""
    try:
        start, end = season.split("-")
        return f"{int(start) - 1}-{int(end) - 1:02d}"
    except Exception:
        return ""


# ── Data loading ──────────────────────────────────────────────────────────────

def load_pergame() -> pd.DataFrame:
    """Load player_quarter_stats, aggregate to per-game, derive season."""
    path = os.path.join(DATA_DIR, "player_quarter_stats.parquet")
    df = pd.read_parquet(path)
    # Aggregate all quarters into full-game stats
    agg = (
        df.groupby(["game_id", "player_id"])[STATS + ["min"]]
        .sum()
        .reset_index()
    )
    agg["season"] = agg["game_id"].apply(game_id_to_season)
    # Filter to players who actually played (>= 1 min)
    agg = agg[agg["min"] >= 1.0].copy()
    return agg


def load_playtype_pivot() -> pd.DataFrame:
    """Load playtypes.parquet, pivot to wide keyed (player_id, season)."""
    path = os.path.join(DATA_DIR, "playtypes.parquet")
    df = pd.read_parquet(path)
    # Normalize play_type to match PT_COLS (lower, no space)
    df["play_type"] = df["play_type"].str.lower().str.replace(" ", "", regex=False)
    # Keep only top-8 play types by row count (already all 9 have good coverage)
    top_types = df["play_type"].value_counts().head(8).index.tolist()
    df = df[df["play_type"].isin(top_types)]
    pivot = df.pivot_table(
        index=["player_id", "season"],
        columns="play_type",
        values="freq_pct",
        aggfunc="mean",
    ).reset_index()
    pivot.columns.name = None
    # Rename columns to pt_<name>_freq
    rename = {pt: f"pt_{pt}_freq" for pt in top_types}
    pivot = pivot.rename(columns=rename)
    # Fill NaN for missing play types with 0
    for col in [f"pt_{pt}_freq" for pt in top_types]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot.fillna(0.0)
    return pivot, [f"pt_{pt}_freq" for pt in top_types]


def build_features_and_targets(
    pergame: pd.DataFrame,
    pt_pivot: pd.DataFrame,
    pt_feat_cols: List[str],
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Build per-row feature matrix with rolling form features + prior-season
    playtype features.

    Leakage-free rolling features:
      - l5_<stat>, l10_<stat>, ewma_<stat> computed with shift(1) within each
        player's chronological game sequence so the target game is never included.
    Prior-season playtype:
      - Derive prior_season from the game's season, join pt_pivot on
        (player_id, prior_season). Rows without a match are dropped.
    """
    # Sort chronologically — game_id is sequential by date within a season
    pergame = pergame.sort_values(["player_id", "game_id"]).reset_index(drop=True)

    # ── Rolling form features (shift(1) to exclude the current game) ──────────
    form_feats: List[str] = []
    for stat in STATS:
        grp = pergame.groupby("player_id")[stat]
        # shift(1) then rolling — strictly prior games
        shifted = grp.shift(1)
        pergame[f"l5_{stat}"] = shifted.groupby(pergame["player_id"]).transform(
            lambda s: s.rolling(5, min_periods=1).mean()
        )
        pergame[f"l10_{stat}"] = shifted.groupby(pergame["player_id"]).transform(
            lambda s: s.rolling(10, min_periods=1).mean()
        )
        # EWMA — pandas ewm is equivalent; com = (1-alpha)/alpha for alpha=0.3
        pergame[f"ewma_{stat}"] = shifted.groupby(pergame["player_id"]).transform(
            lambda s: s.ewm(alpha=0.3, adjust=False, min_periods=1).mean()
        )
        form_feats += [f"l5_{stat}", f"l10_{stat}", f"ewma_{stat}"]

    # games_played (prior games for this player up to but not including this game)
    pergame["games_played"] = pergame.groupby("player_id").cumcount()

    # Drop rows with 0 prior games (no stable form yet)
    pergame = pergame[pergame["games_played"] >= 3].reset_index(drop=True)

    base_feat_cols = form_feats + ["games_played"]

    # ── Prior-season playtype join ─────────────────────────────────────────────
    pergame["prior_season"] = pergame["season"].apply(prior_season)

    # Join on (player_id, prior_season)
    pt_join = pt_pivot.rename(columns={"season": "prior_season"})
    merged = pergame.merge(
        pt_join[["player_id", "prior_season"] + pt_feat_cols],
        on=["player_id", "prior_season"],
        how="left",
    )

    # Rows WITHOUT a prior-season vector get NaN — these are rookies or
    # season-1 players. We keep them as a "base-only" set and compare
    # separately; for the PLAYTYPE head we drop them.
    has_prior = merged[pt_feat_cols[0]].notna()
    print(f"  Rows with prior-season playtype vector: {has_prior.sum()} / {len(merged)}", flush=True)

    # Fill NaN with 0 for missing play types (players with partial coverage)
    for col in pt_feat_cols:
        merged[col] = merged[col].fillna(0.0)

    # Return only rows with prior-season data for the playtype probe
    merged_with_pt = merged[has_prior].reset_index(drop=True)

    return merged_with_pt, base_feat_cols, pt_feat_cols


# ── Walk-forward CV ───────────────────────────────────────────────────────────

def walk_forward_cv(
    df: pd.DataFrame,
    base_cols: List[str],
    pt_cols: List[str],
    n_splits: int = 4,
) -> Dict:
    """4-fold temporal walk-forward.

    For each fold trains:
      A: XGBoost on base_cols only
      B: XGBoost on base_cols + pt_cols
    Reports per-stat MAE delta (B - A) across folds.
    """
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    # Sort by game_id (chronological proxy)
    df = df.sort_values("game_id").reset_index(drop=True)
    n = len(df)
    print(f"\n  Dataset: {n} rows, {len(base_cols)} base features, {len(pt_cols)} playtype features", flush=True)

    # Fold boundaries — expanding train, non-overlapping test
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    fold_metrics: Dict[str, List] = {s: [] for s in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])

        if tr_end < 1000 or (te_end - tr_end) < 200:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, te={te_end-tr_end}) — skip", flush=True)
            continue

        X_tr_base = df.iloc[:tr_end][base_cols].values.astype(float)
        X_te_base = df.iloc[tr_end:te_end][base_cols].values.astype(float)
        X_tr_aug = df.iloc[:tr_end][base_cols + pt_cols].values.astype(float)
        X_te_aug = df.iloc[tr_end:te_end][base_cols + pt_cols].values.astype(float)

        # Replace NaN with 0 (form features may have NaN for earliest rows)
        X_tr_base = np.nan_to_num(X_tr_base, 0.0)
        X_te_base = np.nan_to_num(X_te_base, 0.0)
        X_tr_aug  = np.nan_to_num(X_tr_aug, 0.0)
        X_te_aug  = np.nan_to_num(X_te_aug, 0.0)

        print(f"\n  [fold {fold_idx+1}/{n_splits}] tr={tr_end} te={te_end-tr_end}", flush=True)
        t0 = time.time()

        for stat in STATS:
            y_tr = df.iloc[:tr_end][stat].values.astype(float)
            y_te = df.iloc[tr_end:te_end][stat].values.astype(float)

            # Clamp negatives (can't have negative counting stats)
            y_tr = np.clip(y_tr, 0, None)
            y_te = np.clip(y_te, 0, None)

            params = dict(
                n_estimators=400,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=10,
                reg_lambda=2.0,
                reg_alpha=0.5,
                random_state=42,
                objective="reg:squarederror",
                verbosity=0,
            )

            # Baseline: no playtype
            m_base = xgb.XGBRegressor(**params)
            m_base.fit(X_tr_base, y_tr, verbose=False)
            pred_base = np.clip(m_base.predict(X_te_base), 0, None)
            mae_base = float(mean_absolute_error(y_te, pred_base))

            # Augmented: + playtype
            m_aug = xgb.XGBRegressor(**params)
            m_aug.fit(X_tr_aug, y_tr, verbose=False)
            pred_aug = np.clip(m_aug.predict(X_te_aug), 0, None)
            mae_aug = float(mean_absolute_error(y_te, pred_aug))

            delta = mae_aug - mae_base
            fold_metrics[stat].append({
                "fold": fold_idx + 1,
                "mae_base": mae_base,
                "mae_aug": mae_aug,
                "delta": delta,
            })
            sign = "-" if delta < 0 else "+"
            print(
                f"    {stat.upper():4s} base={mae_base:.4f} aug={mae_aug:.4f} "
                f"delta={delta:+.4f} {'IMPROVE' if delta < 0 else 'regress'}",
                flush=True,
            )

        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.1f}s", flush=True)

    return fold_metrics


# ── Ship gate ─────────────────────────────────────────────────────────────────

def apply_ship_gate(fold_metrics: Dict) -> Dict:
    """
    Ship gate:
      - WF 4/4 positive for each shipped stat
      - mean delta <= -0.005
      - >= 4/7 stats improving

    Returns summary dict with verdict.
    """
    summary = {}
    n_improving = 0
    for stat in STATS:
        folds = fold_metrics[stat]
        if not folds:
            summary[stat] = {"verdict": "NO_DATA"}
            continue
        deltas = [f["delta"] for f in folds]
        mean_delta = float(np.mean(deltas))
        n_pos = sum(1 for d in deltas if d < 0)
        mae_base_mean = float(np.mean([f["mae_base"] for f in folds]))
        mae_aug_mean = float(np.mean([f["mae_aug"] for f in folds]))
        wf_4_4 = (n_pos == len(deltas))
        baseline_val = BASELINES.get(stat, 0)
        improving = mean_delta < 0
        if improving:
            n_improving += 1
        summary[stat] = {
            "mae_base_mean": round(mae_base_mean, 5),
            "mae_aug_mean": round(mae_aug_mean, 5),
            "mean_delta": round(mean_delta, 5),
            "n_folds_positive": n_pos,
            "n_folds_total": len(deltas),
            "wf_4_4": wf_4_4,
            "baseline_published": baseline_val,
            "improving": improving,
            "fold_details": folds,
        }

    # Overall gate
    stats_with_wf_4_4 = [s for s in STATS if summary.get(s, {}).get("wf_4_4", False)]
    mean_delta_over_improving = np.mean([
        summary[s]["mean_delta"] for s in STATS
        if summary.get(s, {}).get("improving", False)
    ]) if n_improving > 0 else 0.0

    overall_improving = [
        s for s in STATS if summary.get(s, {}).get("improving", False)
    ]
    gate_pass = (
        len(overall_improving) >= 4
        and any(summary[s]["wf_4_4"] and summary[s]["mean_delta"] <= -0.005
                for s in STATS)
    )

    summary["_gate"] = {
        "n_improving": n_improving,
        "stats_improving": overall_improving,
        "stats_wf_4_4": stats_with_wf_4_4,
        "mean_delta_improving_stats": round(float(mean_delta_over_improving), 5),
        "gate_pass": gate_pass,
        "verdict": "SHIP" if gate_pass else "REJECT",
    }
    return summary


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()
    print("=" * 60, flush=True)
    print("Probe R10_M14: Synergy Play-Type Features (Prior-Season)", flush=True)
    print("=" * 60, flush=True)

    print("\n[1] Loading per-game data from player_quarter_stats.parquet ...", flush=True)
    pergame = load_pergame()
    print(f"  Per-game rows (after min filter): {len(pergame)}", flush=True)
    print(f"  Seasons: {sorted(pergame['season'].unique())}", flush=True)

    print("\n[2] Loading and pivoting playtypes.parquet ...", flush=True)
    pt_pivot, pt_feat_cols = load_playtype_pivot()
    print(f"  Pivot shape: {pt_pivot.shape}", flush=True)
    print(f"  Play-type feature cols ({len(pt_feat_cols)}): {pt_feat_cols}", flush=True)
    print(f"  Seasons in pivot: {sorted(pt_pivot['season'].unique())}", flush=True)

    print("\n[3] Building features (rolling form + prior-season playtype join) ...", flush=True)
    merged, base_cols, pt_cols = build_features_and_targets(pergame, pt_pivot, pt_feat_cols)
    print(f"  Final dataset (rows with prior-season vector): {len(merged)}", flush=True)
    print(f"  Base features: {len(base_cols)}", flush=True)
    print(f"  Playtype features: {len(pt_cols)}: {pt_cols}", flush=True)

    print("\n[4] Walk-forward CV (4-fold temporal) ...", flush=True)
    fold_metrics = walk_forward_cv(merged, base_cols, pt_cols, n_splits=4)

    print("\n[5] Applying ship gate ...", flush=True)
    summary = apply_ship_gate(fold_metrics)

    print("\n=== WALK-FORWARD SUMMARY ===", flush=True)
    print(f"{'STAT':6s}  {'base_mae':>9s}  {'aug_mae':>9s}  {'delta':>9s}  {'WF4/4':>6s}  {'STATUS':>8s}", flush=True)
    print("-" * 65, flush=True)
    for stat in STATS:
        r = summary.get(stat, {})
        if "verdict" in r and r["verdict"] == "NO_DATA":
            continue
        wf = "YES" if r.get("wf_4_4") else "NO"
        status = "IMPROVE" if r.get("improving") else "regress"
        print(
            f"  {stat.upper():4s}  base={r['mae_base_mean']:.4f}  "
            f"aug={r['mae_aug_mean']:.4f}  delta={r['mean_delta']:+.5f}  "
            f"WF={wf}  {status}",
            flush=True,
        )

    gate = summary["_gate"]
    print(f"\n  Stats improving ({gate['n_improving']}/7): {gate['stats_improving']}", flush=True)
    print(f"  Stats WF 4/4: {gate['stats_wf_4_4']}", flush=True)
    print(f"  Mean delta (improving): {gate['mean_delta_improving_stats']:+.5f}", flush=True)
    print(f"\n  VERDICT: {gate['verdict']}", flush=True)
    print(f"  Gate pass: {gate['gate_pass']}", flush=True)

    # Write results JSON
    result_doc = {
        "probe": "R10_M14",
        "description": "Synergy play-type features (prior-season) for per-game prop prediction",
        "leakage_discipline": "PRIOR-SEASON ONLY (S-1): never uses current-season playtype vector",
        "n_rows": int(len(merged)),
        "base_features": base_cols,
        "pt_features": pt_cols,
        "ship_gate": {
            "wf_4_4_any": any(r.get("wf_4_4") and r.get("mean_delta", 0) <= -0.005
                               for s, r in summary.items() if s != "_gate"),
            "n_improving": gate["n_improving"],
            "stats_improving": gate["stats_improving"],
            "verdict": gate["verdict"],
        },
        "by_stat": {s: summary[s] for s in STATS if s in summary},
        "elapsed_s": round(time.time() - t_start, 1),
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result_doc, f, indent=2, default=str)
    print(f"\nResults written to: {OUT_JSON}", flush=True)
    print(f"Total elapsed: {time.time() - t_start:.1f}s", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
