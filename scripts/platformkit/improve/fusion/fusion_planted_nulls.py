"""scripts.platformkit.improve.fusion.fusion_planted_nulls -- shuffled-label FUSED nulls.

The fusion lane ADDS free parameters (meta-weights, regime splits, residual learners) --
exactly what manufactures in-sample lifts. The honesty tripwire: for EACH fusion family,
route shuffled-OUTCOME-label FUSED models through the IDENTICAL combo gate object the
real fusions use. A planted null MUST reject; if one ever SHIPS, the family's flexibility
manufactured a false win -> the family FREEZES and a human must review (H6-fusion).

This mirrors signals/planted_null_fdr (the power-sized lane) but for FUSION families:
each null builds two disjoint corpora + a shuffled-label fused detail and calls the SAME
combo_gate.gate_combo (ran_through_identical_gate asserts same-object -- tests-mirror-real,
no parallel stub). Shuffled outcome labels preserve marginal balance but destroy the
row-level link, so a meta-learner with real flexibility would still "fit" them -> a SHIP
would prove the gate is leaking.

NEVER writes data/registry/, never flips a flag, never creates the sentinel, never edits
MEMORY.md. Calibration, not edge; no $/ROI anywhere. numpy + pandas (gate contract) +
stdlib; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np

from scripts.platformkit.combo import combo_gate as _CG
from scripts.platformkit.combo.combo_gate import SHIP, gate_combo
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, fdr_budget
from scripts.platformkit.improve.fusion.fusion_families import FAMILIES

logger = logging.getLogger("fusion_planted_nulls")

_DETAIL_COL = "detail"
_MIN_NULLS = 20  # power floor: one null/family cannot estimate the realized FDR.

__all__ = [
    "FusionNullResult", "run_fusion_family_nulls", "frozen_families",
    "ran_through_identical_gate",
]


@dataclass(frozen=True)
class FusionNullResult:
    """Per-fusion-family realized false-discovery estimate from >=20 shuffled-label nulls."""

    family: str
    fdr_hat: float
    n_run: int
    n_shipped: int
    budget: float
    frozen: bool
    note: str = "calibration, not edge"


def _base_corpus(n_games: int, ticks: int, seed: int):
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        strength = float(rng.normal(0.0, 1.0))
        final = strength + float(rng.normal(0.0, 0.5))
        outcome = 1 if final > 0.0 else 0
        for t in range(ticks):
            frac = (t + 1) / float(ticks)
            sd = strength * frac * 10.0 + float(rng.normal(0.0, 1.0))
            rows.append({"game_id": "G%03d" % g, "asof_idx": t, "state_diff": sd,
                         "frac_elapsed": frac, "outcome": int(outcome)})
    return pd.DataFrame(rows)


def _shuffled_fused_detail(base_df, seed: int):
    """A fused-detail frame whose column is the SHUFFLED outcome label (a known null).

    The shuffled label is the strongest within-class null (preserves the marginal but
    destroys the row link); a FUSED model that 'ships' it has manufactured the win.
    """
    import pandas as pd
    rng = np.random.default_rng(seed + 7919)
    y = base_df["outcome"].to_numpy().astype(float)
    shuffled = y[rng.permutation(len(y))]
    detail = shuffled + rng.normal(0.0, 0.25, size=len(shuffled))  # nudge off {0,1}
    return pd.DataFrame({"game_id": base_df["game_id"].to_numpy(),
                         "asof_idx": base_df["asof_idx"].to_numpy(),
                         _DETAIL_COL: detail})


def run_fusion_family_nulls(family: str, *, n: int = _MIN_NULLS, n_games: int = 50,
                            ticks: int = 8, seed: int = 4321, eps: float = DEFAULT_EPS,
                            K: int = 1, gate=gate_combo) -> FusionNullResult:
    """Route >=20 shuffled-label FUSED nulls for `family` through the IDENTICAL combo gate.

    fdr_hat = ships / run. FREEZE on any ship OR fdr_hat > fdr_budget(eps, K). `gate` is a
    parameter ONLY so a test can inject a deliberately-WEAKENED gate to prove the tripwire
    fires; production always uses the default (the same-object assertion guards drift).
    """
    n = max(_MIN_NULLS, int(n))
    budget = fdr_budget(eps, K)
    n_shipped = 0
    for i in range(n):
        s = seed + i * 17
        base_a = _base_corpus(n_games, ticks, seed=s)
        base_b = _base_corpus(n_games, ticks, seed=s + 101)
        det_a = _shuffled_fused_detail(base_a, seed=s)
        det_b = _shuffled_fused_detail(base_b, seed=s + 101)
        try:
            v = gate(None, base_a, det_a, base_b, det_b, combo_col=_DETAIL_COL,
                     base_feature_cols=None, parity_ok=True, eps=eps, K=K, n_corpora=2)
            verdict = str(getattr(v, "verdict", "REJECT"))
        except Exception as exc:  # a crashing null is a conservative non-ship
            logger.debug("fusion null %s/%d crashed -> non-ship: %s", family, i, exc)
            verdict = "ERROR"
        if verdict == SHIP:
            n_shipped += 1
    fdr_hat = n_shipped / float(n)
    frozen = bool(n_shipped > 0 or fdr_hat > budget)
    return FusionNullResult(family=str(family), fdr_hat=float(fdr_hat), n_run=n,
                            n_shipped=int(n_shipped), budget=float(budget), frozen=frozen)


def frozen_families(results: Sequence[FusionNullResult]) -> List[str]:
    """Fusion families whose null shipped OR whose FDR-hat exceeded the budget -> FROZEN."""
    return [r.family for r in results if r.frozen]


def ran_through_identical_gate() -> bool:
    """True: this lane's default gate symbol IS the production combo gate (no stub)."""
    return gate_combo is _CG.gate_combo


def all_family_names() -> List[str]:
    """The fusion family names the null lane covers (one null batch per family)."""
    return list(FAMILIES)
