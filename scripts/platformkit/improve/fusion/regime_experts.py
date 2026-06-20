"""scripts.platformkit.improve.fusion.regime_experts -- MoE regime split (graceful-degrade).

A mixture-of-experts fusion fits a DIFFERENT convex blend per game-state regime. The
regime label MUST be a NAME -- an in-game margin/period/time bucket
(candidate_families._INGAME_MARGIN_BUCKETS) or a vault-taxonomy archetype NAME -- NEVER
a KMeans cluster-id (memory: signal_selectors_use_names; a cluster-id breaks on every
refit). This module owns ONLY the regime split + the graceful-degrade rule; the OOF
meta-fit and the gate live elsewhere.

THE GRACEFUL-DEGRADE RULE (the anti-fishing guard): a regime that is degenerate -- one
that holds too few rows to fit an independent blend, or a split that collapses to a
SINGLE regime -- must NOT manufacture a win. It collapses to the GLOBAL blend (the
proven base's single weight) so a useless split can only MATCH the base -> REJECT
downstream. Trying many splits and keeping the lucky one is counted into K by
meta_flex_fwer; this module makes a degenerate split inert.

  REGIME_NAMES   -- the allowed name-stable regime labels (margin buckets + a late tag).
  assign_regime(margin, frac_elapsed) -> a regime NAME (never a cluster-id).
  regime_split(regimes, min_rows) -> {regime: row_indices}, dropping under-powered
                                     regimes into a pooled GLOBAL bucket (graceful-degrade).
  is_degenerate_split(split) -> True when only ONE effective regime survives.

Calibration, not edge. NO $ / ROI anywhere. numpy + stdlib only; ASCII; <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

# Reuse the PROVEN, name-stable in-game margin buckets (no new numbers, no cluster-ids).
from scripts.platformkit.improve.candidate_families import _INGAME_MARGIN_BUCKETS

# The GLOBAL pseudo-regime: under-powered regimes pool here and fit the single base blend.
GLOBAL = "global"
# A late-game name tag (frac_elapsed past this is "late"); descriptive, person-free.
_LATE_FRAC = 0.75
# Margin thresholds (abs state_diff) that map a numeric margin to a NAME bucket. These
# are descriptive cut labels reusing the proven close/mid/blowout vocabulary.
_CLOSE_ABS = 4.0
_BLOWOUT_ABS = 12.0
# A regime needs at least this many rows to fit its own blend; else it pools to GLOBAL.
DEFAULT_MIN_ROWS = 30

# The allowed regime NAMES (margin buckets + a late tag + the global pool). NEVER a
# KMeans cluster-id -- a cluster-id would re-number on every refit and break selection.
REGIME_NAMES = tuple(_INGAME_MARGIN_BUCKETS) + ("late", GLOBAL)

__all__ = [
    "GLOBAL", "REGIME_NAMES", "assign_regime", "regime_split", "is_degenerate_split",
]


def assign_regime(margin: float, frac_elapsed: float) -> str:
    """Map a (signed margin, frac_elapsed) state to a name-stable regime label.

    Returns one of REGIME_NAMES (a NAME, never a cluster-id). Late-game overrides the
    margin bucket so the proven late-game lever gets its own expert. Non-finite input
    falls back to GLOBAL (conservative: pooled into the single base blend).
    """
    try:
        m = abs(float(margin))
        f = float(frac_elapsed)
    except Exception:  # noqa: BLE001 -- malformed state -> pool to GLOBAL
        return GLOBAL
    if not (np.isfinite(m) and np.isfinite(f)):
        return GLOBAL
    if f >= _LATE_FRAC:
        return "late"
    if m <= _CLOSE_ABS:
        return "close"
    if m >= _BLOWOUT_ABS:
        return "blowout"
    return "mid"


def regime_split(regimes: Sequence[str],
                 min_rows: int = DEFAULT_MIN_ROWS) -> Dict[str, List[int]]:
    """Group row indices by regime NAME; pool under-powered regimes into GLOBAL.

    An expert needs `min_rows` rows to fit an independent convex blend honestly; a regime
    below that floor is POOLED into GLOBAL (graceful-degrade) rather than fit on noise.
    Returns {regime_name: [row_index, ...]}; the GLOBAL bucket always exists (possibly
    empty). A split where only GLOBAL (or one regime) survives is degenerate -- see
    is_degenerate_split -- and downstream collapses to the single base blend.
    """
    min_rows = max(1, int(min_rows))
    by_regime: Dict[str, List[int]] = {}
    for i, r in enumerate(regimes):
        name = str(r) if str(r) in REGIME_NAMES else GLOBAL
        by_regime.setdefault(name, []).append(i)
    out: Dict[str, List[int]] = {GLOBAL: list(by_regime.get(GLOBAL, []))}
    for name, idxs in by_regime.items():
        if name == GLOBAL:
            continue
        if len(idxs) >= min_rows:
            out[name] = list(idxs)          # powered enough for its own expert
        else:
            out[GLOBAL].extend(idxs)        # graceful-degrade: pool into GLOBAL
    out[GLOBAL].sort()
    return out


def is_degenerate_split(split: Dict[str, List[int]]) -> bool:
    """True iff at most ONE regime carries rows (collapses to the GLOBAL blend).

    A degenerate split adds NO regime structure: it must collapse to the single global
    blend so it can only MATCH the base (a degenerate split never manufactures a win).
    """
    non_empty = [name for name, idxs in split.items() if idxs]
    return len(non_empty) <= 1
