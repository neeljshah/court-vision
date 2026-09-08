"""Sealed 200-case construct for G344 shadow-possession exact-match checks."""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.ball_shadow_possession import shadow_states

SEED = 3440908
KINDS = ("valid", "cut", "missing", "duplicate", "motion_disagreement")


def _player(frame: int, x: float, y: float) -> dict[str, str]:
    return {"frame": str(frame), "player_id": "p1", "bbox_x1": str(x - 8),
            "bbox_y1": str(y - 16), "bbox_x2": str(x + 8), "bbox_y2": str(y)}


def _ball(frame: int, x: float, y: float, detected: str = "1") -> dict[str, str]:
    return {"frame": str(frame), "timestamp": str(50000 + frame * 31),
            "ball_x2d": str(x), "ball_y2d": str(y), "detected": detected,
            "confidence": "0.90"}


def case(index: int, seed: int = SEED) -> tuple[str, list[dict[str, str]], list[dict[str, str]], set[int], str, str]:
    """Return one known-truth construct, with intentionally offset ball timestamps."""
    rng, kind = random.Random(seed + index), KINDS[index % len(KINDS)]
    base_x, base_y = rng.randint(80, 500), rng.randint(80, 400)
    players = [_player(frame, base_x + frame, base_y) for frame in range(4)]
    balls = [_ball(frame, base_x + frame, base_y) for frame in range(4)]
    cuts: set[int] = set()
    expected_state, expected_owner = "OBSERVED_VALID", "p1"
    if kind == "cut":
        cuts = {2}
        expected_owner = ""
    elif kind == "missing":
        balls.pop()
        expected_state, expected_owner = "ABSENT", ""
    elif kind == "duplicate":
        balls.append(_ball(3, base_x + 4, base_y))
        expected_state, expected_owner = "AMBIGUOUS", ""
    elif kind == "motion_disagreement":
        players = [_player(frame, base_x - frame, base_y) for frame in range(4)]
        expected_owner = ""
    return kind, players, balls, cuts, expected_state, expected_owner


def evaluate(seed: int = SEED) -> list[dict[str, Any]]:
    """Evaluate all 200 enumerated cases and retain actual and known-truth fields."""
    rows = []
    for index in range(200):
        kind, players, balls, cuts, expected_state, expected_owner = case(index, seed)
        actual = shadow_states(players, balls, 0, 3, 720, cuts)[-1]
        passed = actual["state"] == expected_state and actual["owner_id"] == expected_owner
        rows.append({"case_id": f"{index:06d}", "kind": kind, "expected_state": expected_state,
                     "actual_state": actual["state"], "expected_owner_id": expected_owner,
                     "actual_owner_id": actual["owner_id"], "pass": f"{int(passed):06d}"})
    return rows


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    rows = evaluate(args.seed)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    _main()
