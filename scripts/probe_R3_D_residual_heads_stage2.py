"""scripts/probe_R3_D_residual_heads_stage2.py -- R3-D stage-2 residual heads probe.

Builds on top of BASELINE (which already embeds the R2_F stage-1 correction).
For each (pid, stat), re-runs stage-1 inference locally to get stage1_pred, then
builds X15 = X14 + [stage1_pred] and calls the stage-2 head to get an additional
correction on top of BASELINE.

Final projection:
    out[(pid, stat)] = BASELINE[(pid, stat)] + stage2.predict(X15)[0]
                     = cycle_110_projection + stage1_pred + stage2_pred

Correction is clipped to [-cur_stat, 2 * baseline_projected].

Usage:
    from scripts.probe_R3_D_residual_heads_stage2 import treatment
    from scripts.improve_loop.scaffold import run_endq3_probe
    run_endq3_probe("R3_D_residual_heads_stage2", treatment)

CLI:
    python scripts/probe_R3_D_residual_heads_stage2.py
    python scripts/probe_R3_D_residual_heads_stage2.py --max-games 100
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
STAGE1_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
STAGE2_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_stage2")

FEATURE_NAMES_14 = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]

# Module-level caches: populated on first call to treatment()
_stage1_cache: Dict[str, object] = {}
_stage2_cache: Dict[str, object] = {}
_positions_cache: Optional[Dict[int, str]] = None


def _load_heads(head_dir: str) -> Dict[str, object]:
    """Load all available .lgb boosters from head_dir."""
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
    """Apply stage-1 then stage-2 residual corrections on top of BASELINE.

    Algorithm per (pid, stat):
      1. baseline_proj = BASELINE(snap)[(pid, stat)]   # includes stage-1 already
      2. Rebuild X14 locally; run stage1.predict(X14) to get stage1_pred
      3. Build X15 = X14 + [stage1_pred]
      4. stage2_pred = stage2.predict(X15)[0]
      5. adjusted = baseline_proj + stage2_pred  (clipped)

    Falls back to BASELINE when stage-2 head is unavailable for a stat.
    """
    global _stage1_cache, _stage2_cache, _positions_cache

    if not _stage1_cache:
        _stage1_cache = _load_heads(STAGE1_DIR)
    if not _stage2_cache:
        _stage2_cache = _load_heads(STAGE2_DIR)
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

        feat14 = [
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
        ]
        feat14_arr = np.array([feat14], dtype=np.float32)

        for stat in STATS:
            head2 = _stage2_cache.get(stat)
            if head2 is None:
                continue  # no stage-2 head — leave BASELINE value intact

            key = (pid, stat)
            baseline_proj = base.get(key)
            if baseline_proj is None:
                continue

            # Compute stage-1 prediction locally so we can build X15
            head1 = _stage1_cache.get(stat)
            if head1 is not None:
                stage1_pred = float(head1.predict(feat14_arr)[0])
            else:
                stage1_pred = 0.0  # stage-1 head absent — use 0

            feat15 = np.array([feat14 + [stage1_pred]], dtype=np.float32)
            stage2_pred = float(head2.predict(feat15)[0])

            cur_stat = float(player.get(stat, 0))

            # Clip: don't push below current in-game total; don't balloon > 2x baseline
            lo = -cur_stat
            hi = max(0.0, 2.0 * float(baseline_proj))
            adjusted = float(baseline_proj) + stage2_pred
            adjusted = max(float(baseline_proj) + lo,
                           min(float(baseline_proj) + hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R3-D stage-2 residual heads probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    n_heads = sum(
        1 for s in STATS
        if os.path.exists(os.path.join(STAGE2_DIR, f"{s}.lgb"))
    )
    if n_heads == 0:
        print("  No stage-2 heads found. Run train_residual_heads_stage2.py first.")
        return 1

    print(f"  {n_heads} stage-2 head(s) found. Running probe ...")
    run_endq3_probe(
        "R3_D_residual_heads_stage2",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
