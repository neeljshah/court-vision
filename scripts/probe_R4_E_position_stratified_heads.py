"""scripts/probe_R4_E_position_stratified_heads.py -- R4-E position-stratified residual heads probe.

Treatment logic:
  1. Get b = BASELINE(snap)  (live_engine post-cycle-110, includes R2_F wired corrections)
  2. For each (pid, stat):
       - Determine position bucket via load_positions[pid] (G/F/C; UNK → G)
       - Compute R2_F single-head residual prediction on X14
       - Compute position-stratified head prediction on X14
       - out = BASELINE - r2f_pred + pos_pred  (swap R2_F's correction for position-stratified)
  3. If a (position, stat) head wasn't saved (failed WF gate), keep BASELINE value unchanged
     (i.e. R2_F correction stays in place, no further swap).

Heads live at:
  data/models/residual_heads_pos_G/{stat}.lgb
  data/models/residual_heads_pos_F/{stat}.lgb
  data/models/residual_heads_pos_C/{stat}.lgb

R2_F single-blind heads at:
  data/models/residual_heads/{stat}.lgb

Usage:
    from scripts.probe_R4_E_position_stratified_heads import treatment
    from scripts.improve_loop.scaffold import run_endq3_probe
    run_endq3_probe("R4_E_position_stratified_heads", treatment)

CLI:
    python scripts/probe_R4_E_position_stratified_heads.py
    python scripts/probe_R4_E_position_stratified_heads.py --max-games 100
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

# Position-stratified head dirs
POS_HEAD_DIRS = {
    "G": os.path.join(PROJECT_DIR, "data", "models", "residual_heads_pos_G"),
    "F": os.path.join(PROJECT_DIR, "data", "models", "residual_heads_pos_F"),
    "C": os.path.join(PROJECT_DIR, "data", "models", "residual_heads_pos_C"),
}

# R2_F single-position-blind heads (baseline correction already baked into BASELINE)
R2F_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]

# Module-level caches
_pos_heads_cache: Dict[str, Dict[str, object]] = {}   # {bucket: {stat: booster}}
_r2f_heads_cache: Dict[str, object] = {}              # {stat: booster}
_positions_cache: Optional[Dict[int, str]] = None


def _load_pos_heads() -> Dict[str, Dict[str, object]]:
    """Load all available position-stratified .lgb heads."""
    import lightgbm as lgb
    cache: Dict[str, Dict[str, object]] = {"G": {}, "F": {}, "C": {}}
    for bucket, head_dir in POS_HEAD_DIRS.items():
        for stat in STATS:
            path = os.path.join(head_dir, f"{stat}.lgb")
            if os.path.exists(path):
                try:
                    cache[bucket][stat] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN: could not load {path}: {exc}")
    return cache


def _load_r2f_heads() -> Dict[str, object]:
    """Load R2_F single-head models."""
    import lightgbm as lgb
    cache: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(R2F_HEAD_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            try:
                cache[stat] = lgb.Booster(model_file=path)
            except Exception as exc:
                print(f"  WARN: could not load R2_F {path}: {exc}")
    return cache


def _load_positions() -> Dict[int, str]:
    from scripts.train_minute_trajectory import load_positions
    return load_positions()


def _pos_bucket(pos_str: str) -> str:
    """Map NBA position string to G / F / C bucket. UNK → 'G'."""
    p = (pos_str or "").upper()
    if "C" in p:
        return "C"
    if "F" in p:
        return "F"
    return "G"


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
    """Position-stratified residual correction on top of BASELINE.

    For each (pid, stat):
      - If a position-specific head exists: undo R2_F correction, apply pos head.
      - Otherwise: keep BASELINE as-is (R2_F correction stays in).
    Corrections are clipped to keep final value in [cur_stat, 2 * baseline].
    """
    global _pos_heads_cache, _r2f_heads_cache, _positions_cache

    if not _pos_heads_cache:
        _pos_heads_cache = _load_pos_heads()
    if not _r2f_heads_cache:
        _r2f_heads_cache = _load_r2f_heads()
    if _positions_cache is None:
        _positions_cache = _load_positions()

    import numpy as np

    base = BASELINE(snap)  # already includes R2_F wired corrections

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

        pos_str = _positions_cache.get(pid, "")
        bucket = _pos_bucket(pos_str)
        pos_c, pos_f, pos_g = _pos_flags(pos_str)

        feat = np.array([[
            float(player.get("pts", 0)),
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
            baseline_val = base.get(key)
            if baseline_val is None:
                continue

            pos_head = _pos_heads_cache.get(bucket, {}).get(stat)
            if pos_head is None:
                # No position-specific head — keep BASELINE (R2_F stays)
                continue

            r2f_head = _r2f_heads_cache.get(stat)
            cur_stat = float(player.get(stat, 0))

            # R2_F correction that was already applied inside live_engine/BASELINE
            r2f_pred = float(r2f_head.predict(feat)[0]) if r2f_head is not None else 0.0

            # Position-stratified correction
            pos_pred = float(pos_head.predict(feat)[0])

            # Swap: undo R2_F, apply pos_pred
            adjusted = baseline_val - r2f_pred + pos_pred

            # Clip: non-negative, at most 2× original baseline
            lo = max(0.0, cur_stat)
            hi = max(0.0, 2.0 * baseline_val)
            adjusted = max(lo, min(hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R4-E position-stratified residual heads probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_heads = sum(
        1
        for bucket, head_dir in POS_HEAD_DIRS.items()
        for stat in STATS
        if os.path.exists(os.path.join(head_dir, f"{stat}.lgb"))
    )
    print(f"  {n_heads} position-stratified head(s) found.")
    if n_heads == 0:
        print("  Run train_residual_heads_by_position.py first.")
        return 1

    run_endq3_probe(
        "R4_E_position_stratified_heads",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
