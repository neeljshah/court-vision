"""scripts/probe_R5_B_pregame_proxy_heads.py -- R5-B probe.

Applies residual_heads_v4_pregameproxy heads on top of the live_engine
BASELINE at endQ3 using 21 features (14 base + 7 l20 pregame proxy).

Usage:
    python scripts/probe_R5_B_pregame_proxy_heads.py
    python scripts/probe_R5_B_pregame_proxy_heads.py --max-games 200

Or import:
    from scripts.probe_R5_B_pregame_proxy_heads import treatment
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
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v4_pregameproxy")

# -- clip bounds per stat (same as R2-F / live_engine) --
_CLIP = {
    "pts": (0.0, 80.0),
    "reb": (0.0, 30.0),
    "ast": (0.0, 25.0),
    "fg3m": (0.0, 15.0),
    "stl": (0.0, 10.0),
    "blk": (0.0, 10.0),
    "tov": (0.0, 15.0),
}

# ── Module-level caches (loaded once) ──────────────────────────────────────
_MODELS: Optional[Dict[str, object]] = None
_GAMELOG_INDEX: Optional[Dict] = None
_PID_LOG_INDEX: Optional[Dict] = None
_QSTATS_DF = None  # populated lazily by _get_qstats
_DATE_INDEX: Optional[Dict[str, str]] = None


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


def _get_gamelog_index():
    global _GAMELOG_INDEX
    if _GAMELOG_INDEX is None:
        from scripts.train_residual_heads_v4_pregameproxy import load_gamelog_stat_index
        _GAMELOG_INDEX = load_gamelog_stat_index()
    return _GAMELOG_INDEX


def _get_pid_log_index():
    global _PID_LOG_INDEX
    if _PID_LOG_INDEX is None:
        from train_minute_trajectory import load_player_gamelog_minutes
        _PID_LOG_INDEX = load_player_gamelog_minutes()
    return _PID_LOG_INDEX


def _get_qstats():
    global _QSTATS_DF
    if _QSTATS_DF is None:
        _QSTATS_DF = v1.load_quarter_stats()
    return _QSTATS_DF


def _get_date_index() -> Dict[str, str]:
    """Build game_id -> ISO date mapping lazily."""
    global _DATE_INDEX
    if _DATE_INDEX is None:
        from train_minute_trajectory import find_game_date_for_game
        qdf = _get_qstats()
        pid_log = _get_pid_log_index()
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


def _build_feature_vector(player: dict, snap: dict, game_date: Optional[str],
                           positions: dict) -> list:
    """Build 21-float feature vector for one player from an endQ3 snap."""
    from scripts.train_residual_heads_v4_pregameproxy import l20_means

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

    pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

    gamelog_index = _get_gamelog_index()
    proxy = l20_means(pid, game_date, gamelog_index)

    feat = [
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
        proxy["pts"],
        proxy["reb"],
        proxy["ast"],
        proxy["fg3m"],
        proxy["stl"],
        proxy["blk"],
        proxy["tov"],
    ]
    return feat


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """R5-B treatment: BASELINE + residual head corrections.

    Builds 21-feature vectors, applies each v4_pregameproxy head,
    adds correction to BASELINE projection, clips to valid range.
    """
    import numpy as np

    models = _get_models()
    if not models:
        # No heads available: fall back to BASELINE
        return BASELINE(snap)

    baseline_proj = BASELINE(snap)

    # Load positions lazily
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()

    # Resolve game_date: prefer snap field, else derive from game_id
    game_date: Optional[str] = snap.get("game_date")
    if not game_date:
        game_id = str(snap.get("game_id", ""))
        if game_id:
            date_index = _get_date_index()
            game_date = date_index.get(game_id)

    out = dict(baseline_proj)  # copy baseline

    for player in snap.get("players", []):
        try:
            pid = int(player["player_id"])
        except (TypeError, ValueError):
            continue

        feat = _build_feature_vector(player, snap, game_date, positions)
        if not feat:
            continue

        X = np.array([feat], dtype=np.float32)

        for stat, model in models.items():
            key = (pid, stat)
            if key not in out:
                continue
            correction = float(model.predict(X)[0])
            raw = out[key] + correction
            lo, hi = _CLIP[stat]
            out[key] = float(max(lo, min(hi, raw)))

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="R5-B probe: pregame proxy heads.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    run_endq3_probe(
        name="R5_B_pregame_proxy_heads",
        treatment=treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
