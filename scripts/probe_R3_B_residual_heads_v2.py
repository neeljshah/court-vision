"""scripts/probe_R3_B_residual_heads_v2.py -- R3-B probe (loop 5).

Treatment: BASELINE (live_engine_post_110, which includes R2_F heads)
PLUS v2 residual correction learned on the post-R2_F residual.

v2 heads live in data/models/residual_heads_v2/{stat}.lgb.
If a stat's v2 model does not exist (did not pass WF gate), treatment falls
back to BASELINE for that stat.

Usage (probe run):
    python scripts/probe_R3_B_residual_heads_v2.py
    python scripts/probe_R3_B_residual_heads_v2.py --max-games 200

Smoke test:
    python -c "from scripts.probe_R3_B_residual_heads_v2 import treatment; print('ok')"
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

from scripts.improve_loop.scaffold import BASELINE, run_endq3_probe  # noqa: E402
from scripts.train_residual_heads_v2 import (  # noqa: E402
    BASE_FEATURE_NAMES,
    STATS,
    _feature_names_for_stat,
    _l5_features,
    _pos_flags,
    load_player_gamelogs,
    load_rest_travel,
)

V2_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v2")

# Module-level caches: loaded once on first treatment() call.
_V2_MODELS: Optional[Dict[str, object]] = None
_GAMELOGS: Optional[Dict] = None
_REST_LOOKUP: Optional[Dict] = None


def _load_models() -> Dict[str, object]:
    """Load all available v2 LGB models from disk."""
    import lightgbm as lgb
    models: Dict[str, object] = {}
    for stat in STATS:
        path = os.path.join(V2_MODEL_DIR, f"{stat}.lgb")
        if os.path.exists(path):
            bst = lgb.Booster(model_file=path)
            models[stat] = bst
    return models


def _ensure_loaded() -> None:
    global _V2_MODELS, _GAMELOGS, _REST_LOOKUP
    if _V2_MODELS is None:
        _V2_MODELS = _load_models()
        _GAMELOGS = load_player_gamelogs()
        _REST_LOOKUP = load_rest_travel()
        loaded = list(_V2_MODELS.keys())
        print(f"  [R3-B] v2 models loaded: {loaded or 'none'}")


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """Compute endQ3 projections: BASELINE + v2 head correction.

    For stats without a v2 model, returns BASELINE value unchanged.
    """
    import numpy as np

    _ensure_loaded()
    assert _V2_MODELS is not None
    assert _GAMELOGS is not None
    assert _REST_LOOKUP is not None

    base = BASELINE(snap)
    if not _V2_MODELS:
        return base

    out: Dict[Tuple[int, str], float] = dict(base)

    home_pts = float(snap.get("home_score", 0))
    away_pts = float(snap.get("away_score", 0))
    margin = abs(home_pts - away_pts)
    home_team = str(snap.get("home_team", ""))
    away_team = str(snap.get("away_team", ""))
    gid = str(snap.get("game_id", ""))

    # Rest lookup per team
    team_rest: Dict[str, Tuple[float, float]] = {}
    for team in (home_team, away_team):
        team_rest[team] = _REST_LOOKUP.get((gid, team), (0.0, 2.0))

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

        # We don't have position info in snap natively; default all zeros
        # (positions are a minor feature; no import of load_positions here)
        pos_c, pos_f, pos_g = _pos_flags("")

        base_feat = [
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

        b2b_val, rest_val = team_rest.get(team, (0.0, 2.0))

        for stat, model in _V2_MODELS.items():
            bval = base.get((pid, stat))
            if bval is None:
                continue
            l5_mean, l5_std = _l5_features(pid, stat, None, _GAMELOGS)
            feat = base_feat + [l5_mean, l5_std, b2b_val, rest_val]
            correction = float(model.predict(
                np.array([feat], dtype=np.float32),
                num_iteration=model.best_iteration
                if hasattr(model, "best_iteration") else -1,
            )[0])
            out[(pid, stat)] = bval + correction

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Run R3-B v2 residual heads probe.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    run_endq3_probe(
        name="R3_B_residual_heads_v2",
        treatment=treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
