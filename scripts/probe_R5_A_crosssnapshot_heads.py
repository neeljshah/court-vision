"""scripts/probe_R5_A_crosssnapshot_heads.py -- R5-A probe: cross-snapshot residual heads.

Loads the trained .lgb heads from data/models/residual_heads_v3_crosssnapshot/
and evaluates them via the scaffold's run_endq3_probe.

Treatment: BASELINE(snap) + residual_head.predict(22-feature vector)
  clipped to [-cur_stat, 2 * projected].

Module-level caches _P1_CACHE / _P2_CACHE hold {game_id: {pid: {stat: val}}}
to avoid re-building Q1/Q2 snapshots per player.

Usage:
    python scripts/probe_R5_A_crosssnapshot_heads.py
    python scripts/probe_R5_A_crosssnapshot_heads.py --max-games 300
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

import retro_inplay_mae as v1  # noqa: E402
from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v3_crosssnapshot")

# ---------------------------------------------------------------------------
# Module-level snapshot caches keyed by game_id
# ---------------------------------------------------------------------------
_P1_CACHE: Dict[str, Dict[int, Dict[str, float]]] = {}
_P2_CACHE: Dict[str, Dict[int, Dict[str, float]]] = {}

# Loaded LGB boosters keyed by stat (None if file absent)
_HEADS: Dict[str, object] = {}


def _load_heads() -> None:
    """Load all available .lgb heads once at import time."""
    try:
        import lightgbm as lgb
    except ImportError:
        return
    for stat in STATS:
        path = os.path.join(MODEL_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            _HEADS[stat] = lgb.Booster(model_file=path)


_load_heads()

_QSTATS_DF = v1.load_quarter_stats()


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot from NBA position string."""
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def _get_p1(gid: str, qstats_df=None) -> Dict[int, Dict[str, float]]:
    """Return cached endQ1 {pid: {stat: val}} for game_id."""
    if gid not in _P1_CACHE:
        snap = v1.build_snapshot(gid, "endQ1", qstats_df)
        result: Dict[int, Dict[str, float]] = {}
        if snap is not None:
            for player in snap.get("players", []):
                try:
                    pid = int(player["player_id"])
                except (TypeError, ValueError):
                    continue
                result[pid] = {s: float(player.get(s, 0)) for s in STATS}
        _P1_CACHE[gid] = result
    return _P1_CACHE[gid]


def _get_p2(gid: str, qstats_df=None) -> Dict[int, Dict[str, float]]:
    """Return cached endQ2 {pid: {stat: val}} for game_id."""
    if gid not in _P2_CACHE:
        snap = v1.build_snapshot(gid, "endQ2", qstats_df)
        result: Dict[int, Dict[str, float]] = {}
        if snap is not None:
            for player in snap.get("players", []):
                try:
                    pid = int(player["player_id"])
                except (TypeError, ValueError):
                    continue
                result[pid] = {s: float(player.get(s, 0)) for s in STATS}
        _P2_CACHE[gid] = result
    return _P2_CACHE[gid]


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """Build BASELINE projections then add residual head corrections.

    For each player at endQ3:
      1. Get BASELINE projection (post-R2_F live_engine).
      2. Build 22-feature vector (base14 + q3only7 + hot/cold1).
      3. For each stat with a loaded head: proj += head.predict(feat).
      4. Clip: [-cur_stat, 2 * projected].
    """
    import numpy as np

    base_proj = BASELINE(snap)

    gid = snap.get("game_id", "")
    p1 = _get_p1(gid, _QSTATS_DF)
    p2 = _get_p2(gid, _QSTATS_DF)

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)

    result: Dict[Tuple[int, str], float] = dict(base_proj)

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        if not any((pid, s) in base_proj for s in STATS):
            continue

        team = str(player.get("team", ""))
        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))
        if team == home_team:
            raw_margin = home_pts - away_pts
        elif team == away_team:
            raw_margin = away_pts - home_pts
        else:
            raw_margin = 0.0

        pos_c, pos_f, pos_g = _pos_flags(player.get("position", ""))

        cur = {s: float(player.get(s, 0)) for s in STATS}

        # Q3-only deltas
        p2_pid = p2.get(pid, {})
        q3only = {s: cur[s] - p2_pid.get(s, 0.0) for s in STATS}

        # Hot/cold
        p1_pid = p1.get(pid, {})
        q1_q3_diff_pts = p1_pid.get("pts", 0.0) - q3only["pts"]

        feat = np.array([[
            # Base 14
            cur["pts"], cur["reb"], cur["ast"], cur["fg3m"],
            cur["stl"], cur["blk"], cur["tov"],
            float(player.get("pf", 0)),
            float(player.get("min", 0)),
            margin,
            float(raw_margin > 0),
            pos_c, pos_f, pos_g,
            # Q3-only deltas 7
            q3only["pts"], q3only["reb"], q3only["ast"], q3only["fg3m"],
            q3only["stl"], q3only["blk"], q3only["tov"],
            # Hot/cold 1
            q1_q3_diff_pts,
        ]], dtype=np.float32)

        for stat in STATS:
            head = _HEADS.get(stat)
            if head is None:
                continue
            base_val = base_proj.get((pid, stat))
            if base_val is None:
                continue
            delta = float(head.predict(feat)[0])
            projected = base_val + delta
            # Clip: can't go below -cur_stat (no negative finals), max 2x projected
            cur_stat = cur[stat]
            projected = max(-cur_stat, min(projected, 2.0 * base_val if base_val > 0 else projected))
            result[(pid, stat)] = projected

    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe R5-A cross-snapshot residual heads.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    loaded_stats = list(_HEADS.keys())
    if not loaded_stats:
        print("  WARNING: no heads found in", MODEL_DIR)
        print("  Run train_residual_heads_v3_crosssnapshot.py first.")
    else:
        print(f"  Loaded heads for: {loaded_stats}")

    run_endq3_probe(
        name="R5_A_crosssnapshot_heads",
        treatment=treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )


if __name__ == "__main__":
    main()
