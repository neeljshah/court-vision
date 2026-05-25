"""scripts/probe_R2_D_b2b_road_dampening.py

ANGLE: Road team Q4 dampening on B2B/B3B games.
The learned-Q4 model is rest-agnostic; road teams on the back-end of a B2B/B3B
compress rotations → remaining-minutes projections are too high.

Dampening factors:
  B2B  → FACTOR_B2B = 0.95   (5% haircut on road remaining)
  B3B  → FACTOR_B3B = 0.92   (8% haircut on road remaining)

Data source: data/rest_travel.parquet
  schema: [game_id, team_abbreviation, game_date, is_b2b, is_b3b, miles_traveled, altitude_ft]
  key: (game_id, team_abbreviation)
"""
from __future__ import annotations

import argparse
import os
import sys

# ---------------------------------------------------------------------------
# sys.path bootstrap — works whether invoked as a script or imported
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
for _p in (_PROJECT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd
from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE

# ---------------------------------------------------------------------------
# Load rest/travel table — graceful fallback if parquet is absent
# ---------------------------------------------------------------------------
_RT_PATH = os.path.join(_PROJECT, "data", "rest_travel.parquet")

try:
    _RT = (
        pd.read_parquet(_RT_PATH)
        .set_index(["game_id", "team_abbreviation"])[["is_b2b", "is_b3b"]]
    )
except FileNotFoundError:
    _RT = pd.DataFrame(
        columns=["is_b2b", "is_b3b"],
        index=pd.MultiIndex.from_tuples([], names=["game_id", "team_abbreviation"]),
    )
except Exception:
    _RT = pd.DataFrame(
        columns=["is_b2b", "is_b3b"],
        index=pd.MultiIndex.from_tuples([], names=["game_id", "team_abbreviation"]),
    )

FACTOR_B2B = 0.95
FACTOR_B3B = 0.92


def _road_b2b(snap: dict) -> tuple[float, float]:
    """Return (is_b2b, is_b3b) for the away team, or (0.0, 0.0) on miss."""
    away = snap.get("away_team")
    if not away:
        return 0.0, 0.0
    try:
        row = _RT.loc[(snap["game_id"], away)]
        return float(row["is_b2b"]), float(row["is_b3b"])
    except KeyError:
        return 0.0, 0.0


def treatment(snap: dict) -> dict:
    """Baseline projections with Q4 haircut applied to road team on B2B/B3B."""
    projs = dict(BASELINE(snap))
    b2b, b3b = _road_b2b(snap)
    if b2b < 0.5 and b3b < 0.5:
        return projs

    factor = FACTOR_B3B if b3b >= 0.5 else FACTOR_B2B
    away = snap.get("away_team")
    road_pids = {
        int(p["player_id"])
        for p in (snap.get("players") or [])
        if p.get("team") == away
    }
    pid_to_player = {int(p["player_id"]): p for p in (snap.get("players") or [])}

    for (pid, stat), final in list(projs.items()):
        if pid not in road_pids:
            continue
        p = pid_to_player.get(pid)
        if p is None:
            continue
        cur = float(p.get(stat, 0.0) or 0.0)
        remaining = final - cur
        if remaining <= 0:
            continue
        projs[(pid, stat)] = cur + remaining * factor

    return projs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Probe: road team Q4 dampening on B2B/B3B games"
    )
    ap.add_argument("--max-games", type=int, default=None,
                    help="Cap number of retro games (default: all)")
    args = ap.parse_args()

    run_endq3_probe(
        "R2_D_b2b_road_dampening",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )
