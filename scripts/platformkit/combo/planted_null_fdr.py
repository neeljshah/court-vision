"""scripts.platformkit.combo.planted_null_fdr -- G3: power-sized planted-null FDR lane.

`signals.planted_nulls` runs ONE shuffled-label null per family -- a tripwire, but
near-zero power to ESTIMATE the realized false-ship RATE. A combination search needs
a lane that MEASURES the system's own false-discovery rate: >=20 shuffled-label combos
PER FAMILY routed through the IDENTICAL combo gate object, an empirical FDR-hat, and a
FREEZE when a null ships OR FDR-hat exceeds the (FWER-tightened) budget.

  fdr_hat(family) = (# planted nulls that reached SHIP) / (# planted nulls run).

A null that SHIPS -> FREEZE (flexibility_alarm). FDR-hat > fdr_budget(eps, K) -> FREEZE.
A frozen family's REAL candidates do not gate until a human reviews. This lane is the
system measuring ITSELF: if the gate at scale starts manufacturing ships, the nulls
ship too and the lane catches it BEFORE a real false positive is served.

ran_through_identical_gate(): the lane routes each null through the SAME gate object the
real combos use (combo_gate.gate_combo) -- a test asserts same-object (tests-mirror-real,
no parallel stub). Shuffled OUTCOME labels are the strongest within-class null (preserve
marginal balance, destroy the row-level link).

NEVER writes data/registry/, never flips a flag, never creates the sentinel, never edits
MEMORY.md. Calibration, not edge; no $ / ROI anywhere. numpy + pandas (gate contract) +
stdlib; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.combo import combo_gate as _CG
from scripts.platformkit.combo.combo_gate import SHIP, gate_combo
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, fdr_budget

logger = logging.getLogger("planted_null_fdr")

_DETAIL_COL = "detail"
_MIN_NULLS = 20  # power floor: one null/family cannot estimate an FDR.


@dataclass(frozen=True)
class FDRResult:
    """Per-family realized false-discovery estimate from >=20 shuffled-label combos."""

    family: str
    fdr_hat: Optional[float]     # None => no scorable null (every run crashed)
    n_run: int
    n_shipped: int
    budget: float
    frozen: bool
    note: str = "calibration, not edge"
    n_error: int = 0             # crashed nulls: COUNTED, excluded from the denominator


def _build_base_corpus(n_games: int, ticks: int, seed: int):
    """A realistic (state_diff, frac_elapsed, outcome) base corpus (mirrors planted_nulls)."""
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows: List[Dict[str, object]] = []
    for g in range(n_games):
        strength = float(rng.normal(0.0, 1.0))
        final = strength + float(rng.normal(0.0, 0.5))
        outcome = 1 if final > 0.0 else 0
        for t in range(ticks):
            frac = (t + 1) / float(ticks)
            sd = strength * frac * 10.0 + float(rng.normal(0.0, 1.0))
            rows.append({"game_id": "G%03d" % g, "asof_idx": t,
                         "state_diff": sd, "frac_elapsed": frac, "outcome": int(outcome)})
    return pd.DataFrame(rows)


def _shuffled_label_detail(base_df, seed: int):
    """A DETAIL frame whose column is the SHUFFLED outcome label (a known null)."""
    import pandas as pd
    rng = np.random.default_rng(seed + 7919)
    y = base_df["outcome"].to_numpy().astype(float)
    shuffled = y[rng.permutation(len(y))]
    # nudge off exact {0,1} so the merge-boundary leak guard does not mistake a shuffled
    # label for a perfect leak; it stays a NOISE detail (the gate must REJECT it).
    detail = shuffled + rng.normal(0.0, 0.25, size=len(shuffled))
    return pd.DataFrame({"game_id": base_df["game_id"].to_numpy(),
                         "asof_idx": base_df["asof_idx"].to_numpy(),
                         _DETAIL_COL: detail})


def run_family_nulls(family: str, *, n: int = _MIN_NULLS, n_games: int = 50,
                     ticks: int = 8, seed: int = 1234, eps: float = DEFAULT_EPS,
                     K: int = 1, gate=gate_combo) -> FDRResult:
    """Route >=20 shuffled-label combos for `family` through the IDENTICAL combo gate.

    Each null builds two disjoint corpora + a shuffled-label detail, then calls the SAME
    `gate` object the real combos use (default combo_gate.gate_combo). fdr_hat = ships/SCORED
    run (a crashed null is counted in n_error and left out; all-crashed -> fdr_hat None).
    FREEZE on any ship, on any crash, OR fdr_hat > fdr_budget(eps, K). `gate` is a parameter ONLY so a
    test can inject a deliberately-WEAKENED gate to prove the tripwire fires; production
    always uses the default (the same-object assertion guards drift).
    """
    n = max(_MIN_NULLS, int(n))
    budget = fdr_budget(eps, K)
    n_shipped = 0
    n_error = 0
    for i in range(n):
        s = seed + i * 17
        base_a = _build_base_corpus(n_games, ticks, seed=s)
        base_b = _build_base_corpus(n_games, ticks, seed=s + 101)
        det_a = _shuffled_label_detail(base_a, seed=s)
        det_b = _shuffled_label_detail(base_b, seed=s + 101)
        try:
            v = gate(None, base_a, det_a, base_b, det_b, combo_col=_DETAIL_COL,
                     base_feature_cols=None, parity_ok=True, eps=eps, K=K,
                     n_corpora=2)
            verdict = str(getattr(v, "verdict", "REJECT"))
        except Exception as exc:  # a crashing null measured NOTHING -- not a non-ship
            logger.warning("planted null %s/%d CRASHED -> unscorable: %s", family, i, exc)
            n_error += 1
            verdict = "ERROR"
        if verdict == SHIP:
            n_shipped += 1
    # A crashed null is COUNTED (n_error) and excluded from the denominator: scoring it
    # as a non-ship let 20/20 crashes report fdr_hat=0.0 / frozen=False -- "the gate is
    # not manufacturing ships" having measured nothing. No scorable null -> no rate.
    n_scored = n - n_error
    fdr_hat = (n_shipped / float(n_scored)) if n_scored > 0 else None
    frozen = bool(n_shipped > 0 or n_error > 0
                  or (fdr_hat is not None and fdr_hat > budget))
    return FDRResult(family=family,
                     fdr_hat=None if fdr_hat is None else float(fdr_hat), n_run=n,
                     n_shipped=int(n_shipped), budget=float(budget), frozen=frozen,
                     n_error=int(n_error))


def frozen_families(results: Sequence[FDRResult]) -> List[str]:
    """Families whose null shipped OR whose FDR-hat exceeded the budget -> FROZEN."""
    return [r.family for r in results if r.frozen]


def ran_through_identical_gate() -> bool:
    """True: this lane's default gate symbol IS the production combo gate (no stub)."""
    return gate_combo is _CG.gate_combo


__all__ = [
    "FDRResult", "run_family_nulls", "frozen_families",
    "ran_through_identical_gate",
]
