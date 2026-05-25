"""scripts/probe_R5_H_interaction_heads.py -- R5-H interaction-feature residual heads probe.

Loads data/models/residual_heads_v6_interactions/{stat}.lgb heads trained on
21 features (14 R2_F base + 7 interaction engineered features).

For each (pid, stat) at endQ3:
  1. Compute BASELINE(snap) projection.
  2. Build the 21-feature vector.
  3. Predict the residual correction from the v6 head.
  4. ADD the residual to BASELINE (target was actual - BASELINE, so this
     reconstructs the final projection on the same scale).
  5. Clip to keep result non-negative and bounded.

Usage:
    from scripts.probe_R5_H_interaction_heads import treatment
    from scripts.improve_loop.scaffold import run_endq3_probe
    run_endq3_probe("R5_H_interaction_heads", treatment)

CLI:
    python scripts/probe_R5_H_interaction_heads.py
    python scripts/probe_R5_H_interaction_heads.py --max-games 100
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

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v6_interactions")

FEATURE_NAMES = [
    # --- 14 base (R2_F) ---
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
    # --- 7 interaction ---
    "foul_rate", "pts_per_min", "usage_proxy",
    "margin_sign", "min_per_period", "blowout_flag", "q3_pace_proxy",
]

# Module-level cache: loaded lazily on first call to treatment()
_head_cache: Dict[str, object] = {}
_positions_cache: Optional[Dict[int, str]] = None


def _load_heads() -> Dict[str, object]:
    """Load all available v6-interaction .lgb heads into memory (once)."""
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
    """Apply v6 interaction-head residual corrections on top of BASELINE.

    Builds 21-feature vector per player, predicts residual (actual - baseline),
    adds to BASELINE projection, clips to [0, 2 * baseline] range.
    Falls back to BASELINE when no head is available for a stat.
    """
    global _head_cache, _positions_cache

    if not _head_cache:
        _head_cache = _load_heads()
    if _positions_cache is None:
        _positions_cache = _load_positions()

    import numpy as np

    base = BASELINE(snap)

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
    blowout_flag = 1.0 if margin > 15.0 else 0.0
    q3_pace_proxy = (home_pts + away_pts) / 36.0
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))

    out: Dict[Tuple[int, str], float] = dict(base)

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
        cur_reb = float(player.get("reb", 0))
        cur_ast = float(player.get("ast", 0))
        cur_fg3m = float(player.get("fg3m", 0))
        cur_stl = float(player.get("stl", 0))
        cur_blk = float(player.get("blk", 0))
        cur_tov = float(player.get("tov", 0))
        cur_pf = float(player.get("pf", 0))
        min_q3 = float(player.get("min", 0))

        safe_min = max(min_q3, 1.0)
        foul_rate = cur_pf / safe_min
        pts_per_min = cur_pts / safe_min
        usage_proxy = (cur_pts + cur_ast + cur_tov) / safe_min
        margin_sign = float(1 if raw_margin > 0 else (-1 if raw_margin < 0 else 0))
        min_per_period = min_q3 / 3.0

        feat = np.array([[
            cur_pts, cur_reb, cur_ast, cur_fg3m,
            cur_stl, cur_blk, cur_tov, cur_pf,
            min_q3, margin, float(raw_margin > 0),
            pos_c, pos_f, pos_g,
            foul_rate, pts_per_min, usage_proxy,
            margin_sign, min_per_period, blowout_flag, q3_pace_proxy,
        ]], dtype=np.float32)

        for stat in STATS:
            head = _head_cache.get(stat)
            if head is None:
                continue

            key = (pid, stat)
            projected = base.get(key)
            if projected is None:
                continue

            residual_pred = float(head.predict(feat)[0])
            cur_stat = float(player.get(stat, 0))

            # Clip: adjusted cannot go below cur_stat (already achieved),
            # or above 2x the BASELINE projected value.
            lo = cur_stat - float(projected)   # floor delta: keep at least cur
            hi = max(0.0, 2.0 * float(projected)) - float(projected)
            clipped_residual = max(lo, min(hi, residual_pred))
            adjusted = max(0.0, float(projected) + clipped_residual)

            out[key] = adjusted

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R5-H interaction heads probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_heads = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(HEAD_DIR, f"{s}.lgb"))
    )
    if n_heads == 0:
        print(
            "  No v6-interaction heads found. "
            "Run train_residual_heads_v6_interactions.py first."
        )
        return 1

    print(f"  {n_heads} head(s) found. Running R5-H probe ...")
    run_endq3_probe(
        "R5_H_interaction_heads",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
