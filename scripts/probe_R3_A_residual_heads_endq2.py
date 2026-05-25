"""scripts/probe_R3_A_residual_heads_endq2.py -- R3-A residual heads probe (endQ2).

For each (pid, stat) at endQ2, if data/models/residual_heads_endq2/{stat}.lgb exists,
adds the head's predicted residual correction to the BASELINE projection.

Correction is clipped to [-cur_stat, 2 * projected] so the adjusted value
stays non-negative and doesn't balloon more than double the original projection.

Usage:
    from scripts.probe_R3_A_residual_heads_endq2 import treatment
    from scripts.improve_loop.scaffold import run_point_probe, BASELINE
    run_point_probe("endQ2", "R3_A_residual_heads_endq2", treatment, baseline=BASELINE)

CLI:
    python scripts/probe_R3_A_residual_heads_endq2.py
    python scripts/probe_R3_A_residual_heads_endq2.py --max-games 100
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from scripts.improve_loop.scaffold import run_point_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_endq2")

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q2", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]

# Module-level cache: loaded on first call to treatment()
_head_cache: Dict[str, object] = {}
_positions_cache: Optional[Dict[int, str]] = None


def _load_heads() -> Dict[str, object]:
    """Load all available .lgb heads from residual_heads_endq2/ into memory (once)."""
    import lightgbm as lgb
    heads: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(HEAD_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            try:
                heads[stat] = lgb.Booster(model_file=path)
            except Exception as exc:
                print(f"  WARN: could not load {path}: {exc}")
    return heads


def _load_positions() -> Dict[int, str]:
    """Load player positions (cached)."""
    from scripts.train_minute_trajectory import load_positions
    return load_positions()


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """Apply endQ2 residual head corrections on top of BASELINE projections.

    For each (pid, stat): if a head exists, adjust projected_final by the
    head's predicted residual, clipped to [-cur_stat, 2 * projected_baseline].
    Falls back to BASELINE when no head is available.
    """
    global _head_cache, _positions_cache

    # Lazy-load on first call
    if not _head_cache:
        _head_cache = _load_heads()
    if _positions_cache is None:
        _positions_cache = _load_positions()

    import numpy as np

    # Get baseline projections
    base = BASELINE(snap)

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))

    out: Dict[Tuple[int, str], float] = dict(base)  # start from BASELINE

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        team = str(player.get("team", ""))
        if team == home_team:
            raw_margin = home_pts - away_pts
        elif team == away_team:
            raw_margin = away_pts - home_pts
        else:
            raw_margin = 0.0

        pos_c, pos_f, pos_g = _pos_flags(_positions_cache.get(pid, ""))

        cur_pts = float(player.get("pts", 0))
        feat = np.array([[
            cur_pts,
            float(player.get("reb", 0)),
            float(player.get("ast", 0)),
            float(player.get("fg3m", 0)),
            float(player.get("stl", 0)),
            float(player.get("blk", 0)),
            float(player.get("tov", 0)),
            float(player.get("pf", 0)),
            float(player.get("min", 0)),   # min_through_q2
            margin,
            float(raw_margin > 0),
            pos_c,
            pos_f,
            pos_g,
        ]], dtype=np.float32)

        for stat in STATS:
            head = _head_cache.get(stat)
            if head is None:
                continue

            key = (pid, stat)
            projected = base.get(key)
            if projected is None:
                continue

            # Predict residual and apply correction
            residual_pred = float(head.predict(feat)[0])
            cur_stat = float(player.get(stat, 0))

            # Clip: correction cannot push adjusted below 0 or above 2x projected
            lo = -cur_stat          # can't go below current in-game total
            hi = max(0.0, 2.0 * projected)
            adjusted = float(projected) + residual_pred
            adjusted = max(float(projected) + lo, min(float(projected) + hi, adjusted))
            # Ensure non-negative
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R3-A residual heads probe (endQ2).")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_heads = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(HEAD_DIR, f"{s}.lgb"))
    )
    if n_heads == 0:
        print("  No residual heads found. Run train_residual_heads_endq2.py first.")
        return 1

    print(f"  {n_heads} head(s) found. Running probe ...")
    run_point_probe(
        "endQ2",
        "R3_A_residual_heads_endq2",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
