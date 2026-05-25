"""scripts/probe_R7_B_pregame_anchor_heads.py -- R7-B probe.

Applies v7_pregame_anchor residual heads on top of the live_engine
BASELINE at endQ3 using 15 features (14 base + 1 stat-specific pregame OOF
anchor).

Heads that were not saved in training (gate failed) are silently skipped —
treatment falls back to BASELINE for that stat.

Usage:
    python scripts/probe_R7_B_pregame_anchor_heads.py
    python scripts/probe_R7_B_pregame_anchor_heads.py --max-games 200
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

from scripts.improve_loop.scaffold import BASELINE, run_endq3_probe  # noqa: E402
import retro_inplay_mae as v1  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models",
                         "residual_heads_v7_pregame_anchor")

_CLIP = {
    "pts": (0.0, 80.0),
    "reb": (0.0, 30.0),
    "ast": (0.0, 25.0),
    "fg3m": (0.0, 15.0),
    "stl": (0.0, 10.0),
    "blk": (0.0, 10.0),
    "tov": (0.0, 15.0),
}

# Module-level caches
_MODELS: Optional[Dict[str, object]] = None
_OOF_LOOKUP: Optional[Dict[str, Dict[Tuple[int, str], float]]] = None
_POSITIONS: Optional[Dict[int, str]] = None
_DATE_INDEX: Optional[Dict[str, str]] = None
_QSTATS_DF = None


def _get_models() -> Dict[str, object]:
    global _MODELS
    if _MODELS is None:
        import lightgbm as lgb
        _MODELS = {}
        for stat in STATS:
            p = os.path.join(MODEL_DIR, f"{stat}.lgb")
            if os.path.exists(p):
                _MODELS[stat] = lgb.Booster(model_file=p)
    return _MODELS


def _get_oof_lookup() -> Dict[str, Dict[Tuple[int, str], float]]:
    global _OOF_LOOKUP
    if _OOF_LOOKUP is None:
        from scripts.train_residual_heads_v7_pregame_anchor import load_oof_lookup
        _OOF_LOOKUP = load_oof_lookup()
    return _OOF_LOOKUP


def _get_positions() -> Dict[int, str]:
    global _POSITIONS
    if _POSITIONS is None:
        from scripts.train_minute_trajectory import load_positions
        _POSITIONS = load_positions()
    return _POSITIONS


def _get_qstats():
    global _QSTATS_DF
    if _QSTATS_DF is None:
        _QSTATS_DF = v1.load_quarter_stats()
    return _QSTATS_DF


def _get_date_index() -> Dict[str, str]:
    global _DATE_INDEX
    if _DATE_INDEX is None:
        from train_minute_trajectory import (
            load_player_gamelog_minutes, find_game_date_for_game)
        qdf = _get_qstats()
        pid_log = load_player_gamelog_minutes()
        _DATE_INDEX = {}
        for gid in qdf["game_id"].unique():
            d = find_game_date_for_game(str(gid), qdf, pid_log)
            if d:
                _DATE_INDEX[str(gid)] = d
    return _DATE_INDEX


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def _base_feature_vector(player: dict, snap: dict) -> list:
    """Build the 14-base-feature vector (no anchor)."""
    try:
        pid = int(player["player_id"])
    except (TypeError, ValueError):
        return []

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)

    team = str(player.get("team", ""))
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))
    if team == home_team:
        raw_margin = home_pts - away_pts
    elif team == away_team:
        raw_margin = away_pts - home_pts
    else:
        raw_margin = 0.0

    positions = _get_positions()
    pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

    return [
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
        float(pos_c),
        float(pos_f),
        float(pos_g),
    ]


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """R7-B treatment: BASELINE + residual head corrections (per-stat anchor).

    For each (pid, stat) where a head exists AND an OOF anchor is found,
    apply the head's predicted correction. Otherwise leave BASELINE.
    """
    import numpy as np

    models = _get_models()
    if not models:
        return BASELINE(snap)

    baseline_proj = BASELINE(snap)
    oof_lookup = _get_oof_lookup()

    game_date: Optional[str] = snap.get("game_date")
    if not game_date:
        game_id = str(snap.get("game_id", ""))
        if game_id:
            game_date = _get_date_index().get(game_id)

    out = dict(baseline_proj)

    if not game_date:
        return out  # cannot anchor without a date

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        base_feat = _base_feature_vector(player, snap)
        if not base_feat:
            continue

        for stat, model in models.items():
            key = (pid, stat)
            if key not in out:
                continue
            anchor = oof_lookup[stat].get((pid, game_date))
            if anchor is None:
                continue  # leave baseline untouched for this (pid, stat)
            X = np.array([base_feat + [float(anchor)]], dtype=np.float32)
            correction = float(model.predict(X)[0])
            raw = out[key] + correction
            lo, hi = _CLIP[stat]
            out[key] = float(max(lo, min(hi, raw)))

    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="R7-B probe: stat-specific pregame anchor residual heads.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    run_endq3_probe(
        name="R7_B_pregame_anchor_heads",
        treatment=treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
