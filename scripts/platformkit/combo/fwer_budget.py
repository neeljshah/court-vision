"""scripts.platformkit.combo.fwer_budget -- the bar-vs-K curve (C3 G2 / L6).

A combination search EXPLODES the multiple-comparisons surface: enumerating K
interaction / regime-conditional / residual-on-residual / archetype-blend
candidates and gating each at a fixed eps makes P(>=1 false SHIP) ~= 1-(1-eps)^K,
which is large for the K a real combo factory produces. The load-bearing honesty
move is a per-test bar that TIGHTENS as K grows, so a wider search gets STRICTER,
not looser, and a SHIP is HARD while a REJECT is CHEAP.

This is the ONE place the bar-vs-K curve lives (pure functions, stdlib math only):

  eps_eff(eps, K)        = eps / max(1, K)            (Bonferroni-on-eps; FWER-correct,
                                                       assumption-light -- no independence
                                                       needed). MONOTONE DECREASING in K.
  min_corpora_eff(...)   = min(n_corpora, 2 + floor(log2 K)), capped at `cap` (default 4)
                           -- the replication floor RISES with K as defense-in-depth, but is
                           capped so a genuine 2-corpora signal stays REACHABLE (the aim is
                           MORE real survivors, NEVER zero ships).
  fdr_budget(eps, K)     = eps_eff(eps, K) -- the planted-null lane's FDR-hat must stay
                           at/below the SAME tightened budget the real candidates clear.

S14 ADDED A SECOND, LOOSER AXIS -- say so plainly:

  bh_within_family(p_values, q) -- Benjamini-Hochberg FDR over the p-values of ONE
                           frozen family (docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md).
                           A within-family FDR bar at q=0.05 is STRICTLY LOOSER than the
                           global Bonferroni `deflated_p(raw_p, k_global)` for any hypothesis
                           sitting inside a family of more than one member. It is admissible
                           ONLY because the families were frozen and committed BEFORE the first
                           family-relative trial, because an AHEAD must clear BOTH bars (see
                           eval_gate/family_bars.dual_bar_verdict), and because NO PAST VERDICT
                           IS RE-SCORED under it -- re-scoring a recorded verdict against a
                           looser bar is a self-serving reinterpretation, not a measurement.
  across_families(p, n)  = deflated_p(p, n) -- Bonferroni across the FAMILY count, for a claim
                           that ranges over families rather than inside one.

K-CUMULATIVITY (R13): K_live MUST be the deduped enumerated count summed CUMULATIVELY
across cycles (a per-family running total). Splitting a search into many tiny cycles
must NOT reset the budget -- so callers pass the cumulative K, and `cumulative_k`
helps a ledger combine a prior total with this cycle's new deduped count.

Calibration, not edge. NO $ / ROI / market-edge anywhere. ASCII.
"""
from __future__ import annotations

import math
from typing import NamedTuple, Sequence

from statsmodels.stats.multitest import multipletests

from scripts.platformkit.eval_gate.deflated_metrics import deflated_p

# eps default mirrors the in-game gate's eps=0.05 (ingame_gate_generic.gate_cross).
DEFAULT_EPS = 0.05
# Replication-floor cap: never exceed this many required corpora (R14 -- over-tightening
# guard). A FIXED constant, not a moving target, so a real 2-corpora signal stays reachable.
DEFAULT_CORPORA_CAP = 4
# Within-family FDR level, frozen in FWER_FAMILIES_SPEC_2026-09-03.md (`q_within_family`).
DEFAULT_Q = 0.05
# The floor never drops below 2 corpora (single-corpus replication is never enough).
_MIN_CORPORA_FLOOR = 2


def eps_eff(eps: float, k: int) -> float:
    """Effective per-test FWER threshold = eps / max(1, K). Monotone DECREASING in K.

    Bonferroni-on-eps: assumption-light and correct for family-wise error. At K=1 it
    equals eps (a single test is uncorrected); as K grows the per-test p-value bar
    shrinks, so a combo that would clear the bar at K=1 must clear a much stricter bar
    once the search is wide. K is clamped to >=1 (an empty search does not loosen eps).
    """
    if not (0.0 < eps <= 1.0):
        raise ValueError(f"eps must be in (0,1], got {eps}")
    return float(eps) / float(max(1, int(k)))


