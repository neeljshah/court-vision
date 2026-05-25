"""scripts/probe_R3_H_ensemble_residual_heads.py -- R3-H probe (loop 5).

Evaluates a 5-seed ensemble of residual heads vs the R2_F single-seed (42)
head as the baseline.  Both are trained on:
    target = actual - cycle_110_projection

At inference:
  1. Build X14 for each (pid, stat) from the endQ3 snapshot.
  2. Load all available seed models; predict residual per seed; average.
  3. Load R2_F single-seed head (data/models/residual_heads/{stat}.lgb).
  4. Swap: treatment = BASELINE - r2f_pred + ensemble_pred
  5. Apply the same clip as R2_F (max 0, lower-bound from a stat floor map).

Gate: same as all improve_loop probes — WF 4/4 PTS folds <= 0, mean PTS
      delta <= -0.005, >= 4/7 stats with delta <= -0.005.

Usage:
    python scripts/probe_R3_H_ensemble_residual_heads.py
    python scripts/probe_R3_H_ensemble_residual_heads.py --max-games 200
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
SEEDS = [42, 7, 13, 99, 256]

# Directories
_R2F_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
_MULTI_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_seeds")

# Per-stat lower-clip floors (same as R2_F: predictions must stay non-negative
# and below a loose upper bound).  Upper bound = 100 for all (no realistic cap).
_STAT_FLOOR = {s: 0.0 for s in STATS}

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


# ---------------------------------------------------------------------------
# Model cache (loaded once per process)
# ---------------------------------------------------------------------------
_r2f_models: Dict[str, object] = {}       # stat -> lgb.Booster
_ensemble_models: Dict[str, List[object]] = {}  # stat -> [lgb.Booster, ...]


def _load_models():
    """Populate _r2f_models and _ensemble_models on first call."""
    global _r2f_models, _ensemble_models
    if _r2f_models:
        return  # already loaded

    import lightgbm as lgb

    # R2_F single-seed (seed=42) heads
    for stat in STATS:
        path = os.path.join(_R2F_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            _r2f_models[stat] = lgb.Booster(model_file=path)

    # Multi-seed ensemble heads
    for stat in STATS:
        _ensemble_models[stat] = []
        for seed in SEEDS:
            path = os.path.join(_MULTI_DIR, f"seed_{seed}", f"{stat}.lgb")
            if os.path.exists(path):
                _ensemble_models[stat].append(lgb.Booster(model_file=path))

    loaded_r2f = [s for s in STATS if s in _r2f_models]
    loaded_ens = {s: len(v) for s, v in _ensemble_models.items() if v}
    print(f"  [R3-H] R2F models loaded: {loaded_r2f}", flush=True)
    print(f"  [R3-H] ensemble seeds per stat: {loaded_ens}", flush=True)


# ---------------------------------------------------------------------------
# Feature builder (mirrors train_residual_heads.py)
# ---------------------------------------------------------------------------

def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def _build_X14(snap: dict, positions: Optional[Dict[int, str]] = None) -> Dict[int, List[float]]:
    """Return {pid: [14 floats]} for all players in the snapshot."""
    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))

    result: Dict[int, List[float]] = {}
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

        pos_str = ""
        if positions:
            pos_str = positions.get(pid, "")
        pos_c, pos_f, pos_g = _pos_flags(pos_str)

        result[pid] = [
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
    return result


# ---------------------------------------------------------------------------
# Lazy-load positions (same helper as training script)
# ---------------------------------------------------------------------------
_positions: Optional[Dict[int, str]] = None


def _get_positions() -> Dict[int, str]:
    global _positions
    if _positions is None:
        try:
            from scripts.train_minute_trajectory import load_positions
            _positions = load_positions()
        except Exception:
            _positions = {}
    return _positions


# ---------------------------------------------------------------------------
# Treatment function
# ---------------------------------------------------------------------------

def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """R3-H ensemble: BASELINE - r2f_pred + ensemble_mean_pred, clipped."""
    import numpy as np

    _load_models()
    positions = _get_positions()

    # Step 1: get baseline projections
    base_projs = BASELINE(snap)

    # Step 2: build X14 for all players
    x14_map = _build_X14(snap, positions)
    if not x14_map:
        return base_projs

    pids = list(x14_map.keys())
    X = np.array([x14_map[pid] for pid in pids], dtype=np.float32)

    out: Dict[Tuple[int, str], float] = {}

    for stat in STATS:
        # Get R2_F single-seed prediction
        r2f_model = _r2f_models.get(stat)
        ens_models = _ensemble_models.get(stat, [])

        if r2f_model is None or not ens_models:
            # Fall back to baseline if models missing
            for pid in pids:
                key = (pid, stat)
                if key in base_projs:
                    out[key] = base_projs[key]
            continue

        r2f_preds = np.array(r2f_model.predict(X), dtype=np.float32)

        # Step 3: ensemble prediction (average across available seeds)
        seed_preds = np.stack(
            [np.array(m.predict(X), dtype=np.float32) for m in ens_models],
            axis=0,
        )
        ensemble_preds = seed_preds.mean(axis=0)

        for i, pid in enumerate(pids):
            key = (pid, stat)
            base_val = base_projs.get(key)
            if base_val is None:
                continue

            # Swap R2_F single-seed with ensemble mean
            new_val = float(base_val) - float(r2f_preds[i]) + float(ensemble_preds[i])

            # Clip: lower-bound at floor (non-negative), no hard upper cap
            new_val = max(new_val, _STAT_FLOOR[stat])

            out[key] = new_val

    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Probe R3-H multi-seed ensemble residual heads.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    run_endq3_probe(
        name="R3_H_ensemble_residual_heads",
        treatment=treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
