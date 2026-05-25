"""scripts/probe_R3_G_context_aware_heads.py -- R3-G probe: context-aware residual heads.

Compares context-aware (close/blow) residual heads (v2) against the
single-context R2_F residual heads (v1) that are already wired into
live_engine.project_from_snapshot.

Strategy: swap v1 correction for v2 correction on top of the live_engine
baseline (which already includes R2_F).

    out[(pid, stat)] = BASELINE(snap) - v1_correction + v2_correction

Where:
  BASELINE = live_engine (includes R2_F single-context heads)
  v1_correction = per-(pid, stat) residual predicted by R2_F single heads
  v2_correction = per-(pid, stat) residual predicted by context-aware heads
                  (bucket dispatched by |score_margin_abs| < 12)

This directly measures whether context stratification beats a flat head.

Usage:
    python scripts/probe_R3_G_context_aware_heads.py
    python scripts/probe_R3_G_context_aware_heads.py --max-games 200

If run as __main__, calls run_endq3_probe and writes
scripts/_results/improve_R3_G_context_aware_heads.{md,json}.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import numpy as np  # noqa: E402

from scripts.improve_loop.scaffold import BASELINE, run_endq3_probe  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
CLOSE_THRESHOLD = 12.0

# Artifact directories
_V2_DIR_CLOSE = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_close")
_V2_DIR_BLOW = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_blow")
_V1_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")

# Module-level lazy caches
_v1_heads: Optional[Dict[str, object]] = None
_v2_close_heads: Optional[Dict[str, object]] = None
_v2_blow_heads: Optional[Dict[str, object]] = None
_positions_cache: Optional[Dict[int, str]] = None


def _load_lgb_dir(dirpath: str) -> Dict[str, object]:
    """Load all {stat}.lgb files from a directory into a dict."""
    try:
        import lightgbm as lgb
    except ImportError:
        return {}
    heads: Dict[str, object] = {}
    if not os.path.isdir(dirpath):
        return heads
    for stat in STATS:
        path = os.path.join(dirpath, f"{stat}.lgb")
        if os.path.exists(path):
            try:
                heads[stat] = lgb.Booster(model_file=path)
            except Exception as exc:
                print(f"  WARN: could not load {path}: {exc}")
    return heads


def _get_v1_heads() -> Dict[str, object]:
    global _v1_heads
    if _v1_heads is None:
        _v1_heads = _load_lgb_dir(_V1_DIR)
    return _v1_heads


def _get_v2_heads(bucket: str) -> Dict[str, object]:
    global _v2_close_heads, _v2_blow_heads
    if bucket == "close":
        if _v2_close_heads is None:
            _v2_close_heads = _load_lgb_dir(_V2_DIR_CLOSE)
        return _v2_close_heads
    else:
        if _v2_blow_heads is None:
            _v2_blow_heads = _load_lgb_dir(_V2_DIR_BLOW)
        return _v2_blow_heads


def _get_positions() -> Dict[int, str]:
    global _positions_cache
    if _positions_cache is None:
        try:
            from scripts.train_minute_trajectory import load_positions
            _positions_cache = load_positions() or {}
        except Exception:
            _positions_cache = {}
    return _positions_cache


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def _build_feat(player: dict, margin: float, raw_margin: float,
                pid: int) -> "np.ndarray":
    """Build the 14-feature vector used by both v1 and v2 heads."""
    positions = _get_positions()
    pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))
    return np.array([[
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
        pos_c, pos_f, pos_g,
    ]], dtype=np.float32)


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """R3-G treatment: swap R2_F single-context correction for v2 context-aware.

    Algorithm per (pid, stat):
        adjusted = BASELINE_proj - v1_residual_pred + v2_residual_pred

    Falls back gracefully:
    - If v2 head missing for a bucket/stat, keeps BASELINE (no swap).
    - If v1 head missing for a stat, v2 correction is applied additively
      (same as if v1_correction = 0).
    - Applies the same clip logic as residual_heads.apply_residual_correction.
    """
    # Step 1: get live_engine projection (already includes R2_F v1 correction)
    b = BASELINE(snap)

    v1_heads = _get_v1_heads()

    home_pts = float(snap.get("home_score", 0) or 0)
    away_pts = float(snap.get("away_score", 0) or 0)
    margin = abs(home_pts - away_pts)
    bucket = "close" if margin < CLOSE_THRESHOLD else "blow"
    v2_heads = _get_v2_heads(bucket)

    home_team = str(snap.get("home_team", "") or "")
    away_team = str(snap.get("away_team", "") or "")

    out = dict(b)

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

        feat = _build_feat(player, margin, raw_margin, pid)

        for stat in STATS:
            key = (pid, stat)
            projected_b = out.get(key)  # includes v1 correction
            if projected_b is None:
                continue

            v2_head = v2_heads.get(stat)
            if v2_head is None:
                # No v2 head for this bucket/stat — leave BASELINE unchanged
                continue

            v2_pred = float(v2_head.predict(feat)[0])

            # Compute v1 correction to subtract out
            v1_head = v1_heads.get(stat)
            v1_pred = float(v1_head.predict(feat)[0]) if v1_head is not None else 0.0

            # Reverse v1, apply v2: adjusted = projected_b - v1_pred + v2_pred
            # First recover the pre-v1-correction baseline (approximate):
            #   base_approx = projected_b - v1_pred (unclipped approx)
            # Then apply v2 correction on top of base_approx.
            base_approx = float(projected_b) - v1_pred
            cur_stat = float(player.get(stat, 0) or 0)

            # Clip same as residual_heads.apply_residual_correction
            lo = -cur_stat
            hi = max(0.0, 2.0 * base_approx)
            adjusted = base_approx + v2_pred
            adjusted = max(base_approx + lo, min(base_approx + hi, adjusted))
            adjusted = max(0.0, adjusted)

            out[key] = adjusted

    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Probe R3-G: context-aware residual heads vs R2_F baseline."
    )
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    run_endq3_probe(
        name="R3_G_context_aware_heads",
        treatment=treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
