"""Rerunnable power assessment for the rung 8 (bullpen/pitch-count conditioning)
walk-forward measurement.

Standard paired-comparison power formula (per-GAME clustered, not per-tick -- ticks
within a game are highly correlated, so the effective sample size for a game-clustered
CI is n_games, per the domain's leak-free / no-same-game-leakage discipline):

    n_required = (z_(a/2) + z_b)^2 * sigma_diff^2 / delta^2

where delta is the target Brier improvement (candidate re-price vs unconditioned
baseline, per game) and sigma_diff is the game-level standard deviation of that paired
difference. sigma_diff has NOT been empirically measured yet (no candidate model has
been fit -- fitting one on 60-70 games would itself risk overfitting/leakage before a
model even exists). The values below are swept across a plausible range so the
threshold is honest about its own assumption, not a single fabricated number.

CLI: python -m domains.mlb.ingame.rung8_state.rung8_power
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from domains.mlb.ingame.rung8_state.rung8_corpus_assessment import join_to_grade_corpus

_Z_ALPHA_2 = 1.96  # two-sided alpha=0.05
_Z_BETA = 0.84  # power=0.80

# Target Brier improvement range this class of feature would need to matter,
# per the edge-queue brief (the ~0.04 market-gap ceiling; a real signal here
# would need to close ~0.005-0.01 of it).
_DELTA_GRID = [0.005, 0.0075, 0.01]
# sigma_diff sweep: no empirical estimate exists yet (see docstring) -- this range
# is a labeled ASSUMPTION bracketing plausible per-game paired-Brier-delta noise.
_SIGMA_GRID = [0.02, 0.03, 0.05]


@dataclass(frozen=True)
class PowerRow:
    delta: float
    sigma_diff: float
    n_required: float


def required_n(delta: float, sigma_diff: float, z_alpha_2: float = _Z_ALPHA_2, z_beta: float = _Z_BETA) -> float:
    """Minimum paired game-clustered N to detect `delta` at the given sigma_diff,
    for a two-sided test at alpha=0.05, power=0.80 (defaults)."""
    return ((z_alpha_2 + z_beta) ** 2) * (sigma_diff ** 2) / (delta ** 2)


def detectable_delta(n_games: int, sigma_diff: float, z_alpha_2: float = _Z_ALPHA_2, z_beta: float = _Z_BETA) -> float:
    """Minimum detectable delta at a given n_games and sigma_diff (inverse of required_n)."""
    return (z_alpha_2 + z_beta) * sigma_diff / (n_games ** 0.5)


def sweep(n_games: int) -> List[PowerRow]:
    rows = []
    for delta in _DELTA_GRID:
        for sigma in _SIGMA_GRID:
            rows.append(PowerRow(delta, sigma, required_n(delta, sigma)))
    return rows


def main() -> int:
    n_total, n_joined, _unmatched = join_to_grade_corpus()
    print(f"current joined corpus (games with both reconstructed state AND market prob): {n_joined}")
    print(f"({n_total} total gumbo_live games, {n_joined}/{n_total} joined -- see rung8_corpus_assessment)\n")

    print("required N (game-clustered, alpha=0.05, power=0.80) by target delta x sigma_diff assumption:")
    print(f"{'delta':>8} {'sigma_diff':>11} {'n_required':>11} {'powered_at_current_n':>21}")
    for row in sweep(n_joined if n_joined else 1):
        powered = "YES" if n_joined >= row.n_required else "no"
        print(f"{row.delta:>8.4f} {row.sigma_diff:>11.3f} {row.n_required:>11.1f} {powered:>21}")

    mid_delta, mid_sigma = 0.0075, 0.03
    mid_n = required_n(mid_delta, mid_sigma)
    print(
        f"\nmid-of-range unblock threshold (delta={mid_delta}, sigma_diff={mid_sigma}): "
        f"~{mid_n:.0f} joined games needed. Currently at {n_joined}."
    )
    if n_joined < mid_n:
        print(
            f"VERDICT: WAIT-FOR-DATA. Need ~{mid_n - n_joined:.0f} more joined games "
            "(re-run this module as gumbo_live/ingame_grade corpora grow)."
        )
    else:
        print("VERDICT: powered at the mid-of-range assumption -- proceed to measurement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
