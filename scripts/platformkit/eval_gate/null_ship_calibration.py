"""Sequential pure-noise calibration for the corrected eval gate.

Each candidate assigns one outcome-blind probability to every golden-fixture game.
The original fixture states, including their per-game clustering and corpus sizes,
then pass through ``run_gate_in_process`` unchanged.  A candidate ships only when
the hard-stop gate passes and at least one corrected corpus row is ship-eligible.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS
from scripts.platformkit.eval_gate.golden_loader import load_golden
from scripts.platformkit.eval_gate.run_gate import gate_exit_code, run_gate_in_process

DEFAULT_CANDIDATES = 200
MAX_WALL_SECONDS = 45.0 * 60.0
_CLIP_LO = 0.02
_CLIP_HI = 0.98


@dataclass(frozen=True)
class CalibrationResult:
    candidates: int
    ships: int
    wall_seconds: float
    nominal_alpha: float
    provisional: bool

    @property
    def ship_rate(self) -> float:
        return self.ships / self.candidates if self.candidates else 0.0

    @property
    def threshold(self) -> float:
        return 2.0 * self.nominal_alpha

    @property
    def passed(self) -> bool:
        return self.ship_rate <= self.threshold


def _game_keys(states: Sequence[dict]) -> List[Tuple[str, str]]:
    """Return fixture game keys once, without inspecting labels or close prices."""
    return sorted({(str(s["season"]), str(s["game_id"])) for s in states})


def pure_noise_predictor(states: Sequence[dict], seed: int):
    """Make one independent, outcome-blind probability for every fixture game."""
    rng = np.random.default_rng(seed)
    probabilities: Dict[Tuple[str, str], float] = {
        key: float(rng.uniform(_CLIP_LO, _CLIP_HI)) for key in _game_keys(states)
    }

    def predict(_train: List[dict], test: dict, select_inside: bool) -> float:
        assert select_inside is True, "null predictor requires inside-window selection"
        return probabilities[(str(test["season"]), str(test["game_id"]))]

    return predict, probabilities


def candidate_ships(rows: Sequence[dict]) -> bool:
    """Apply the real gate's hard stop plus its corrected ship eligibility."""
    return gate_exit_code(list(rows)) == 0 and any(
        bool(row.get("ship_eligible")) for row in rows
    )


def run_calibration(n: int = DEFAULT_CANDIDATES, seed: int = 20260901,
                    max_wall_seconds: float = MAX_WALL_SECONDS) -> CalibrationResult:
    """Run candidates serially; stop early only after the registered wall-time cap."""
    if n < 1:
        raise ValueError("n must be positive")
    states = load_golden()
    started = time.perf_counter()
    ships = 0
    completed = 0
    provisional = False
    for candidate in range(n):
        predict, _ = pure_noise_predictor(states, seed + candidate)
        # Do not inject ``states`` here: the real gate loads and season-filters
        # each corpus slot itself. Passing the combined fixture would make both
        # rows score the wrong corpus dimensions.
        rows = run_gate_in_process(predict)
        ships += int(candidate_ships(rows))
        completed += 1
        if completed < n and time.perf_counter() - started >= max_wall_seconds:
            provisional = True
            break
    return CalibrationResult(completed, ships, time.perf_counter() - started,
                             DEFAULT_EPS, provisional)


def render_report(result: CalibrationResult) -> str:
    """Render the pre-registered decision in ASCII only."""
    scope = "PROVISIONAL" if result.provisional else "FINAL"
    verdict = "PASS" if result.passed else "BROKEN"
    lines = [
        "NULL-SHIP CALIBRATION OF THE CORRECTED GATE",
        "status=%s candidates=%d ships=%d" % (scope, result.candidates, result.ships),
        "nominal_alpha=%.6f observed_null_ship_rate=%.6f ceiling=%.6f" % (
            result.nominal_alpha, result.ship_rate, result.threshold),
        "wall_seconds=%.3f verdict=%s" % (result.wall_seconds, verdict),
    ]
    if result.provisional:
        lines.append("PROVISIONAL: 200 sequential runs exceeded the 45-minute wall-time cap.")
    if not result.passed:
        lines.append("BROKEN: every SHIP since the last passing calibration is suspended.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sequential corrected-gate null calibration")
    parser.add_argument("--n", type=int, default=DEFAULT_CANDIDATES)
    parser.add_argument("--seed", type=int, default=20260901)
    args = parser.parse_args(argv)
    result = run_calibration(args.n, args.seed)
    print(render_report(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
