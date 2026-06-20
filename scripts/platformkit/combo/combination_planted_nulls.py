"""scripts.platformkit.combo.combination_planted_nulls -- the FDR lane, PER FAMILY.

`planted_null_fdr` measures a single anonymous family's realized false-ship rate; this
module binds that lane to the FIVE combination FAMILIES (combination_families.FAMILIES):
for each family it routes >=20 shuffled-label combos through the IDENTICAL combo gate
object the real combos use (combo_gate.gate_combo -- no parallel stub, tests-mirror-real)
and reports a per-family FDRResult + the frozen-family list.

A combination null is a known NULL: the detail column is the SHUFFLED outcome label
(plus a small jitter so the merge-boundary leak guard does not mistake it for a perfect
leak). It MUST REJECT. If ANY family's null ships -> FREEZE (flexibility_alarm) -> that
family's REAL candidates do not gate until a human reviews. The lane is the system
measuring ITSELF: if the gate at scale starts manufacturing ships, the nulls ship too
and this catches it BEFORE a real false positive is served.

Different families share the SAME underlying shuffled-label null construction (the null
has no real combination structure -- a shuffled label is structureless regardless of the
family transform that WOULD have been applied), so the FDR estimate is per-family but the
null draws are family-seeded for independence. This is the honest null: it does not try
to "look like" a family, it IS pure noise, and the gate must reject pure noise at every K.

NEVER writes data/registry/, never flips a flag, never creates the sentinel. Calibration,
not edge; no $/ROI token. numpy (+ pandas via the lane) + stdlib; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Sequence

from scripts.platformkit.combo.combination_families import FAMILIES
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS
from scripts.platformkit.combo.planted_null_fdr import (
    FDRResult, frozen_families as _frozen, ran_through_identical_gate, run_family_nulls,
)

logger = logging.getLogger("combination_planted_nulls")

# A stable per-family seed offset so each family draws independent nulls (R8 -- a null
# that ships is caught per-family, not averaged away).
_FAMILY_SEED = {fam: 1000 + 137 * i for i, fam in enumerate(FAMILIES)}


def run_all_family_nulls(
    *, n: int = 20, n_games: int = 50, ticks: int = 8,
    eps: float = DEFAULT_EPS, K: int = 1, families: Sequence[str] = FAMILIES,
) -> Dict[str, FDRResult]:
    """Run the planted-null FDR lane for EVERY combination family through the SAME gate.

    Returns {family: FDRResult}. Each family routes >=20 shuffled-label combos through
    combo_gate.gate_combo (the production object). A family whose null ships OR whose
    FDR-hat exceeds fdr_budget(eps, K) is FROZEN. HONEST EXPECTATION: every family's
    fdr_hat == 0.0 (a structureless shuffled label cannot replicate cross-corpus).
    """
    if not ran_through_identical_gate():
        raise AssertionError("planted-null lane is NOT routed through the production gate "
                             "object -- a parallel stub would let a null ship unnoticed.")
    results: Dict[str, FDRResult] = {}
    for fam in families:
        seed = _FAMILY_SEED.get(fam, 1234)
        res = run_family_nulls(fam, n=n, n_games=n_games, ticks=ticks,
                               seed=seed, eps=eps, K=K)
        results[fam] = res
        logger.info("family=%s fdr_hat=%.3f n_run=%d n_shipped=%d frozen=%s",
                    fam, res.fdr_hat, res.n_run, res.n_shipped, res.frozen)
    return results


def all_nulls_reject(results: Dict[str, FDRResult]) -> bool:
    """True iff NO family's planted null shipped (every fdr_hat is 0 and none frozen)."""
    return all(r.n_shipped == 0 and not r.frozen for r in results.values())


def frozen_families(results: Dict[str, FDRResult]) -> List[str]:
    """Families whose null shipped OR whose FDR-hat exceeded budget -> FROZEN."""
    return _frozen(list(results.values()))


__all__ = [
    "run_all_family_nulls", "all_nulls_reject", "frozen_families",
    "ran_through_identical_gate",
]
