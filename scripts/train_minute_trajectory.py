"""train_minute_trajectory.py -- tier3-10 (loop 5).

Trains :class:`src.prediction.minute_trajectory.MinuteTrajectoryModel` on the
550-game per-quarter parquet (cycle 91a). Chronological 80/20 split: earliest
80 % of game_ids train, latest 20 % validate. Writes the LightGBM artifact
to ``data/models/minute_trajectory.lgb`` plus meta JSON.

Usage:
    python scripts/train_minute_trajectory.py
    python scripts/train_minute_trajectory.py --max-games 100  (debug)
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

from src.prediction.minute_trajectory import (  # noqa: E402
    FEATURE_NAMES,
    MinuteTrajectoryModel,
    build_feature_row,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")
_POSITIONS = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")


def _parse_gamelog_date(s) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except (ValueError, TypeError):
        return None


def load_positions() -> Dict[int, str]:
    """Return {player_id: position_string}."""
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
    """For each player, build chronologically-sorted (date_iso, min) list
    from all gamelog_<pid>_*.json files. Used to compute L20 / L5 baselines
    that exclude the target game (no future-game leakage).
    """
    out: Dict[int, List[Tuple[str, float]]] = {}
    for fp in glob.glob(os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")):
        base = os.path.basename(fp)
        # gamelog_<pid>_<season>.json
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
    """Cheap game-id -> date lookup: match the highest-MIN player's full-game
    MIN total against their gamelog. Returns ISO date or None.
    """
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
    """Mean MIN over the last `window` gamelog rows strictly BEFORE
    `target_date`. None if no prior games available.
    """
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


def build_training_corpus(max_games: Optional[int] = None) -> Tuple[
        List[List[float]], List[float], List[str]]:
    """Walk the per-quarter parquet and emit one (X_row, y) per
    (game, player_who_played_any_minutes_q1-q3).

    Target = sum of period >= 4 minutes (Q4 + OT). Players with 0 min through
    Q3 are skipped (no useful signal for predicting remaining; coach decisions
    are out-of-scope).
    """
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions = load_positions()
    pid_log_index = load_player_gamelog_minutes()

    games_in_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_in_order = games_in_order[:max_games]

    X_rows: List[List[float]] = []
    y: List[float] = []
    game_id_rows: List[str] = []

    for gid in games_in_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue

        # Sum scores Q1-Q3 per team is heavy without team map; approximate
        # the score-margin context by team-agnostic totals (pts split by team
        # would require team_map). Use absolute Q1-Q3 PTS spread between
        # the two leaders' teams as a stand-in: we don't have team labels in
        # the parquet, so use 0.0 for margin (model handles missing via
        # default 0). is_leading_team also 0. The model can still learn the
        # other 12 features; we're not over-claiming a leakage path here.
        target_date = find_game_date_for_game(gid, df, pid_log_index)

        for pid in gdf["player_id"].unique():
            pdf = gdf[gdf["player_id"] == pid]
            # Per-quarter stat lookups.
            min_by_q: Dict[int, float] = {}
            pf_by_q: Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pf_by_q[p] = float(r["pf"])
            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_q3 = min_by_q.get(3, 0.0)
            min_through = min_q1 + min_q2 + min_q3
            if min_through <= 0.5:
                # Player didn't play in regulation Q1-Q3 -- no signal for
                # remaining-minute prediction. Skip.
                continue
            pf_through = pf_by_q.get(1, 0.0) + pf_by_q.get(2, 0.0) + pf_by_q.get(3, 0.0)
            q3_pf = pf_by_q.get(3, 0.0)

            # Target: sum of period >= 4.
            rem_min = 0.0
            for _, r in pdf.iterrows():
                if int(r["period"]) >= 4:
                    rem_min += float(r["min"])

            pos_str = positions.get(int(pid))
            l20 = rolling_mean_min(int(pid), target_date, 20, pid_log_index)
            l5 = rolling_mean_min(int(pid), target_date, 5, pid_log_index)

            row = build_feature_row(
                pf_through_q3=pf_through,
                q3_pf=q3_pf,
                min_q1=min_q1,
                min_q2=min_q2,
                min_q3=min_q3,
                period=3,
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
    """Split rows by GAME chronology: earliest (1-val_frac) of game_ids
    go to train, latest val_frac to val. Rows from the same game ALL stay
    on the same side.
    """
    games_order = sorted(set(game_id_rows))
    cutoff = int(len(games_order) * (1 - val_frac))
    train_games = set(games_order[:cutoff])
    X_tr, y_tr, X_val, y_val = [], [], [], []
    for x, yi, gid in zip(X, y, game_id_rows):
        if gid in train_games:
            X_tr.append(x)
            y_tr.append(yi)
        else:
            X_val.append(x)
            y_val.append(yi)
    return X_tr, y_tr, X_val, y_val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    print("  loading + building training corpus...")
    X, y, gids = build_training_corpus(max_games=args.max_games)
    print(f"  corpus: {len(X)} rows across {len(set(gids))} games")
    if not X:
        print("  ERROR: empty corpus, abort")
        return 2

    X_tr, y_tr, X_val, y_val = chronological_split(X, y, gids, val_frac=0.2)
    print(f"  split: train={len(X_tr)}  val={len(X_val)}")

    model = MinuteTrajectoryModel()
    model.fit(X_tr, y_tr, X_val=X_val, y_val=y_val,
              num_boost_round=400, learning_rate=0.05,
              num_leaves=31, min_data_in_leaf=30, seed=42)

    # Eval on val + train.
    import numpy as np
    pred_val = model.predict(X_val) if X_val else np.array([])
    val_mae = float(np.mean(np.abs(pred_val - np.asarray(y_val)))) if len(pred_val) else float("nan")
    pred_tr = model.predict(X_tr)
    tr_mae = float(np.mean(np.abs(pred_tr - np.asarray(y_tr))))
    print(f"  train MAE: {tr_mae:.4f}  val MAE: {val_mae:.4f}")
    print(f"  fallback (train mean y): {model.fallback_mean:.4f}")

    # Baseline reference: predict the global mean remaining minutes for
    # everyone. If the LightGBM model can't beat this, it learned nothing.
    if len(y_val):
        mean_pred = float(np.mean(y_tr))
        baseline_val_mae = float(np.mean(np.abs(np.asarray(y_val) - mean_pred)))
        print(f"  baseline (mean-pred) val MAE: {baseline_val_mae:.4f}  "
              f"(improvement: {baseline_val_mae - val_mae:+.4f})")

    model.save()
    print(f"  saved model -> {model.params}")
    print(f"  -> data/models/minute_trajectory.lgb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
