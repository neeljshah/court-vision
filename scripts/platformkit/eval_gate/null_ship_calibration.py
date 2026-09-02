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
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS
from scripts.platformkit.eval_gate.golden_loader import load_golden
from scripts.platformkit.eval_gate.run_gate import gate_exit_code, run_gate_in_process

DEFAULT_CANDIDATES = 200
MAX_WALL_SECONDS = 45.0 * 60.0
_CLIP_LO = 0.02
_CLIP_HI = 0.98
_REPORT = Path(__file__).with_name("post_hardening_revalidation_report.txt")


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
        # S40b / RT-6: `passed` never consulted `provisional`, so a run that hit the
        # wall-time cap after ONE candidate reported PASS (measured: candidates=1,
        # ships=0, provisional=True -> passed True, main() exit 0). A provisional run
        # has not measured the ship rate; it can only be UNDECIDED, never PASS.
        # The 2*alpha ceiling itself is a pre-registered bar and does NOT move.
        return (not self.provisional) and self.ship_rate <= self.threshold


@dataclass(frozen=True)
class ExploitRegressionResult:
    """One forbidden predictor read exercised through the real gate."""

    name: str
    outcome: str
    ships: int

    @property
    def blocked(self) -> bool:
        return self.ships == 0


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


def _label_echo_predictor(_train: List[dict], test: dict, select_inside: bool) -> float:
    """Adversarially attempt to return the held-out realized outcome."""
    assert select_inside is True, "label echo requires inside-window selection"
    return float(test["outcome"])


def _market_echo_predictor(_train: List[dict], test: dict, select_inside: bool) -> float:
    """Adversarially attempt to return the held-out devigged close probability."""
    assert select_inside is True, "market echo requires inside-window selection"
    return float(test["devig_close_prob"])


def run_exploit_regressions() -> Tuple[ExploitRegressionResult, ...]:
    """Verify forbidden label and market echoes are redacted and cannot ship."""
    checks = (
        ("LABEL-ECHO", _label_echo_predictor),
        ("MARKET-ECHO", _market_echo_predictor),
    )
    results = []
    for name, predictor in checks:
        try:
            rows = run_gate_in_process(predictor)
        except (KeyError, AssertionError) as exc:
            outcome = "LEAK_ERROR" if "LEAK" in str(exc) else "REDACTED"
            results.append(ExploitRegressionResult(name, outcome, 0))
            continue
        results.append(ExploitRegressionResult(
            name,
            "NON_SHIP" if not candidate_ships(rows) else "UNEXPECTED_SHIP",
            int(candidate_ships(rows)),
        ))
    return tuple(results)


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


def render_report(result: CalibrationResult,
                  exploits: Sequence[ExploitRegressionResult] = ()) -> str:
    """Render the pre-registered decision in ASCII only."""
    scope = "PROVISIONAL" if result.provisional else "FINAL"
    # A provisional run is UNDECIDED, not BROKEN: it stopped early, it did not misbehave.
    verdict = "UNDECIDED" if result.provisional else ("PASS" if result.passed else "BROKEN")
    lines = [
        "NULL-SHIP CALIBRATION OF THE CORRECTED GATE",
        "status=%s candidates=%d ships=%d" % (scope, result.candidates, result.ships),
        "nominal_alpha=%.6f observed_null_ship_rate=%.6f ceiling=%.6f" % (
            result.nominal_alpha, result.ship_rate, result.threshold),
        "wall_seconds=%.3f verdict=%s" % (result.wall_seconds, verdict),
    ]
    if result.provisional:
        lines.append("PROVISIONAL: 200 sequential runs exceeded the 45-minute wall-time cap.")
    if not result.passed and not result.provisional:
        lines.append("BROKEN: every SHIP since the last passing calibration is suspended.")
    for exploit in exploits:
        lines.append("exploit=%s outcome=%s ships=%d verdict=%s" % (
            exploit.name, exploit.outcome, exploit.ships,
            "BLOCKED" if exploit.blocked else "BROKEN"))
    return "\n".join(lines)


def write_revalidation_report(result: CalibrationResult,
                              exploits: Sequence[ExploitRegressionResult],
                              path: Path = _REPORT) -> str:
    """Persist the ASCII calibration evidence beside the reproducible gate code."""
    text = render_report(result, exploits) + "\n"
    path.write_text(text, encoding="ascii")
    return text


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sequential corrected-gate null calibration")
    parser.add_argument("--n", type=int, default=DEFAULT_CANDIDATES)
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(argv)
    result = run_calibration(args.n, args.seed)
    exploits = run_exploit_regressions()
    text = render_report(result, exploits)
    if args.write_report:
        write_revalidation_report(result, exploits)
    print(text)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
