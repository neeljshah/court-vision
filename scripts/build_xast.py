"""
build_xast.py — A3 channel: train xAST model on CV potential_assists + NBA priors.

Steps:
  1. Load prop_pergame dataset (all rows, min_prior=0)
  2. Load cv_features DB and build game_id -> date map from schedule files
  3. For each prop_pergame row, look up player's PRIOR CV games (before row date)
     and compute last-5 aggregates: pa_avg, touches_avg, paint_avg, shots_pp, poss_dur
  4. Train XGBoost regressor on combined features (NBA priors + CV aggregates)
  5. Generate xAST predictions for all cv_features (game_id, player_id) and write to DB
  6. Report training stats

Usage:
    conda activate basketball_ai
    python scripts/build_xast.py
"""
from __future__ import annotations

import glob
import json
import logging
import os
import pickle
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH    = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "xast_model.pkl")
SCHEDULE_DIR = os.path.join(PROJECT_DIR, "data", "nba", "schedule")

# CV features we aggregate (last 5 prior games per player)
_CV_AGG_FEATURES = [
    "potential_assists",    # -> pa_avg
    "touches_per_game",     # -> touches_avg
    "paint_dwell_pct",      # -> paint_avg
    "shots_per_possession", # -> shots_pp
    "possession_duration_avg",  # -> poss_dur
]

# NBA prior features from prop_pergame row used as model inputs
_NBA_PRIOR_COLS = [
    "l5_ast", "l10_ast", "ewma_ast", "std_ast", "prev_ast",
    "l5_min", "l10_min", "ewma_min",
    "bbref_usg_pct",       # usage rate (season-level but prior)
    "bbref_ast_pct",       # AST% (pass creation efficiency)
    "opp_def_ast",         # opponent defence factor on AST
    "rest_days",
    "is_home",
    "is_b2b",
]

# Output CV feature names (aggregated column names in combined feature vector)
_CV_OUTPUT_NAMES = ["pa_avg", "touches_avg", "paint_avg", "shots_pp", "poss_dur"]


# ── schedule helpers ──────────────────────────────────────────────────────────

def _build_game_date_map() -> Dict[str, str]:
    """Build game_id -> ISO date string from all schedule JSON files.
    Fills gaps for missing games via nearest-neighbor interpolation on game_id int.
    """
    game_date_map: Dict[str, str] = {}
    for f in glob.glob(os.path.join(SCHEDULE_DIR, "*.json")):
        try:
            with open(f) as fp:
                games = json.load(fp)
            for g in games:
                gid = g.get("game_id")
                date = g.get("date")
                if gid and date:
                    game_date_map[gid] = date
        except Exception:
            pass

    # Fill missing game_ids using nearest neighbor within same season prefix
    # (cv_features has 26/266 games not in schedule — all 2025-26 end-of-season)
    known_2526 = sorted(
        [(int(k), v) for k, v in game_date_map.items() if k.startswith("00225")],
        key=lambda x: x[0],
    )
    known_2425 = sorted(
        [(int(k), v) for k, v in game_date_map.items() if k.startswith("00224")],
        key=lambda x: x[0],
    )

    # Get all CV game_ids
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT game_id FROM cv_features")
    cv_game_ids = [r[0] for r in c.fetchall()]
    conn.close()

    for gid in cv_game_ids:
        if gid in game_date_map:
            continue
        gid_int = int(gid)
        pool = known_2526 if gid.startswith("00225") else known_2425
        if pool:
            closest = min(pool, key=lambda x: abs(x[0] - gid_int))
            game_date_map[gid] = closest[1]

    return game_date_map


# ── CV history builder ────────────────────────────────────────────────────────

