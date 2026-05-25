"""src/prediction/residual_heads.py -- cycle R2_F (loop 5).

Helper module: load + apply the 7 per-stat residual LightGBM heads trained
by train_residual_heads.py. Wired into live_engine.project_from_snapshot
at endQ3 (period=4) via _apply_residual_correction.

Artifacts: data/models/residual_heads/{pts,reb,ast,fg3m,stl,blk,tov}.lgb
Probe reference: scripts/probe_R2_F_residual_heads.py (SHIP=True)
Result: PTS MAE -0.0965, 7/7 stats win, WF 4/4 folds negative.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Module-level lazy caches.
_HEAD_CACHE: Optional[Dict[str, object]] = None
_POSITIONS_CACHE: Optional[Dict[int, str]] = None


def load_heads() -> Dict[str, object]:
    """Load all available .lgb residual heads (lazy, cached).

    Returns {} if the artifact directory is missing or lightgbm is absent.
    Any individual missing/corrupt file is silently skipped.
    """
    global _HEAD_CACHE
    if _HEAD_CACHE is not None:
        return _HEAD_CACHE
    try:
        import lightgbm as lgb
    except ImportError:
        _HEAD_CACHE = {}
        return _HEAD_CACHE
    heads: Dict[str, object] = {}
    if os.path.isdir(HEAD_DIR):
        for stat in STATS:
            path = os.path.join(HEAD_DIR, f"{stat}.lgb")
            if os.path.exists(path):
                try:
                    heads[stat] = lgb.Booster(model_file=path)
                except Exception as exc:
                    print(f"  WARN residual_heads: could not load {path}: {exc}")
    _HEAD_CACHE = heads
    return _HEAD_CACHE


def _load_positions() -> Dict[int, str]:
    global _POSITIONS_CACHE
    if _POSITIONS_CACHE is not None:
        return _POSITIONS_CACHE
    try:
        from scripts.train_minute_trajectory import load_positions
        _POSITIONS_CACHE = load_positions() or {}
    except Exception:
        _POSITIONS_CACHE = {}
    return _POSITIONS_CACHE


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot flags matching probe logic."""
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def apply_residual_correction(
    snap: dict,
    projs: Dict[Tuple[int, str], float],
) -> Dict[Tuple[int, str], float]:
    """Apply per-(player, stat) residual head correction to projections.

    For each (pid, stat) at endQ3, if a head exists, adds the head's
    predicted residual to the BASELINE projection. Correction is clipped to
    [-cur_stat, 2 * projected] so the adjusted value stays non-negative and
    doesn't balloon more than 2x the incoming projection.

    Parameters
    ----------
    snap : dict
        Canonical snapshot dict (same shape as live_engine uses).
    projs : dict[(pid, stat) -> float]
        Current projected_final values keyed by (player_id int, stat str).
        Updated copy is returned; caller's dict is not mutated.

    Returns
    -------
    dict[(pid, stat) -> float]
        Updated projections. Stats without a head artifact are unchanged.
    """
    heads = load_heads()
    if not heads:
        return projs

    try:
        import numpy as np
    except ImportError:
        return projs

    positions = _load_positions()

    home_pts = float(snap.get("home_score", 0) or 0)
    away_pts = float(snap.get("away_score", 0) or 0)
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", "") or "")
    away_team = str(snap.get("away_team", "") or "")

    out = dict(projs)

    for player in snap.get("players") or []:
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError, KeyError):
            continue

        team = str(player.get("team", "") or "")
        if team == home_team:
            raw_margin = home_pts - away_pts
        elif team == away_team:
            raw_margin = away_pts - home_pts
        else:
            raw_margin = 0.0

        pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

        feat = np.array([[
            float(player.get("pts", 0) or 0),
            float(player.get("reb", 0) or 0),
            float(player.get("ast", 0) or 0),
            float(player.get("fg3m", 0) or 0),
            float(player.get("stl", 0) or 0),
            float(player.get("blk", 0) or 0),
            float(player.get("tov", 0) or 0),
            float(player.get("pf", 0) or 0),
            float(player.get("min", 0) or 0),
            margin,
            float(raw_margin > 0),
            pos_c,
            pos_f,
            pos_g,
        ]], dtype=np.float32)

        for stat in STATS:
            head = heads.get(stat)
            if head is None:
                continue
            key = (pid, stat)
            projected = out.get(key)
            if projected is None:
                continue

            residual_pred = float(head.predict(feat)[0])
            cur_stat = float(player.get(stat, 0) or 0)

            # Clip: adjusted must stay >= 0 and <= 2x projected.
            lo = -cur_stat
            hi = max(0.0, 2.0 * projected)
            adjusted = float(projected) + residual_pred
            adjusted = max(float(projected) + lo, min(float(projected) + hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out
