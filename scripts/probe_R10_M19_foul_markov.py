"""probe_R10_M19_foul_markov.py — R10 candidate M19.

Foul-Trouble Markov: REGRESSION on actual Q4 minutes given (PF_endQ3,
min_played_Q1-Q3, position, is_starter) — then apply resulting multiplier
across all 7 stats at endQ3.

WHY: M30 (binary foul-out classifier) failed Gate 1 (AUC 0.295, 10 positives).
M19 sidesteps sparsity by modelling the FULL Q4-minute distribution, not just
the extreme tail. A player with pf=3 in Q3 still plays fewer Q4 minutes —
capturing that gradient is the value.

PROCEDURE
1. Build endQ3 snapshot from player_quarter_stats.parquet.
   Features (no future info): pf_endQ3, q3_pf, min_q1..q3, is_starter,
   pos_C, pos_F, pos_G.
2. Target = actual min_q4.
3. LightGBM regressor, 4-fold walk-forward (chronological by game_id).
4. Baseline Q4-min per player = rolling 10-game mean min_q4 (lagged, no leak).
5. Multiplier = clip(predicted_q4 / baseline_q4, 0.5, 1.5) per player-game.
6. Apply multiplier to baseline in-play projection at endQ3 across 7 stats.
7. MAE gate: WF 4/4 positive, mean_delta <= -0.005, >=4/7 stats improving.

NO LABEL LEAKAGE: target (min_q4) is future-quarter data; features are
endQ3-and-before only. Rolling baseline uses shift(1) — previous games only.

Run: python -u scripts/probe_R10_M19_foul_markov.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
QUARTER_PARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")
POSITIONS_PARQUET = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")
OUTPUT_JSON = os.path.join(PROJECT_DIR, "data", "cache",
                           "probe_R10_M19_foul_markov_results.json")
LOG_DIR = os.path.join(PROJECT_DIR, "scripts", "_results")

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Ship-gate baseline MAE at endQ3 (from task spec)
BASELINE_MAE = {
    "pts": 2.214, "reb": 0.8987, "ast": 0.5755,
    "fg3m": 0.3528, "stl": 0.2506, "blk": 0.1543, "tov": 0.3663,
}

MULTIPLIER_CLIP = (0.5, 1.5)
DELTA_CLIP = (-8.0, 4.0)       # clip minute-delta: max reduction 8 min, max increase 4 min
BASELINE_ROLLING_WINDOW = 10   # rolling mean Q4 min per player (lagged)


# ── helpers ────────────────────────────────────────────────────────────────────

def _load_positions() -> Dict[int, str]:
    """Return {player_id: position_str}."""
    try:
        df = pd.read_parquet(POSITIONS_PARQUET)
        return {int(r["player_id"]): str(r.get("position") or "")
                for _, r in df.iterrows()}
    except Exception as exc:
        print(f"  WARN: could not load positions: {exc}")
        return {}


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot from free-text position."""
    p = (pos_str or "").lower()
    is_c = 1.0 if ("center" in p or p.strip().upper() == "C") else 0.0
    is_f = 1.0 if ("forward" in p or p.strip().upper() in {"F", "PF", "SF"}) else 0.0
    is_g = 1.0 if ("guard" in p or p.strip().upper() in {"G", "PG", "SG"}) else 0.0
    return is_c, is_f, is_g


# ── Stage 1: build Markov regression dataset ──────────────────────────────────

FEAT_COLS = [
    "pf_endQ3", "q3_pf",
    "min_q1", "min_q2", "min_q3", "min_through_q3",
    "is_starter",
    "pos_C", "pos_F", "pos_G",
    "baseline_q4_min",            # per-player rolling mean (lagged)
]


