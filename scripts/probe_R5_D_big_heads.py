"""scripts/probe_R5_D_big_heads.py -- R5-D big residual heads probe (loop 5).

Swaps the small R2_F residual head for the bigger R5-D head on each stat.
Output = BASELINE - r2f_pred + big_pred  (i.e. same clip logic as R2_F).

If a big head is unavailable for a stat, falls back to the R2_F small head,
then to plain BASELINE.

Usage:
    from scripts.probe_R5_D_big_heads import treatment
    from scripts.improve_loop.scaffold import run_endq3_probe
    run_endq3_probe("R5_D_big_heads", treatment)

CLI:
    python scripts/probe_R5_D_big_heads.py
    python scripts/probe_R5_D_big_heads.py --max-games 100
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

BIG_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_big")
R2F_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]

# Module-level caches
_big_cache: Dict[str, object] = {}
_r2f_cache: Dict[str, object] = {}
_positions_cache: Optional[Dict[int, str]] = None


def _load_heads(head_dir: str) -> Dict[str, object]:
    """Load all available .lgb heads from a directory."""
    import lightgbm as lgb
    heads: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(head_dir, f"{stat}.lgb")
        if os.path.exists(path):
            try:
                heads[stat] = lgb.Booster(model_file=path)
            except Exception as exc:
                print(f"  WARN: could not load {path}: {exc}")
    return heads


def _load_positions() -> Dict[int, str]:
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
    """Apply R5-D big head corrections on top of BASELINE.

    For each (pid, stat):
      out = BASELINE - r2f_pred + big_pred
    where both heads use the same clip as R2_F.
    Falls back to R2_F head if no big head, then BASELINE.
    """
    global _big_cache, _r2f_cache, _positions_cache

    if not _big_cache:
        _big_cache = _load_heads(BIG_HEAD_DIR)
    if not _r2f_cache:
        _r2f_cache = _load_heads(R2F_HEAD_DIR)
    if _positions_cache is None:
        _positions_cache = _load_positions()

    import numpy as np

    base = BASELINE(snap)

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
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
        feat = np.array([[
            cur_pts,
            float(player.get("reb", 0)),
            float(player.get("ast", 0)),
            float(player.get("fg3m", 0)),
            float(player.get("stl", 0)),
            float(player.get("blk", 0)),
            float(player.get("tov", 0)),
            float(player.get("pf", 0)),
            float(player.get("min", 0)),
            margin,
            float(raw_margin > 0),
            pos_c,
            pos_f,
            pos_g,
        ]], dtype=np.float32)

        for stat in STATS:
            key = (pid, stat)
            projected = base.get(key)
            if projected is None:
                continue

            big_head = _big_cache.get(stat)
            r2f_head = _r2f_cache.get(stat)

            cur_stat = float(player.get(stat, 0))
            lo = -cur_stat
            hi = max(0.0, 2.0 * projected)

            if big_head is not None:
                # Compute both residuals and swap: out = baseline - r2f_pred + big_pred
                big_residual = float(big_head.predict(feat)[0])
                if r2f_head is not None:
                    r2f_residual = float(r2f_head.predict(feat)[0])
                else:
                    r2f_residual = 0.0

                # Apply big_pred correction (same clip logic as R2_F)
                adjusted = float(projected) - r2f_residual + big_residual
                # Clip relative to projected
                correction = adjusted - float(projected)
                correction = max(lo, min(hi, correction))
                adjusted = float(projected) + correction
                adjusted = max(0.0, adjusted)
                out[key] = adjusted

            elif r2f_head is not None:
                # Fall back to plain R2_F head (same as probe_R2_F_residual_heads)
                residual_pred = float(r2f_head.predict(feat)[0])
                adjusted = float(projected) + residual_pred
                adjusted = max(float(projected) + lo, min(float(projected) + hi, adjusted))
                adjusted = max(0.0, adjusted)
                out[key] = adjusted
            # else: leave as BASELINE

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R5-D big residual heads probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_big = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(BIG_HEAD_DIR, f"{s}.lgb"))
    )
    n_r2f = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(R2F_HEAD_DIR, f"{s}.lgb"))
    )
    print(f"  big heads: {n_big}/7   r2f heads (fallback): {n_r2f}/7")
    if n_big == 0:
        print("  No big heads found. Run train_residual_heads_big.py first.")
        return 1

    run_endq3_probe(
        "R5_D_big_heads",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
