"""scripts/probe_R2_B_foul_out_cliff.py

Probe R2_B: pf=5 foul-out cliff at endQ3.
Players with 5 personal fouls face a non-linear coaching decision:
  blowout  (margin > 15) -> bench them (factor 0.30)
  cautious (8-15)        -> play cautiously (factor 0.55)
  close    (margin < 8)  -> still plays, conservative (factor 0.85)

Applies a piece-wise multiplicative dampener to projected_remaining for
qualifying players (pf==5 AND min > 20), leaving all others at baseline.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts.improve_loop.scaffold import run_endq3_probe, BASELINE  # noqa: E402

_FACTORS = {"blowout": 0.30, "cautious": 0.55, "close": 0.85}


def _bucket(margin: float) -> str:
    if margin > 15:
        return "blowout"
    if margin >= 8:
        return "cautious"
    return "close"


def treatment(snap: dict) -> Dict[Tuple[int, str], float]:
    """EndQ3 projection with foul-out cliff dampening for pf=5 players."""
    home = snap.get("home_score", 0)
    away = snap.get("away_score", 0)
    margin = abs(home - away)
    bucket = _bucket(margin)
    factor = _FACTORS[bucket]

    base = BASELINE(snap)

    # Build pid -> player record lookup
    pid_map: Dict[int, dict] = {}
    for player in snap.get("players", []):
        try:
            pid = int(player.get("player_id") or player.get("pid", 0))
        except (TypeError, ValueError):
            continue
        pid_map[pid] = player

    out: Dict[Tuple[int, str], float] = {}
    for (pid, stat), bval in base.items():
        player = pid_map.get(pid)
        if player is None:
            out[(pid, stat)] = bval
            continue

        pf = player.get("pf", 0) or 0
        minutes = player.get("min", 0) or player.get("minutes", 0) or 0

        if pf == 5 and minutes > 20:
            # Current accumulated value for this stat
            cur = float(player.get(stat, 0) or 0)
            remaining = bval - cur
            out[(pid, stat)] = cur + remaining * factor
        else:
            out[(pid, stat)] = bval

    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe R2_B: foul-out cliff dampener at endQ3"
    )
    parser.add_argument(
        "--max-games", type=int, default=None,
        help="Cap number of games for quick smoke test"
    )
    args = parser.parse_args()

    run_endq3_probe(
        "R2_B_foul_out_cliff",
        treatment,
        baseline=BASELINE,
        max_games=args.max_games,
    )


if __name__ == "__main__":
    main()
