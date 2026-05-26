"""
probe_R10_M5_inplay_winprob.py
In-game win-probability updates at endQ1, endQ2, endQ3.

Separate LightGBM binary classifiers per snapshot. Features use only
information available at or before that snapshot. 4-fold walk-forward CV.

SHIP gate: any snapshot with mean_brier <= 0.183 AND mean_accuracy >= 0.72.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBA_CACHE = os.path.join(PROJECT, "data", "nba")
DATA_CACHE = os.path.join(PROJECT, "data", "cache")
OUT_JSON = os.path.join(DATA_CACHE, "probe_R10_M5_inplay_winprob_results.json")

os.makedirs(DATA_CACHE, exist_ok=True)

# ── Data loading ───────────────────────────────────────────────────────────────

def load_linescores() -> Dict[str, Dict]:
    path = os.path.join(NBA_CACHE, "linescores_all.json")
    with open(path) as f:
        return json.load(f)


def load_season_games() -> Dict[str, Dict]:
    """Load 2022-23, 2023-24, 2024-25 season_games into gid -> row dict."""
    seasons = ["2022-23", "2023-24", "2024-25"]
    all_rows: Dict[str, Dict] = {}
    for s in seasons:
        path = os.path.join(NBA_CACHE, f"season_games_{s}.json")
        if not os.path.exists(path):
            print(f"  [WARN] missing {path}", flush=True)
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("rows", []):
            all_rows[row["game_id"]] = row
    return all_rows


# ── Feature engineering ────────────────────────────────────────────────────────

MINUTES_PER_QUARTER = 12.0


def build_rows(linescores: Dict, season_games: Dict) -> pd.DataFrame:
    """
    Build one row per (game_id, snapshot) where snapshot ∈ {endQ1, endQ2, endQ3}.
    Features are computed from quarter scores up to the snapshot only.
    """
    records: List[Dict] = []

    for gid, ls in linescores.items():
        sg = season_games.get(gid)
        if sg is None:
            continue

        # Require all 4 quarter scores present and non-null
        required_qs = ["home_q1", "home_q2", "home_q3", "home_q4",
                       "away_q1", "away_q2", "away_q3", "away_q4"]
        if any(ls.get(k) is None for k in required_qs):
            continue

        hq = [ls["home_q1"], ls["home_q2"], ls["home_q3"], ls["home_q4"]]
        aq = [ls["away_q1"], ls["away_q2"], ls["away_q3"], ls["away_q4"]]

        home_total = sum(hq)
        away_total = sum(aq)

        # Label: home won (using final scores from linescore)
        home_team_won = int(home_total > away_total)

        game_date = sg.get("game_date", "1900-01-01")
        home_team_id = ls.get("home_team_id", 0) or sg.get("home_team", "UNK")
        season = sg.get("season", "unknown")

        # pregame win prob from sim_win_prob in season_games
        pregame_wp = sg.get("sim_win_prob")
        if pregame_wp is None:
            pregame_wp = 0.5  # fallback

        # Cumulative scores per quarter endpoint
        for snap_idx, snapshot in enumerate(["endQ1", "endQ2", "endQ3"]):
            n_qtrs = snap_idx + 1
            minutes_played = n_qtrs * MINUTES_PER_QUARTER

            h_cum = sum(hq[:n_qtrs])
            a_cum = sum(aq[:n_qtrs])
            total_pts = h_cum + a_cum

            # Filter: endQ3 total must be >= 60 (checked per spec across all games at endQ3)
            if snapshot == "endQ3" and total_pts < 60:
                continue

            score_margin = h_cum - a_cum
            pace_so_far = total_pts / minutes_played  # pts/min

            # Quarter-by-quarter deltas (only those available at snapshot)
            q1_delta = hq[0] - aq[0]
            q2_delta = (hq[1] - aq[1]) if n_qtrs >= 2 else np.nan
            q3_delta = (hq[2] - aq[2]) if n_qtrs >= 3 else np.nan

            # Momentum: scoring run in most recent quarter
            last_q_margin = hq[n_qtrs - 1] - aq[n_qtrs - 1]

            row = {
                "game_id": gid,
                "game_date": game_date,
                "snapshot": snapshot,
                "home_team_id": home_team_id,
                "season": season,
                "score_margin": score_margin,
                "total_pts": total_pts,
                "pace_so_far": pace_so_far,
                "q1_delta": q1_delta,
                "q2_delta": q2_delta,
                "q3_delta": q3_delta,
                "last_q_margin": last_q_margin,
                "pregame_win_prob": pregame_wp,
                "home_team_won": home_team_won,
            }
            records.append(row)

    df = pd.DataFrame(records)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  Built {len(df)} snapshot rows from {len(df['game_id'].unique())} games",
          flush=True)
    return df


# ── Walk-forward CV ────────────────────────────────────────────────────────────

def walk_forward_cv(
    X: pd.DataFrame,
    y: pd.Series,
    n_folds: int = 4,
) -> List[Dict[str, float]]:
    """
    4-fold expanding-window walk-forward CV.
    Fold i trains on rows 0..split_i, tests on rows split_i..split_{i+1}.
    """
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score,
        brier_score_loss,
        log_loss,
        roc_auc_score,
    )

    n = len(X)
    # First fold uses 60% for training, remaining split evenly for test folds
    min_train = int(n * 0.60)
    test_size = (n - min_train) // n_folds

    fold_results = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        test_start = train_end
        test_end = test_start + test_size if fold < n_folds - 1 else n

        if train_end < 30 or test_start >= n:
            print(f"  Fold {fold}: not enough data, skip", flush=True)
            continue

        X_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        X_te, y_te = X.iloc[test_start:test_end], y.iloc[test_start:test_end]

        if len(X_te) < 10:
            print(f"  Fold {fold}: test set too small ({len(X_te)}), skip", flush=True)
            continue

        cat_cols = [c for c in ["home_team_id", "season"] if c in X_tr.columns]
        for c in cat_cols:
            X_tr = X_tr.copy()
            X_te = X_te.copy()
            X_tr[c] = X_tr[c].astype("category")
            X_te[c] = X_te[c].astype("category")

        model = lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=4,
            verbose=-1,
        )
        model.fit(
            X_tr, y_tr,
            categorical_feature=cat_cols if cat_cols else "auto",
        )

        probs = model.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.5).astype(int)

        fold_results.append({
            "fold": fold,
            "train_n": len(X_tr),
            "test_n": len(X_te),
            "auc": float(roc_auc_score(y_te, probs)),
            "brier": float(brier_score_loss(y_te, probs)),
            "log_loss": float(log_loss(y_te, probs)),
            "accuracy": float(accuracy_score(y_te, preds)),
        })
        print(
            f"  Fold {fold}: train={len(X_tr)}, test={len(X_te)}, "
            f"AUC={fold_results[-1]['auc']:.4f}, "
            f"Brier={fold_results[-1]['brier']:.4f}, "
            f"Acc={fold_results[-1]['accuracy']:.4f}",
            flush=True,
        )

    return fold_results


def mean_metrics(fold_results: List[Dict]) -> Dict[str, float]:
    if not fold_results:
        return {}
    keys = ["auc", "brier", "log_loss", "accuracy"]
    return {k: float(np.mean([r[k] for r in fold_results])) for k in keys}


# ── Pregame baseline Brier ─────────────────────────────────────────────────────

def compute_pregame_brier(sg_rows: Dict) -> float:
    """Compute Brier score of sim_win_prob vs actual home_win."""
    from sklearn.metrics import brier_score_loss
    preds, labels = [], []
    for row in sg_rows.values():
        wp = row.get("sim_win_prob")
        hw = row.get("home_win")
        if wp is not None and hw is not None:
            preds.append(float(wp))
            labels.append(int(hw))
    if len(preds) < 10:
        return 0.20  # placeholder
    return float(brier_score_loss(labels, preds))


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print("=== Probe R10_M5: In-Game Win Probability ===", flush=True)

    # Load data
    print("\n[1] Loading linescores and season_games ...", flush=True)
    linescores = load_linescores()
    season_games = load_season_games()
    print(f"  Linescores: {len(linescores)}, SeasonGames: {len(season_games)}", flush=True)

    # Pregame baseline
    print("\n[2] Computing pregame baseline Brier ...", flush=True)
    pregame_brier = compute_pregame_brier(season_games)
    print(f"  Pregame Brier (sim_win_prob): {pregame_brier:.4f}", flush=True)

    # Build feature rows
    print("\n[3] Building snapshot rows ...", flush=True)
    df = build_rows(linescores, season_games)

    # Apply endQ3 total_pts filter globally (for endQ3 rows only)
    # Already applied per-row in build_rows; apply a consistent filter for all snaps:
    # Drop any game that would fail the endQ3 filter (so all snapshots use same game set)
    # Find game_ids that pass endQ3 filter
    df_endq3 = df[df["snapshot"] == "endQ3"]
    valid_games = set(df_endq3["game_id"].tolist())
    df = df[df["game_id"].isin(valid_games)].copy()
    print(f"  After endQ3 total_pts filter: {len(df)} rows, "
          f"{len(valid_games)} games", flush=True)

    # Feature columns per snapshot
    SNAP_FEATURES = {
        "endQ1": ["score_margin", "total_pts", "pace_so_far", "q1_delta",
                  "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
        "endQ2": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
                  "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
        "endQ3": ["score_margin", "total_pts", "pace_so_far", "q1_delta", "q2_delta",
                  "q3_delta", "last_q_margin", "pregame_win_prob", "home_team_id", "season"],
    }

    # Run CV per snapshot
    all_results: Dict[str, Any] = {}
    ship = False
    ship_snapshot = None
    ship_reason = ""

    SHIP_BRIER = 0.183
    SHIP_ACC = 0.72

    for snapshot in ["endQ1", "endQ2", "endQ3"]:
        print(f"\n[4] Snapshot: {snapshot}", flush=True)
        sub = df[df["snapshot"] == snapshot].copy()
        feat_cols = SNAP_FEATURES[snapshot]
        X = sub[feat_cols].copy()
        y = sub["home_team_won"].copy()

        print(f"  Rows: {len(sub)}, label balance: "
              f"{y.mean():.3f} (home win rate)", flush=True)

        fold_results = walk_forward_cv(X, y, n_folds=4)
        means = mean_metrics(fold_results)

        snap_ship = (
            means.get("brier", 9.0) <= SHIP_BRIER
            and means.get("accuracy", 0.0) >= SHIP_ACC
        )

        if snap_ship and not ship:
            ship = True
            ship_snapshot = snapshot
            ship_reason = (
                f"{snapshot} mean_brier={means['brier']:.4f} <= {SHIP_BRIER}, "
                f"mean_accuracy={means['accuracy']:.4f} >= {SHIP_ACC}"
            )

        all_results[snapshot] = {
            "n_games": int(len(valid_games)),
            "n_rows": int(len(sub)),
            "folds": fold_results,
            "mean": means,
            "passes_ship_gate": snap_ship,
        }
        print(
            f"  {snapshot} MEAN: AUC={means.get('auc', 0):.4f}, "
            f"Brier={means.get('brier', 0):.4f}, "
            f"Acc={means.get('accuracy', 0):.4f} "
            f"=> {'PASS' if snap_ship else 'FAIL'}",
            flush=True,
        )

    elapsed = time.time() - t0
    status = "SHIP" if ship else "REJECT"
    if not ship:
        ship_reason = (
            "No snapshot achieved mean_brier <= 0.183 AND mean_accuracy >= 0.72. "
            "Best brier: " + str(min(
                all_results[s]["mean"].get("brier", 9) for s in all_results
            ))
        )

    result = {
        "probe": "R10_M5_inplay_winprob",
        "status": status,
        "ship_reason": ship_reason,
        "ship_snapshot": ship_snapshot,
        "pregame_brier_baseline": float(pregame_brier),
        "ship_gate": {"max_brier": SHIP_BRIER, "min_accuracy": SHIP_ACC},
        "snapshots": all_results,
        "elapsed_s": float(elapsed),
        "n_folds": 4,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n{'='*50}", flush=True)
    print(f"RESULT: {status}", flush=True)
    print(f"Reason: {ship_reason}", flush=True)
    print(f"Results saved to: {OUT_JSON}", flush=True)
    print(f"Elapsed: {elapsed:.1f}s", flush=True)

    # Summary table
    print("\n=== Snapshot Summary ===", flush=True)
    for snap, res in all_results.items():
        m = res["mean"]
        print(
            f"  {snap}: Brier={m.get('brier', 0):.4f}, "
            f"Acc={m.get('accuracy', 0):.4f}, "
            f"AUC={m.get('auc', 0):.4f} "
            f"[{'SHIP' if res['passes_ship_gate'] else 'REJECT'}]",
            flush=True,
        )


if __name__ == "__main__":
    main()
