"""scripts.platformkit.combo.batch_gate_rules -- pure rule helpers split out of
batch_gate.py to keep that module under the 300-LOC cap.

Two rules, each enforcing one PREREG_AMENDMENT_A2 clause BY CODE:
  1. `remap_replicated_weak` -- clause 3: a same-source adjacent-season corpus
     pair can never mint a SHIP; any SHIP verdict is downgraded in place.
  2. `plant_null_for_spec` -- clause 4 letter-of-spec: a PRODUCT feature's
     null draw permutes its UNDERLYING columns and recomputes the product,
     rather than permuting the precomputed product column directly (a solo
     permute of an already-multiplied column destroys less of the tested
     structure than permuting the factors that build it).

Calibration, not edge. NO $/ROI anywhere. numpy + pandas + stdlib only. ASCII.
"""
from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.stack_gate_pregame import StackVerdict


def remap_replicated_weak(verdict: StackVerdict, same_source_pair: bool) -> StackVerdict:
    """PREREG_AMENDMENT_A2 clause 3: on a same-source (e.g. adjacent-season,
    same-pipeline) corpus pair, a SHIP verdict is NOT a real ship -- it lacks
    independent-source confirmation. Mutates + returns `verdict` in place
    (StackVerdict is not frozen); no-op for every other verdict/pair combo."""
    if same_source_pair and verdict.verdict == "SHIP":
        verdict.verdict = "REPLICATED_WEAK"
        verdict.detail["promotion_blocked_until"] = "independent-source confirmation"
        verdict.proposal_only = True
        verdict.caveats.append(
            "clause 3 (PREREG_AMENDMENT_A2): same_source_pair=True -- SHIP remapped to "
            "REPLICATED_WEAK, promotion blocked pending independent-source confirmation.")
    return verdict


def plant_null_for_spec(
    unit_df: pd.DataFrame, features: Sequence[str],
    components: Optional[Mapping[str, Sequence[str]]],
    rng: np.random.Generator,
    fit_and_score_fn: Callable[[pd.DataFrame, Sequence[str]], Sequence],
    prescreen_delta_fn: Callable[[Sequence], float],
) -> bool:
    """PREREG_AMENDMENT_A2 clause 4, letter-of-spec: for a feature declared as
    a PRODUCT of underlying columns (`components[feature]`), permute the
    UNDERLYING columns and RECOMPUTE the product -- destroying the tested
    interaction structure itself, not just its precomputed column. Features
    with no `components` entry fall back to the direct-permute-the-column
    behavior (caveat noted by the caller via `used_direct_permute_fallback`).
    True iff the shuffled stack beats base, mirroring the un-split original."""
    shuffled = unit_df.copy()
    components = components or {}
    for feat in features:
        underlying = components.get(feat)
        if underlying:
            for col in underlying:
                shuffled[col] = rng.permutation(shuffled[col].to_numpy())
            shuffled[feat] = np.prod([shuffled[c].to_numpy() for c in underlying], axis=0)
        else:
            shuffled[feat] = rng.permutation(shuffled[feat].to_numpy())
    null_rows = fit_and_score_fn(shuffled, features)
    if not null_rows:
        return False
    return prescreen_delta_fn(null_rows) > 0.0


__all__ = ["remap_replicated_weak", "plant_null_for_spec"]