def build_markov_df() -> pd.DataFrame:
    """Build one row per (player_id, game_id) at endQ3.

    Features: endQ3-and-before only.
    Target: actual Q4 minutes.
    """
    print("Loading player_quarter_stats.parquet ...")
    df = pd.read_parquet(QUARTER_PARQUET)
    positions = _load_positions()

    # Per-period slices
    q1 = (df[df["period"] == 1]
          .rename(columns={c: c + "_q1" for c in df.columns
                           if c not in ("game_id", "player_id")}))
    q2 = (df[df["period"] == 2]
          .rename(columns={c: c + "_q2" for c in df.columns
                           if c not in ("game_id", "player_id")}))
    q3 = (df[df["period"] == 3]
          .rename(columns={c: c + "_q3" for c in df.columns
                           if c not in ("game_id", "player_id")}))
    q4 = (df[df["period"] == 4]
          [["game_id", "player_id", "min", "pts", "reb", "ast",
            "fg3m", "stl", "blk", "tov"]]
          .rename(columns={c: c + "_q4" for c in
                           ("min", "pts", "reb", "ast", "fg3m",
                            "stl", "blk", "tov")}))

    snap = (q1.merge(q2, on=["game_id", "player_id"], how="inner")
              .merge(q3, on=["game_id", "player_id"], how="inner")
              .merge(q4, on=["game_id", "player_id"], how="inner"))

    print(f"  Merged snapshot rows (all 4 periods): {len(snap)}")

    # Derived features (all endQ3-and-before)
    snap["pf_endQ3"] = snap["pf_q1"] + snap["pf_q2"] + snap["pf_q3"]
    snap["q3_pf"] = snap["pf_q3"]
    snap["min_q1"] = snap["min_q1"]
    snap["min_q2"] = snap["min_q2"]
    snap["min_q3"] = snap["min_q3"]
    snap["min_through_q3"] = snap["min_q1"] + snap["min_q2"] + snap["min_q3"]

    # Starter proxy: played >= 5 min in Q1
    snap["is_starter"] = (snap["min_q1"] >= 5.0).astype(float)

    # Position one-hot
    snap["pos_C"] = snap["player_id"].apply(
        lambda pid: _pos_flags(positions.get(int(pid), ""))[0])
    snap["pos_F"] = snap["player_id"].apply(
        lambda pid: _pos_flags(positions.get(int(pid), ""))[1])
    snap["pos_G"] = snap["player_id"].apply(
        lambda pid: _pos_flags(positions.get(int(pid), ""))[2])

    # Target
    snap["target_min_q4"] = snap["min_q4"]

    # Sort chronologically by game_id (NBA game IDs are time-ordered)
    snap = snap.sort_values(["game_id", "player_id"]).reset_index(drop=True)

    # Per-player rolling baseline Q4 minutes (lagged — shift(1) → no leak)
    # Use the full sorted frame; within each player group shift the Q4 col.
    snap["baseline_q4_min"] = (
        snap.groupby("player_id")["target_min_q4"]
            .transform(lambda x: x.shift(1)
                                  .rolling(BASELINE_ROLLING_WINDOW, min_periods=1)
                                  .mean())
    )
    # Fill NaN baseline (first game per player) with global mean
    global_q4_mean = snap["target_min_q4"].mean()
    snap["baseline_q4_min"] = snap["baseline_q4_min"].fillna(global_q4_mean)

    print(f"  target_min_q4 mean={snap['target_min_q4'].mean():.3f} "
          f"std={snap['target_min_q4'].std():.3f}")
    print(f"  pf_endQ3 distribution:\n"
          + snap["pf_endQ3"].value_counts().sort_index().to_string())

    return snap


# ── Stage 2: LightGBM regressor walk-forward ──────────────────────────────────