def min_corpora_eff(n_corpora: int, k: int, cap: int = DEFAULT_CORPORA_CAP) -> int:
    """Replication floor that RISES with K: min(n_corpora, 2 + floor(log2 K)), capped.

    2 at K=1, 3 at K=2..3, 4 at K=4.., then held at `cap`. Never exceeds the number of
    AVAILABLE corpora (so a 2-corpora environment can still clear at the floor of 2),
    and never drops below 2. The cap (default 4) keeps a genuine signal reachable.
    """
    k = max(1, int(k))
    cap = max(_MIN_CORPORA_FLOOR, int(cap))
    rises = _MIN_CORPORA_FLOOR + int(math.floor(math.log2(k)))
    floor = min(rises, cap)
    floor = max(_MIN_CORPORA_FLOOR, floor)
    # Never demand more corpora than exist (else nothing could ever ship -- R14).
    return int(min(floor, max(_MIN_CORPORA_FLOOR, int(n_corpora))))


def fdr_budget(eps: float, k: int) -> float:
    """The planted-null FDR-hat budget -- the SAME tightened per-test bar real combos face.

    The null lane's measured false-ship RATE must stay at/below this; if it rises above
    it as K scales, the gate is manufacturing false positives and the family FREEZES.
    """
    return eps_eff(eps, k)


def cumulative_k(prior_k: int, new_deduped_k: int) -> int:
    """Combine a ledger's PRIOR cumulative K with this cycle's NEW deduped count (R13).

    Splitting a wide search across many small cycles must NOT reset the budget: the
    ledger persists a per-family running total and this returns prior + new, so eps_eff
    keeps tightening as the cumulative search width grows. Both clamped to >=0.
    """
    return int(max(0, int(prior_k))) + int(max(0, int(new_deduped_k)))


class BHResult(NamedTuple):
    """One Benjamini-Hochberg pass over ONE frozen family's p-values."""

    q: float
    n: int
    n_discoveries: int
    rejected: tuple
    adjusted: tuple
    threshold: float


def bh_within_family(p_values: Sequence[float], q: float = DEFAULT_Q) -> BHResult:
    """Benjamini-Hochberg FDR at level `q` over the p-values of ONE frozen family.

    Thin wrapper over statsmodels.stats.multitest.multipletests(method="fdr_bh")
    (statsmodels 0.14.4, BSD 3-Clause, already installed -- no new dependency): BH is
    worth importing rather than re-deriving because the step-up rule is easy to get
    subtly wrong at ties, and a wrong FDR routine fails OPEN.

    `threshold` is the largest p-value rejected (0.0 when nothing is rejected), so a
    caller can print the bar its hypothesis actually had to clear. `rejected` and
    `adjusted` are returned in the caller's input ORDER, not sorted order.

    THE FAMILY MUST BE FROZEN FIRST. Choosing family membership after seeing the
    p-values is the whole failure mode this bar invites; the membership lives in
    docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md and is pinned by content.
    """
    if not (0.0 < q <= 1.0):
        raise ValueError(f"q must be in (0,1], got {q}")
    values = [float(p) for p in p_values]
    if not values:
        raise ValueError("a family needs at least one p-value")
    if any(not (0.0 <= p <= 1.0) for p in values):
        raise ValueError("every p-value must be in [0,1]")
    rejected, adjusted, _sidak, _bonf = multipletests(values, alpha=float(q), method="fdr_bh")
    flags = tuple(bool(r) for r in rejected)
    hits = [p for p, flag in zip(values, flags) if flag]
    return BHResult(float(q), len(values), len(hits), flags,
                    tuple(float(a) for a in adjusted), max(hits) if hits else 0.0)


def across_families(p: float, n_families: int) -> float:
    """Bonferroni-deflate a p-value across the FAMILY count, not the hypothesis count.

    The complement of `bh_within_family`: BH prices a hypothesis inside its family;
    this prices a claim that ranges ACROSS families. Delegates to the one canonical
    deflation (`eval_gate.deflated_metrics.deflated_p`) so the two paths cannot drift.
    It does NOT replace the global `deflated_p(raw_p, k_cumulative)` bar, which is
    unchanged and still charged on every trial.
    """
    return deflated_p(p, n_families)


__all__ = [
    "DEFAULT_EPS", "DEFAULT_CORPORA_CAP", "DEFAULT_Q", "BHResult",
    "eps_eff", "min_corpora_eff", "fdr_budget", "cumulative_k",
    "bh_within_family", "across_families",
]
