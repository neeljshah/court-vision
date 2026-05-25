"""train_period_heads.py -- cycle 105b (loop 5).

Trains 21 period-specific projection heads (7 stats x 3 snapshot points)
from data/player_quarter_stats.parquet. Each head predicts REMAINING stat
(snapshot through end-of-regulation) given the snapshot state.

Chronological split per (stat, point): earliest 80% of game_ids train,
latest 20% validate. Heads with < 200 training rows are SKIPPED (no artifact
written) so downstream callers cleanly fall back to cycle-88 linear extrap.

Usage:
    python scripts/train_period_heads.py
    python scripts/train_period_heads.py --max-games 100
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import numpy as np  # noqa: E402

from src.prediction.period_specific_heads import (  # noqa: E402
    PeriodHead, STATS, SNAPSHOT_POINTS, SNAPSHOT_QUARTERS, REMAINING_QUARTERS,
    build_feature_row,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")
_POSITIONS = os.path.join(PROJECT_DIR, "data", "player_positions.parquet")
MIN_TRAINING_ROWS = 200


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


def load_player_gamelog_stats() -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """{pid: [(date_iso, {min,pts,reb,ast,fg3m,stl,blk,tov}), ...]} sorted."""
    cols = {"min": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST",
            "fg3m": "FG3M", "stl": "STL", "blk": "BLK", "tov": "TOV"}
    out: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
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
            stats: Dict[str, float] = {}
            for k, col in cols.items():
                try:
                    stats[k] = float(row.get(col) or 0)
                except (TypeError, ValueError):
                    stats[k] = 0.0
            out.setdefault(pid, []).append((d, stats))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def find_game_date(game_id: str, qstats_df,
                   pid_logs: Dict[int, List[Tuple[str, Dict[str, float]]]]
                   ) -> Optional[str]:
    g = qstats_df[qstats_df["game_id"] == game_id]
    if g.empty:
        return None
    min_totals = g.groupby("player_id")["min"].sum().sort_values(ascending=False)
    for pid, mt in min_totals.head(5).items():
        log = pid_logs.get(int(pid), [])
        for (d, s) in log:
            if abs(s.get("min", 0.0) - float(mt)) <= 1.0:
                return d
    return None


def rolling_mean(pid: int, target_date: Optional[str], window: int, stat: str,
                 pid_logs: Dict[int, List[Tuple[str, Dict[str, float]]]]
                 ) -> Optional[float]:
    log = pid_logs.get(pid, [])
    if not log:
        return None
    if target_date:
        prior = [s for (d, s) in log if d < target_date][-window:]
    else:
        prior = [s for (_, s) in log][-window:]
    if not prior:
        return None
    return sum(p.get(stat, 0.0) for p in prior) / len(prior)


def build_corpus(max_games: Optional[int] = None
                 ) -> Dict[Tuple[str, str], Tuple[List[List[float]], List[float], List[str]]]:
    """Build one (X, y, game_ids) corpus per (stat, snapshot_point)."""
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions = load_positions()
    pid_logs = load_player_gamelog_stats()

    games_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_order = games_order[:max_games]

    corpora: Dict[Tuple[str, str], Tuple[List[List[float]], List[float], List[str]]] = {
        (s, p): ([], [], []) for s in STATS for p in SNAPSHOT_POINTS
    }

    for gid in games_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue
        target_date = find_game_date(gid, gdf, pid_logs)

        # Precompute per-player per-quarter dicts.
        per_player_qstats: Dict[int, Dict[int, Dict[str, float]]] = defaultdict(dict)
        for _, r in gdf.iterrows():
            pid = int(r["player_id"])
            per = int(r["period"])
            per_player_qstats[pid][per] = {
                "min": float(r["min"]),
                "pf":  float(r["pf"]),
                **{s: float(r[s]) for s in STATS},
            }

        for pid, by_q in per_player_qstats.items():
            pos_str = positions.get(int(pid))
            # Per-quarter L20/L5 baselines (function of pid + date only).
            l5 = {s: rolling_mean(pid, target_date, 5, s, pid_logs) for s in STATS}
            l20 = {s: rolling_mean(pid, target_date, 20, s, pid_logs) for s in STATS}
            l20m = rolling_mean(pid, target_date, 20, "min", pid_logs)

            for point in SNAPSHOT_POINTS:
                obs_qs = SNAPSHOT_QUARTERS[point]
                rem_qs = REMAINING_QUARTERS[point]
                # Must have at least one of the observed quarters and one
                # remaining quarter present (else can't form (X,y)).
                obs_data = [by_q.get(q) for q in obs_qs]
                rem_data = [by_q.get(q) for q in rem_qs]
                if not any(obs_data):
                    continue
                # Aggregate observed window.
                min_through = sum((d or {}).get("min", 0.0) for d in obs_data)
                if min_through <= 0.5:
                    continue
                pf_through = sum((d or {}).get("pf", 0.0) for d in obs_data)

                for stat in STATS:
                    cur = sum((d or {}).get(stat, 0.0) for d in obs_data)
                    # Target: remaining stat through end of regulation Q4.
                    # Skip if no regulation Q4 data (player didn't play Q4 ok,
                    # that's a valid 0 target, but if the parquet is missing
                    # Q4 entirely for this game we can't tell).
                    # We treat missing q-data as 0 minutes / 0 stat played.
                    rem = sum((d or {}).get(stat, 0.0) for d in rem_data)

                    row = build_feature_row(
                        current_stat=cur, min_through=min_through,
                        pf_through=pf_through,
                        score_margin_abs=0.0, is_leading_team=0,
                        l5_stat=l5.get(stat), l20_stat=l20.get(stat),
                        l20_min=l20m, position_proxy=pos_str,
                    )
                    X, y, gids = corpora[(stat, point)]
                    X.append(row)
                    y.append(float(rem))
                    gids.append(gid)

    return corpora


def chrono_split(X, y, gids, val_frac: float = 0.2):
    games_order = sorted(set(gids))
    cutoff = int(len(games_order) * (1 - val_frac))
    train_games = set(games_order[:cutoff])
    X_tr, y_tr, X_val, y_val = [], [], [], []
    for x, yi, g in zip(X, y, gids):
        if g in train_games:
            X_tr.append(x); y_tr.append(yi)
        else:
            X_val.append(x); y_val.append(yi)
    return X_tr, y_tr, X_val, y_val


def linear_extrap_baseline_mae(point: str,
                                X_val: List[List[float]],
                                y_val: List[float]) -> float:
    """Cycle-88 linear extrapolation baseline on the same val rows.

    rem_pred = current_stat * (remaining_share / observed_share)
    With observed_share = len(SNAPSHOT_QUARTERS[point]) / 4
    and remaining_share = 1 - observed_share.
    Note: this is the SAME math used by predict_in_game.project_remaining
    when player_clock_played_min is None (game-clock basis).
    """
    obs_share = len(SNAPSHOT_QUARTERS[point]) / 4.0
    rem_share = 1.0 - obs_share
    ratio = rem_share / obs_share if obs_share > 0 else 0.0
    if not y_val:
        return float("nan")
    errs = []
    for x, yi in zip(X_val, y_val):
        cur = x[0]  # current_stat is feature 0
        pred = cur * ratio
        errs.append(abs(pred - yi))
    return float(np.mean(errs))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--reject-summary", default=os.path.join(
        PROJECT_DIR, "scripts", "_results", "period_heads_train_v1.md"))
    args = ap.parse_args()

    print("  building corpora...")
    corpora = build_corpus(max_games=args.max_games)

    summary_lines: List[str] = []
    summary_lines.append("# Period-specific projection heads -- cycle 105b (loop 5)\n")
    summary_lines.append("| stat | point | n_train | n_val | linear_extrap_mae | trained_head_mae | delta |")
    summary_lines.append("|------|-------|---------|-------|-------------------|------------------|-------|")

    per_point_results: Dict[str, List[Tuple[str, float, float]]] = defaultdict(list)
    n_saved = 0
    for point in SNAPSHOT_POINTS:
        for stat in STATS:
            X, y, gids = corpora[(stat, point)]
            n_total = len(X)
            if n_total < MIN_TRAINING_ROWS:
                summary_lines.append(
                    f"| {stat} | {point} | {n_total} | -- | -- | -- | SKIPPED (<{MIN_TRAINING_ROWS}) |")
                continue
            X_tr, y_tr, X_val, y_val = chrono_split(X, y, gids, val_frac=0.2)
            if len(X_tr) < MIN_TRAINING_ROWS or len(X_val) < 20:
                summary_lines.append(
                    f"| {stat} | {point} | {len(X_tr)} | {len(X_val)} | -- | -- | SKIPPED (split too small) |")
                continue

            lin_mae = linear_extrap_baseline_mae(point, X_val, y_val)

            head = PeriodHead(stat=stat, point=point)
            head.fit(X_tr, y_tr, X_val=X_val, y_val=y_val,
                     num_boost_round=400, learning_rate=0.05,
                     num_leaves=31, min_data_in_leaf=30, seed=42)
            pred_val = head.predict(X_val)
            val_mae = float(np.mean(np.abs(pred_val - np.asarray(y_val))))
            delta = val_mae - lin_mae

            head.save()
            n_saved += 1
            summary_lines.append(
                f"| {stat} | {point} | {len(X_tr)} | {len(X_val)} | "
                f"{lin_mae:.4f} | {val_mae:.4f} | {delta:+.4f} |")
            per_point_results[point].append((stat, lin_mae, val_mae))
            print(f"  [{stat}/{point}] n_tr={len(X_tr)} n_val={len(X_val)} "
                  f"lin={lin_mae:.4f} head={val_mae:.4f} delta={delta:+.4f}")

    # Ship gate per snapshot point.
    summary_lines.append("")
    summary_lines.append("## Ship gate (relaxed: delta < -0.05 counts as win)")
    summary_lines.append("")
    for point in SNAPSHOT_POINTS:
        res = per_point_results.get(point, [])
        wins = sum(1 for (_, lin, head) in res if head < lin - 0.05)
        summary_lines.append(
            f"- **{point}**: {wins}/{len(res)} stats beat linear extrap by >= 0.05 MAE "
            f"({'SHIP' if wins >= 4 else 'REJECT'})")

    summary_lines.append("")
    summary_lines.append(f"Saved {n_saved} / {len(STATS) * len(SNAPSHOT_POINTS)} artifacts to "
                         f"`data/models/period_heads/`")
    os.makedirs(os.path.dirname(args.reject_summary), exist_ok=True)
    with open(args.reject_summary, "w", encoding="utf-8") as fh:
        fh.write("\n".join(summary_lines) + "\n")
    print(f"  wrote {args.reject_summary}")
    print(f"  saved {n_saved} artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