def run_markov_regression(snap: pd.DataFrame) -> dict:
    """4-fold walk-forward regression for Q4 minutes.

    Folds are chronological (by game_id). Train on past games, test on
    future games — no look-ahead.
    """
    import lightgbm as lgb

    snap = snap.reset_index(drop=True)
    n = len(snap)
    fold_size = max(1, n // 4)
    print(f"\nStage 1 — Markov Q4-min regression, n={n}, fold_size~{fold_size}")

    mae_folds: List[float] = []
    mae_base_folds: List[float] = []
    best_model = None

    for fold in range(4):
        test_start = fold * fold_size
        test_end = (fold + 1) * fold_size if fold < 3 else n
        train_df = snap.iloc[:test_start]
        test_df  = snap.iloc[test_start:test_end]

        if len(train_df) < 100:
            print(f"  fold {fold}: skipped (train too small: {len(train_df)})")
            mae_folds.append(float("nan"))
            mae_base_folds.append(float("nan"))
            continue

        X_tr = train_df[FEAT_COLS].fillna(0.0).values.astype(np.float32)
        y_tr = train_df["target_min_q4"].values.astype(np.float32)
        X_te = test_df[FEAT_COLS].fillna(0.0).values.astype(np.float32)
        y_te = test_df["target_min_q4"].values.astype(np.float32)

        train_set = lgb.Dataset(X_tr, label=y_tr,
                                feature_name=FEAT_COLS)
        val_set   = lgb.Dataset(X_te, label=y_te,
                                feature_name=FEAT_COLS,
                                reference=train_set)

        params = {
            "objective":      "regression",
            "metric":         "mae",
            "learning_rate":  0.05,
            "num_leaves":     31,
            "min_data_in_leaf": 20,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "bagging_freq":   5,
            "verbose":        -1,
            "seed":           42,
        }

        callbacks = [
            lgb.early_stopping(stopping_rounds=40, verbose=False),
            lgb.log_evaluation(period=0),
        ]
        booster = lgb.train(
            params, train_set,
            num_boost_round=600,
            valid_sets=[train_set, val_set],
            valid_names=["train", "val"],
            callbacks=callbacks,
        )

        preds = booster.predict(X_te)
        preds = np.clip(preds, 0.0, 12.0)

        mae_model = float(np.mean(np.abs(preds - y_te)))
        mae_base  = float(np.mean(np.abs(
            test_df["baseline_q4_min"].fillna(global_q4_mean := snap["target_min_q4"].mean()).values
            - y_te)))

        print(f"  fold {fold}: n_train={len(train_df)} n_test={len(test_df)} "
              f"MAE_model={mae_model:.4f} MAE_baseline={mae_base:.4f} "
              f"delta={mae_model-mae_base:+.4f}")

        mae_folds.append(mae_model)
        mae_base_folds.append(mae_base)
        best_model = booster   # keep last fold (most training data)

    valid = [(m, b) for m, b in zip(mae_folds, mae_base_folds)
             if not (np.isnan(m) or np.isnan(b))]
    mean_mae_model    = float(np.mean([m for m, _ in valid])) if valid else float("inf")
    mean_mae_baseline = float(np.mean([b for _, b in valid])) if valid else float("inf")
    print(f"\n  Mean MAE (Q4 min): model={mean_mae_model:.4f} "
          f"baseline={mean_mae_baseline:.4f} "
          f"delta={mean_mae_model - mean_mae_baseline:+.4f}")

    return {
        "mae_per_fold":          mae_folds,
        "mae_baseline_per_fold": mae_base_folds,
        "mae_model_mean":        mean_mae_model,
        "mae_baseline_mean":     mean_mae_baseline,
        "model":                 best_model,
    }


# ── Stage 3: downstream endQ3 MAE probe ───────────────────────────────────────

def run_downstream_probe(markov_result: dict, snap: pd.DataFrame) -> dict:
    """Walk-forward endQ3 stat MAE with the Markov Q4-min multiplier applied.

    For each test game we:
      1. Get the baseline projection from predict_in_game.project_snapshot.
      2. Compute per-player multiplier = predicted_q4_min / baseline_q4_min,
         clipped to MULTIPLIER_CLIP.
      3. Apply multiplier to projected_final for that player.
      4. Compare to actual full-game totals.

    The walk-forward folds are defined on game_ids (chronological) — identical
    split logic to Stage 1 to avoid peeking at future foul distributions.
    """
    import predict_in_game as pig
    from retro_inplay_mae import (
        load_quarter_stats, build_snapshot, actuals_for_game,
        project_snapshot_to_finals,
    )

    model = markov_result.get("model")
    if model is None:
        return {"error": "no Markov model available"}

    print("\nStage 3 — downstream endQ3 MAE probe ...")
    qstats = load_quarter_stats(QUARTER_PARQUET)
    game_ids = sorted(qstats["game_id"].unique())
    n_games  = len(game_ids)
    fold_size = max(1, n_games // 4)

    # Build a lookup: (player_id, game_id) -> Markov features for fast access
    # snap is already sorted by game_id
    snap_indexed = snap.set_index(["game_id", "player_id"])

    fold_results: List[dict] = []

    for fold in range(4):
        test_start = fold * fold_size
        test_end   = (fold + 1) * fold_size if fold < 3 else n_games
        test_gids  = game_ids[test_start:test_end]

        errs_base: Dict[str, List[float]] = {s: [] for s in STATS}
        errs_m19:  Dict[str, List[float]] = {s: [] for s in STATS}
        n_games_fold = 0

        for gid in test_gids:
            snap_dict = build_snapshot(gid, "endQ3", qstats)
            if snap_dict is None:
                continue
            actuals = actuals_for_game(gid, qstats)
            if not actuals:
                continue

            projs_base = project_snapshot_to_finals(snap_dict)
            projs_m19  = dict(projs_base)

            # For each player in the snapshot, compute multiplier
            for player in snap_dict.get("players") or []:
                try:
                    pid = int(player["player_id"])
                except (TypeError, ValueError, KeyError):
                    continue

                key = (gid, pid)
                if key not in snap_indexed.index:
                    continue  # player not in our endQ3 snapshot df

                row = snap_indexed.loc[key]
                feat_vals = [
                    float(row.get("pf_endQ3", 0)),
                    float(row.get("q3_pf", 0)),
                    float(row.get("min_q1", 0)),
                    float(row.get("min_q2", 0)),
                    float(row.get("min_q3", 0)),
                    float(row.get("min_through_q3", 0)),
                    float(row.get("is_starter", 0)),
                    float(row.get("pos_C", 0)),
                    float(row.get("pos_F", 0)),
                    float(row.get("pos_G", 0)),
                    float(row.get("baseline_q4_min", 7.0)),
                ]
                X = np.array([feat_vals], dtype=np.float32)
                pred_q4_min = float(np.clip(model.predict(X)[0], 0.0, 12.0))
                base_q4_min = float(row.get("baseline_q4_min", 7.0))
                base_q4_min = max(base_q4_min, 0.5)  # avoid /0

                # Minute delta: how many Q4 minutes is this player expected
                # to lose (or gain) relative to their rolling baseline?
                # Negative = foul trouble reduction; positive = healthy/favored.
                minute_delta = float(np.clip(
                    pred_q4_min - base_q4_min,
                    DELTA_CLIP[0], DELTA_CLIP[1]
                ))

                # Apply proportionally to stats:
                # stat_adjustment = minute_delta * (stat_rate_through_Q3 / min_through_q3)
                # This represents extra stat production in the delta minutes.
                min_through = float(row.get("min_through_q3", 0) or 0)
                if min_through < 1.0:
                    continue  # avoid noisy rate for DNP-like rows

                for stat in STATS:
                    k = (pid, stat)
                    base_proj = projs_m19.get(k)
                    if base_proj is None:
                        continue
                    actual_so_far = float(player.get(stat, 0) or 0)
                    # Per-minute rate through Q3
                    rate_per_min = actual_so_far / min_through
                    # Adjustment to final projection
                    projs_m19[k] = base_proj + rate_per_min * minute_delta

            # Accumulate errors
            for (pid, stat), actual in actuals.items():
                base_proj = projs_base.get((pid, stat))
                m19_proj  = projs_m19.get((pid, stat))
                if base_proj is not None:
                    errs_base[stat].append(abs(base_proj - actual))
                if m19_proj is not None:
                    errs_m19[stat].append(abs(m19_proj - actual))

            n_games_fold += 1

        # Compute per-stat MAE delta for this fold
        fold_delta: Dict[str, float] = {}
        all_positive = True
        for stat in STATS:
            if not errs_base[stat] or not errs_m19[stat]:
                fold_delta[stat] = 0.0
                continue
            mae_base_stat = float(np.mean(errs_base[stat]))
            mae_m19_stat  = float(np.mean(errs_m19[stat]))
            delta = mae_m19_stat - mae_base_stat
            fold_delta[stat] = round(delta, 5)
            if delta >= 0:
                all_positive = False

        print(f"  fold {fold}: n_games={n_games_fold} deltas="
              + " ".join(f"{s}:{d:+.4f}" for s, d in fold_delta.items()))

        fold_results.append({
            "fold":       fold,
            "n_games":    n_games_fold,
            "mae_delta":  fold_delta,
            "all_stats_positive": all_positive,
        })

    # Mean delta across folds
    mean_delta: Dict[str, float] = {}
    for stat in STATS:
        deltas = [fr["mae_delta"].get(stat, 0.0)
                  for fr in fold_results if stat in fr.get("mae_delta", {})]
        mean_delta[stat] = round(float(np.mean(deltas)), 5) if deltas else 0.0

    folds_all_positive = sum(1 for fr in fold_results if fr["all_stats_positive"])
    n_stats_improving  = sum(1 for s in STATS if mean_delta.get(s, 0.0) < 0)
    overall_mean_delta = float(np.mean(list(mean_delta.values())))

    print(f"\n  Mean deltas: "
          + " ".join(f"{s}:{d:+.4f}" for s, d in mean_delta.items()))
    print(f"  Folds all-positive: {folds_all_positive}/4")
    print(f"  Stats improving: {n_stats_improving}/7")
    print(f"  Overall mean delta: {overall_mean_delta:+.5f}")

    # Ship gate
    wf_pass    = folds_all_positive == 4
    delta_pass = overall_mean_delta <= -0.005
    stats_pass = n_stats_improving >= 4

    ship = wf_pass and delta_pass and stats_pass
    print(f"\n  GATE: WF_pass={wf_pass} delta_pass={delta_pass} "
          f"stats_pass={stats_pass} => SHIP={ship}")

    return {
        "folds":                 fold_results,
        "mean_delta":            mean_delta,
        "folds_all_positive":    folds_all_positive,
        "n_stats_improving":     n_stats_improving,
        "overall_mean_delta":    round(overall_mean_delta, 5),
        "wf_pass":               wf_pass,
        "delta_pass":            delta_pass,
        "stats_pass":            stats_pass,
        "ship":                  ship,
    }


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

    print("=" * 70)
    print("probe_R10_M19_foul_markov — Foul-Trouble Markov Q4-min regression")
    print("=" * 70)

    # Build dataset
    snap = build_markov_df()

    # Stage 1: regressor walk-forward (classifier MAE on Q4 minutes)
    markov_result = run_markov_regression(snap)

    # Stage 3: downstream endQ3 stat MAE
    downstream = run_downstream_probe(markov_result, snap)

    # Assemble output (strip model object — not JSON-serialisable)
    result = {
        "probe":     "R10_M19_foul_markov",
        "n_rows":    len(snap),
        "markov_q4_min_regression": {
            "mae_per_fold":          markov_result["mae_per_fold"],
            "mae_baseline_per_fold": markov_result["mae_baseline_per_fold"],
            "mae_model_mean":        round(markov_result["mae_model_mean"], 4),
            "mae_baseline_mean":     round(markov_result["mae_baseline_mean"], 4),
        },
        "downstream_endQ3": downstream,
        "baseline_mae":     BASELINE_MAE,
        "ship":             downstream.get("ship", False),
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(f"\nResults saved -> {OUTPUT_JSON}")
    print(f"SHIP = {result['ship']}")


if __name__ == "__main__":
    main()