def _build_cv_history(game_date_map: Dict[str, str]) -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """
    Returns {player_id: [(iso_date, {feature_name: value, ...}), ...]}
    sorted chronologically (oldest first).

    Only includes games where `potential_assists` exists for the player
    (ensures the game was tracked and CV data is real, not default-zeroed).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Pivot: get all (game_id, player_id, feature_name, feature_value) rows
    c.execute(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features"
    )
    rows = c.fetchall()
    conn.close()

    # Build per-player per-game feature dict
    # Structure: player_history[player_id][game_id] = {feat: val}
    player_history: Dict[int, Dict[str, Dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for game_id, player_id, feat, val in rows:
        if val is not None:
            player_history[player_id][game_id][feat] = float(val)

    # Convert to sorted list of (date, features) tuples, filtering out games
    # where potential_assists is missing or zero AND other features are all zero
    # (indicates a player not actually tracked in that game)
    result: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
    for player_id, games in player_history.items():
        entries = []
        for game_id, feats in games.items():
            date = game_date_map.get(game_id)
            if date is None:
                continue
            # Only include if potential_assists key exists (tracked game)
            if "potential_assists" not in feats:
                continue
            entries.append((date, feats))
        # Sort by date ascending (oldest first)
        entries.sort(key=lambda x: x[0])
        if entries:
            result[int(player_id)] = entries

    log.info(
        "CV history built: %d players, %d total game records",
        len(result),
        sum(len(v) for v in result.values()),
    )
    return result


def _get_cv_agg(
    player_id: int,
    before_date_str: str,
    cv_history: Dict[int, List[Tuple[str, Dict[str, float]]]],
    n_games: int = 5,
) -> Optional[Dict[str, float]]:
    """
    Compute last-n_games CV feature averages for player_id STRICTLY before before_date_str.
    Returns None if no prior CV games exist.
    """
    entries = cv_history.get(player_id)
    if not entries:
        return None

    # Filter to games strictly before this date
    prior = [feats for date, feats in entries if date < before_date_str]
    if not prior:
        return None

    # Take last n_games
    recent = prior[-n_games:]

    agg = {}
    for feat, col_name in zip(_CV_AGG_FEATURES, _CV_OUTPUT_NAMES):
        vals = [g[feat] for g in recent if feat in g]
        agg[col_name] = float(sum(vals) / len(vals)) if vals else 0.0

    return agg


# ── dataset builder ───────────────────────────────────────────────────────────

def build_xast_dataset(
    cv_history: Dict[int, List[Tuple[str, Dict[str, float]]]],
) -> Tuple[List[Dict], List[str], List[float]]:
    """
    Build training dataset combining prop_pergame rows with CV aggregates.

    Returns:
        rows_meta — list of {player_id, date, n_cv_games} for diagnostics
        feature_names — ordered list of feature column names
        X_list — list of feature dicts (same order as feature_names)
        y — list of target AST values
    """
    from src.prediction.prop_pergame import build_pergame_dataset

    log.info("Loading prop_pergame dataset...")
    pg_rows, _ = build_pergame_dataset(min_prior=0)
    log.info("  %d prop_pergame rows loaded", len(pg_rows))

    feature_names = _NBA_PRIOR_COLS + _CV_OUTPUT_NAMES
    X_list: List[List[float]] = []
    y: List[float] = []
    rows_meta: List[Dict] = []
    skipped_no_cv = 0
    skipped_no_target = 0

    for row in pg_rows:
        target = row.get("target_ast")
        if target is None:
            skipped_no_target += 1
            continue

        date_raw = row.get("date")
        if not date_raw:
            continue

        # Normalize date to ISO string YYYY-MM-DD
        if isinstance(date_raw, str) and "T" in date_raw:
            date_iso = date_raw[:10]
        else:
            date_iso = str(date_raw)[:10]

        player_id = row.get("player_id")
        if player_id is None:
            continue

        player_id = int(player_id)
        cv_agg = _get_cv_agg(player_id, date_iso, cv_history)

        if cv_agg is None:
            skipped_no_cv += 1
            continue

        # NBA prior features
        nba_feats = [float(row.get(c) or 0.0) for c in _NBA_PRIOR_COLS]
        # CV aggregated features
        cv_feats = [cv_agg[c] for c in _CV_OUTPUT_NAMES]

        X_list.append(nba_feats + cv_feats)
        y.append(float(target))
        rows_meta.append({
            "player_id": player_id,
            "date": date_iso,
            "n_cv_prior": len([e for e, _ in (cv_history.get(player_id) or []) if e < date_iso]),
        })

    log.info(
        "Dataset built: %d rows with CV data, %d skipped (no CV), %d skipped (no target)",
        len(X_list), skipped_no_cv, skipped_no_target,
    )
    return rows_meta, feature_names, X_list, y


# ── training ──────────────────────────────────────────────────────────────────

def train_xast_model(
    X_list: List[List[float]],
    y: List[float],
    feature_names: List[str],
) -> Tuple[object, Dict]:
    """
    Train XGBoost xAST model. Chronological 80/20 split.
    Also trains a baseline model on NBA prior features only (no CV).
    Returns (model, metrics_dict).
    """
    import numpy as np
    import xgboost as xgb

    X = np.array(X_list, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)

    n = len(y_arr)
    split_idx = int(n * 0.8)

    X_train, X_eval = X[:split_idx], X[split_idx:]
    y_train, y_eval = y_arr[:split_idx], y_arr[split_idx:]

    log.info(
        "Train/eval split: %d train / %d eval (chronological 80/20)",
        split_idx, n - split_idx,
    )

    # Full model (NBA priors + CV features)
    model = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_lambda=2.0,
        reg_alpha=0.5,
        gamma=0.2,
        random_state=42,
        objective="reg:squarederror",
        eval_metric="mae",
        device="cuda",
        tree_method="hist",
        verbosity=0,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_eval, y_eval)],
        verbose=False,
    )

    # Predictions
    y_pred_train = model.predict(X_train)
    y_pred_eval  = model.predict(X_eval)

    train_mae = float(np.mean(np.abs(y_pred_train - y_train)))
    eval_mae  = float(np.mean(np.abs(y_pred_eval  - y_eval)))

    # Training set R²
    ss_res = float(np.sum((y_train - y_pred_train) ** 2))
    ss_tot = float(np.sum((y_train - np.mean(y_train)) ** 2))
    train_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Baseline model (NBA priors only — no CV columns)
    n_nba = len(_NBA_PRIOR_COLS)
    X_train_base = X_train[:, :n_nba]
    X_eval_base  = X_eval[:, :n_nba]

    baseline = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_lambda=2.0,
        reg_alpha=0.5,
        gamma=0.2,
        random_state=42,
        objective="reg:squarederror",
        eval_metric="mae",
        device="cuda",
        tree_method="hist",
        verbosity=0,
    )
    baseline.fit(X_train_base, y_train, verbose=False)
    y_pred_base_eval = baseline.predict(X_eval_base)
    baseline_eval_mae = float(np.mean(np.abs(y_pred_base_eval - y_eval)))

    # Feature importance
    importance = model.get_booster().get_score(importance_type="gain")
    fi_sorted = sorted(importance.items(), key=lambda x: -x[1])
    top5_fi = [
        {"feature": feature_names[int(k[1:])] if k.startswith("f") else k, "gain": v}
        for k, v in fi_sorted[:5]
    ]

    metrics = {
        "n_train": int(split_idx),
        "n_eval": int(n - split_idx),
        "train_mae": round(train_mae, 4),
        "eval_mae": round(eval_mae, 4),
        "baseline_eval_mae": round(baseline_eval_mae, 4),
        "eval_delta": round(eval_mae - baseline_eval_mae, 4),
        "train_r2": round(train_r2, 4),
        "top5_feature_importance": top5_fi,
    }

    log.info("Model trained:")
    log.info("  Train MAE: %.4f", train_mae)
    log.info("  Eval MAE:  %.4f (full) vs %.4f (baseline) — delta %+.4f",
             eval_mae, baseline_eval_mae, eval_mae - baseline_eval_mae)
    log.info("  Train R²:  %.4f", train_r2)
    log.info("  Top-5 features: %s", [f['feature'] for f in top5_fi])

    return model, metrics


# ── prediction generation ─────────────────────────────────────────────────────

def generate_xast_predictions(
    model: object,
    cv_history: Dict[int, List[Tuple[str, Dict[str, float]]]],
    game_date_map: Dict[str, str],
) -> int:
    """
    For every (game_id, player_id) in cv_features with potential_assists > 0,
    generate xAST prediction and write to cv_features table as feature_name='cv_xast_pred'.
    Returns count of predictions written.
    """
    import numpy as np
    from src.prediction.prop_pergame import build_pergame_dataset

    # Build lookup: (player_id, date_iso) -> NBA prior features row
    # We need NBA prior features for each (game_id, player_id) in cv_features
    log.info("Loading prop_pergame for prediction generation...")
    pg_rows, _ = build_pergame_dataset(min_prior=0)

    # Index by (player_id, date_iso)
    player_date_to_row: Dict[Tuple[int, str], dict] = {}
    for row in pg_rows:
        date_raw = row.get("date")
        if not date_raw:
            continue
        date_iso = str(date_raw)[:10] if isinstance(date_raw, str) else str(date_raw)[:10]
        if "T" in date_iso:
            date_iso = date_iso[:10]
        pid = row.get("player_id")
        if pid is not None:
            player_date_to_row[(int(pid), date_iso)] = row

    log.info("  %d (player_id, date) lookup entries", len(player_date_to_row))

    # Get all cv_features (game_id, player_id) with potential_assists > 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT DISTINCT game_id, player_id FROM cv_features "
        "WHERE feature_name='potential_assists' AND feature_value > 0"
    )
    candidate_pairs = c.fetchall()
    log.info("  %d (game_id, player_id) candidates with potential_assists > 0", len(candidate_pairs))

    predictions: List[Tuple[str, int, float]] = []
    skipped = 0

    for game_id, player_id in candidate_pairs:
        date_iso = game_date_map.get(game_id)
        if date_iso is None:
            skipped += 1
            continue

        player_id = int(player_id)
        cv_agg = _get_cv_agg(player_id, date_iso, cv_history)
        if cv_agg is None:
            skipped += 1
            continue

        # Get NBA prior features for this (player_id, date)
        pg_row = player_date_to_row.get((player_id, date_iso))
        if pg_row is None:
            skipped += 1
            continue

        nba_feats = [float(pg_row.get(col) or 0.0) for col in _NBA_PRIOR_COLS]
        cv_feats  = [cv_agg[col] for col in _CV_OUTPUT_NAMES]
        X = np.array([nba_feats + cv_feats], dtype=np.float32)
        pred = float(model.predict(X)[0])
        predictions.append((game_id, player_id, pred))

    log.info("  %d predictions generated, %d skipped", len(predictions), skipped)

    # Write to DB: INSERT OR REPLACE
    c.execute("BEGIN")
    written = 0
    for game_id, player_id, pred in predictions:
        c.execute(
            """
            INSERT OR REPLACE INTO cv_features (game_id, player_id, feature_name, feature_value)
            VALUES (?, ?, 'cv_xast_pred', ?)
            """,
            (game_id, player_id, pred),
        )
        written += 1
    conn.commit()
    conn.close()

    log.info("  %d cv_xast_pred rows written to DB", written)
    return written


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import numpy as np

    log.info("=== A3 xAST Model: build_xast.py ===")

    # Step 1: build game_id -> date map
    log.info("Building game_id -> date map from schedule files...")
    game_date_map = _build_game_date_map()
    log.info("  %d game_id -> date mappings", len(game_date_map))

    # Step 2: build per-player CV history
    log.info("Building CV history from cv_features DB...")
    cv_history = _build_cv_history(game_date_map)

    # Step 3: build training dataset
    rows_meta, feature_names, X_list, y = build_xast_dataset(cv_history)

    n_rows = len(y)
    log.info("Training dataset: %d rows with ≥1 prior CV game", n_rows)

    if n_rows < 500:
        log.error("Too few rows (%d) to train. Aborting.", n_rows)
        sys.exit(1)

    # Step 4: train model
    model, metrics = train_xast_model(X_list, y, feature_names)

    # Save model
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "feature_names": feature_names, "metrics": metrics}, f)
    log.info("Model saved to %s", MODEL_PATH)

    # Step 5: generate predictions for all cv_features (game_id, player_id)
    n_written = generate_xast_predictions(model, cv_history, game_date_map)

    # Step 6: check distribution of written predictions
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*), MIN(feature_value), MAX(feature_value), AVG(feature_value) "
        "FROM cv_features WHERE feature_name='cv_xast_pred'"
    )
    dist = c.fetchone()
    conn.close()

    # ── Final Report ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("## A3 xAST Model — Final Report (build_xast.py)")
    print("=" * 70)

    print("\n### Training data")
    print(f"  Rows with >=1 prior CV game: {n_rows:,} / 101,765")
    print(f"  Train/eval split: {metrics['n_train']:,} train / {metrics['n_eval']:,} eval (chronological 80/20)")
    print(f"  Feature set: {feature_names}")

    print("\n### Model performance")
    print(f"  {'metric':<25} {'baseline':>10} {'+ CV':>10} {'delta':>10}")
    print(f"  {'':<25} {'----------':>10} {'----------':>10} {'----------':>10}")
    print(f"  {'eval MAE':<25} {metrics['baseline_eval_mae']:>10.4f} {metrics['eval_mae']:>10.4f} {metrics['eval_delta']:>+10.4f}")
    print(f"  {'train MAE':<25} {metrics['train_mae']:>10.4f}")
    print(f"  {'train R²':<25} {metrics['train_r2']:>10.4f}")

    print("\n### Feature importance (Top 5 by gain)")
    for i, fi in enumerate(metrics["top5_feature_importance"]):
        print(f"  {i+1}. {fi['feature']}: {fi['gain']:.1f}")

    pa_in_top5 = any("pa_avg" in fi["feature"] or "potential_assists" in fi["feature"]
                     for fi in metrics["top5_feature_importance"])
    print(f"\n  pa_avg (potential_assists) in top-5: {'YES' if pa_in_top5 else 'NO'}")

    print("\n### cv_xast_pred distribution in DB")
    if dist and dist[0]:
        print(f"  N predictions written: {dist[0]:,}")
        print(f"  Range: [{dist[1]:.3f}, {dist[2]:.3f}]")
        print(f"  Mean: {dist[3]:.3f}")
    else:
        print("  No predictions found in DB")

    print("\n### Raw metrics dict")
    print(f"  {metrics}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
