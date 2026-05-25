"""probe_period_heads.py -- cycle 105b (loop 5).

Walk-forward probe of the period-specific projection heads. For each
snapshot point, runs 4-fold expanding-window CV on the training corpus and
reports per-stat WF MAE versus the linear-extrap baseline. Used as the
honesty gate before flipping the live_engine opt-in flag.

Usage:
    python scripts/probe_period_heads.py
    python scripts/probe_period_heads.py --max-games 300
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import numpy as np  # noqa: E402

from src.prediction.period_specific_heads import (  # noqa: E402
    PeriodHead, STATS, SNAPSHOT_POINTS,
)
import train_period_heads as tph  # noqa: E402


def walk_forward(X, y, gids, point: str, n_folds: int = 4) -> Tuple[float, float, int]:
    """Return (lin_mae, head_mae, n_wins_over_folds) for one (stat, point)."""
    games_order = sorted(set(gids))
    if len(games_order) < n_folds + 1:
        return float("nan"), float("nan"), 0
    # Expanding windows: each fold's train = first (start_frac * (i+1)/(n_folds+1)).
    fold_lin: List[float] = []
    fold_head: List[float] = []
    wins = 0
    for i in range(n_folds):
        cut_train = int(len(games_order) * (i + 1) / (n_folds + 1))
        cut_val = int(len(games_order) * (i + 2) / (n_folds + 1))
        train_set = set(games_order[:cut_train])
        val_set = set(games_order[cut_train:cut_val])
        X_tr, y_tr, X_val, y_val = [], [], [], []
        for x, yi, g in zip(X, y, gids):
            if g in train_set:
                X_tr.append(x); y_tr.append(yi)
            elif g in val_set:
                X_val.append(x); y_val.append(yi)
        if len(X_tr) < 100 or len(X_val) < 20:
            continue
        lin_mae = tph.linear_extrap_baseline_mae(point, X_val, y_val)
        head = PeriodHead(stat="probe", point=point)
        head.fit(X_tr, y_tr, num_boost_round=200, learning_rate=0.05,
                 num_leaves=31, min_data_in_leaf=30, seed=42)
        pred = head.predict(X_val)
        head_mae = float(np.mean(np.abs(pred - np.asarray(y_val))))
        fold_lin.append(lin_mae)
        fold_head.append(head_mae)
        if head_mae < lin_mae:
            wins += 1
    if not fold_lin:
        return float("nan"), float("nan"), 0
    return float(np.mean(fold_lin)), float(np.mean(fold_head)), wins


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    ap.add_argument("--output", default=os.path.join(
        PROJECT_DIR, "scripts", "_results", "period_heads_probe_v1.md"))
    args = ap.parse_args()

    print("  building corpora...")
    corpora = tph.build_corpus(max_games=args.max_games)

    lines: List[str] = []
    lines.append("# Period-specific heads WF probe -- cycle 105b (loop 5)\n")
    lines.append("4-fold expanding-window walk-forward. Win = head MAE < linear-extrap MAE on a fold.\n")
    lines.append("| stat | point | n_total | lin_mae | head_mae | folds_won |")
    lines.append("|------|-------|---------|---------|----------|-----------|")

    per_point_wins: Dict[str, List[Tuple[str, bool]]] = defaultdict(list)
    for point in SNAPSHOT_POINTS:
        for stat in STATS:
            X, y, gids = corpora[(stat, point)]
            if len(X) < 200:
                lines.append(f"| {stat} | {point} | {len(X)} | -- | -- | SKIP |")
                continue
            lin, head, wins = walk_forward(X, y, gids, point, n_folds=4)
            lines.append(f"| {stat} | {point} | {len(X)} | {lin:.4f} | {head:.4f} | {wins}/4 |")
            print(f"  [{stat}/{point}] lin={lin:.4f} head={head:.4f} wins={wins}/4")
            # Ship-grade fold count = 4/4. Relaxed gate = head < lin overall AND wins>=3.
            per_point_wins[point].append((stat, head < lin - 0.05 and wins >= 3))

    lines.append("")
    lines.append("## Per-snapshot ship gate (head beats lin by 0.05 MAE AND >= 3/4 WF folds)")
    lines.append("")
    for point in SNAPSHOT_POINTS:
        winners = [s for (s, w) in per_point_wins.get(point, []) if w]
        total = len(per_point_wins.get(point, []))
        verdict = "SHIP" if len(winners) >= 4 else "REJECT"
        lines.append(f"- **{point}**: {len(winners)}/{total} stats pass ({verdict}). "
                     f"Winners: {winners}")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
