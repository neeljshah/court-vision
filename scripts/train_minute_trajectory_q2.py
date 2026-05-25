"""train_minute_trajectory_q2.py -- R2_A probe support (loop 5).

Trains a DEDICATED endQ2 remaining-minutes model.  The parent
minute_trajectory.py was trained at endQ3; at endQ2 it is OOD (Q3 features
zero-filled), causing +0.51 PTS regression (cycle 113 / R1_A).

This model uses ONLY endQ2-observable features (10 total):
    pf_through_q2, min_q1, min_q2, period=2,
    score_margin_abs, is_leading_team,
    pos_C, pos_F, pos_G, l20_min, l5_min

Target: min_q3 + min_q4 (remaining minutes after Q2 ends).
Rows with min_q1+min_q2 < 0.5 are skipped (no useful signal).

Artifacts:
    data/models/minute_trajectory_q2.lgb
    data/models/minute_trajectory_q2_meta.json

Usage:
    python scripts/train_minute_trajectory_q2.py
    python scripts/train_minute_trajectory_q2.py --max-games 100  (debug)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")
_POSITIONS = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")

MODEL_PATH = os.path.join(PROJECT_DIR, "data", "models", "minute_trajectory_q2.lgb")
META_PATH  = os.path.join(PROJECT_DIR, "data", "models", "minute_trajectory_q2_meta.json")

# 10 features for endQ2 model (no Q3 features).
FEATURE_NAMES_Q2: List[str] = [
    "pf_through_q2",
    "min_q1", "min_q2",
    "period",
    "score_margin_abs", "is_leading_team",
    "pos_C", "pos_F", "pos_G",
    "l20_min", "l5_min",
]


# ── helpers (mirrors train_minute_trajectory.py) ──────────────────────────────

def _parse_gamelog_date(s) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def load_positions() -> Dict[int, str]:
    import pandas as pd
    if not os.path.exists(_POSITIONS):
        return {}
    df = pd.read_parquet(_POSITIONS)
    out: Dict[int, str] = {}
    for _, r in df.iterrows():
        try:
            pid = int(r["player_id"])
        except (TypeError, ValueError):
            continue
        pos = str(r.get("position") or "")
        if pos:
            out[pid] = pos
    return out


def load_player_gamelog_minutes() -> Dict[int, List[Tuple[str, float]]]:
    out: Dict[int, List[Tuple[str, float]]] = {}
    for fp in glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")):
        base = os.path.basename(fp)
        parts = base.split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                games = json.load(fh) or []
        except Exception:
            continue
        for row in games:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None:
                continue
            try:
                m = float(row.get("MIN") or 0)
            except (TypeError, ValueError):
                continue
            if m < 1.0:
                continue
            out.setdefault(pid, []).append((d, m))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def find_game_date_for_game(game_id: str, qstats_df,
                             pid_log_index: Dict[int, List[Tuple[str, float]]]) -> Optional[str]:
    g = qstats_df[qstats_df["game_id"] == game_id]
    if g.empty:
        return None
    totals = g.groupby("player_id")["min"].sum().sort_values(ascending=False)
    for pid, min_total in totals.head(5).items():
        log = pid_log_index.get(int(pid), [])
        for (d, m) in log:
            if abs(m - float(min_total)) <= 1.0:
                return d
    return None


def rolling_mean_min(pid: int, target_date: Optional[str], window: int,
                     pid_log_index: Dict[int, List[Tuple[str, float]]]) -> Optional[float]:
    log = pid_log_index.get(pid, [])
    if not log:
        return None
    if target_date:
        prior = [m for (d, m) in log if d < target_date][-window:]
    else:
        prior = [m for (_, m) in log][-window:]
    if not prior:
        return None
    return sum(prior) / len(prior)


def _normalize_position(position_proxy: Optional[str]) -> str:
    if not position_proxy:
        return ""
    s = str(position_proxy).strip().lower()
    if not s:
        return ""
    if "center" in s:
        return "C"
    if "forward" in s:
        return "F"
    if "guard" in s:
        return "G"
    u = s.upper()
    if u == "C":
        return "C"
    if u in {"PF", "SF", "F"}:
        return "F"
    if u in {"PG", "SG", "G"}:
        return "G"
    return ""


def build_feature_row_q2(
    *,
    pf_through_q2: float,
    min_q1: float,
    min_q2: float,
    score_margin_abs: float = 0.0,
    is_leading_team: int = 0,
    position_proxy: Optional[str] = None,
    l20_min: Optional[float] = None,
    l5_min: Optional[float] = None,
) -> List[float]:
    """Build 10-dim feature row for endQ2 model (FEATURE_NAMES_Q2 order)."""
    pf  = float(max(0, int(pf_through_q2)))
    m1  = float(max(0.0, min_q1))
    m2  = float(max(0.0, min_q2))
    margin  = abs(float(score_margin_abs))
    leading = 1 if int(is_leading_team) >= 1 else 0
    pos = _normalize_position(position_proxy)
    is_c = 1.0 if pos == "C" else 0.0
    is_f = 1.0 if pos == "F" else 0.0
    is_g = 1.0 if pos == "G" else 0.0
    l20 = float("nan") if l20_min is None else float(l20_min)
    l5  = float("nan") if l5_min  is None else float(l5_min)
    return [pf, m1, m2, 2.0, margin, float(leading), is_c, is_f, is_g, l20, l5]


# ── corpus builder ─────────────────────────────────────────────────────────────

def build_training_corpus(max_games: Optional[int] = None) -> Tuple[
        List[List[float]], List[float], List[str]]:
    """One (X_row, y) per (game, player) observed through Q2.

    Target = min_q3 + min_q4 (sum of remaining minutes after Q2).
    Rows with min_q1+min_q2 < 0.5 are skipped.
    """
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions  = load_positions()
    pid_log_index = load_player_gamelog_minutes()

    games_in_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_in_order = games_in_order[:max_games]

    X_rows:       List[List[float]] = []
    y:            List[float]       = []
    game_id_rows: List[str]         = []

    for gid in games_in_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue
        target_date = find_game_date_for_game(gid, df, pid_log_index)

        for pid in gdf["player_id"].unique():
            pdf = gdf[gdf["player_id"] == pid]
            min_by_q: Dict[int, float] = {}
            pf_by_q:  Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pf_by_q[p]  = float(r["pf"])

            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_through_q2 = min_q1 + min_q2

            # Skip players with negligible Q1+Q2 minutes.
            if min_through_q2 < 0.5:
                continue

            pf_through_q2 = pf_by_q.get(1, 0.0) + pf_by_q.get(2, 0.0)

            # Target: min_q3 + min_q4 (+ OT periods >= 5).
            rem_min = 0.0
            for _, r in pdf.iterrows():
                if int(r["period"]) >= 3:
                    rem_min += float(r["min"])

            pos_str = positions.get(int(pid))
            l20 = rolling_mean_min(int(pid), target_date, 20, pid_log_index)
            l5  = rolling_mean_min(int(pid), target_date, 5,  pid_log_index)

            row = build_feature_row_q2(
                pf_through_q2=pf_through_q2,
                min_q1=min_q1,
                min_q2=min_q2,
                score_margin_abs=0.0,
                is_leading_team=0,
                position_proxy=pos_str,
                l20_min=l20,
                l5_min=l5,
            )
            X_rows.append(row)
            y.append(float(rem_min))
            game_id_rows.append(gid)

    return X_rows, y, game_id_rows


def chronological_split(X: List[List[float]], y: List[float],
                        game_id_rows: List[str], val_frac: float = 0.2) -> Tuple[
                            List[List[float]], List[float],
                            List[List[float]], List[float]]:
    games_order = sorted(set(game_id_rows))
    cutoff = int(len(games_order) * (1 - val_frac))
    train_games = set(games_order[:cutoff])
    X_tr, y_tr, X_val, y_val = [], [], [], []
    for x, yi, gid in zip(X, y, game_id_rows):
        if gid in train_games:
            X_tr.append(x); y_tr.append(yi)
        else:
            X_val.append(x); y_val.append(yi)
    return X_tr, y_tr, X_val, y_val


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    print("  loading + building endQ2 training corpus...")
    X, y, gids = build_training_corpus(max_games=args.max_games)
    print(f"  corpus: {len(X)} rows across {len(set(gids))} games")
    if not X:
        print("  ERROR: empty corpus, abort")
        return 2

    X_tr, y_tr, X_val, y_val = chronological_split(X, y, gids, val_frac=0.2)
    print(f"  split: train={len(X_tr)}  val={len(X_val)}")

    import lightgbm as lgb
    import numpy as np

    X_tr_arr  = np.asarray(X_tr,  dtype=np.float64)
    y_tr_arr  = np.asarray(y_tr,  dtype=np.float64)
    X_val_arr = np.asarray(X_val, dtype=np.float64)
    y_val_arr = np.asarray(y_val, dtype=np.float64)

    train_set = lgb.Dataset(X_tr_arr, label=y_tr_arr,
                            feature_name=FEATURE_NAMES_Q2)
    val_set   = lgb.Dataset(X_val_arr, label=y_val_arr,
                            feature_name=FEATURE_NAMES_Q2,
                            reference=train_set)

    params = {
        "objective":        "regression",
        "metric":           "mae",
        "learning_rate":    0.05,
        "num_leaves":       31,
        "min_data_in_leaf": 30,
        "feature_pre_filter": False,
        "verbose":          -1,
        "seed":             42,
    }
    callbacks = [
        lgb.early_stopping(stopping_rounds=30, verbose=False),
        lgb.log_evaluation(period=0),
    ]
    booster = lgb.train(
        params,
        train_set,
        num_boost_round=400,
        valid_sets=[train_set, val_set],
        valid_names=["train", "val"],
        callbacks=callbacks,
    )

    pred_val = booster.predict(X_val_arr)
    pred_tr  = booster.predict(X_tr_arr)
    tr_mae   = float(np.mean(np.abs(pred_tr  - y_tr_arr)))
    val_mae  = float(np.mean(np.abs(pred_val - y_val_arr)))
    mean_pred_mae = float(np.mean(np.abs(y_val_arr - float(np.mean(y_tr_arr)))))

    print(f"  train MAE: {tr_mae:.4f}  val MAE: {val_mae:.4f}")
    print(f"  baseline (mean-pred) val MAE: {mean_pred_mae:.4f}  "
          f"(improvement: {mean_pred_mae - val_mae:+.4f})")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    booster.save_model(MODEL_PATH)
    meta = {
        "feature_names":  FEATURE_NAMES_Q2,
        "fallback_mean":  float(np.mean(y_tr_arr)),
        "params":         params,
    }
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    print(f"  saved -> {MODEL_PATH}")
    print(f"  saved -> {META_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
