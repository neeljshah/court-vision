"""scripts.platformkit.combo.combination_enum -- dedup + Thompson bandit + HARD K-cap.

The combinatorial space EXPLODES, so the generator's job is to NARROW it, never
brute-force it (brute force is a guaranteed false-positive farm). This module is the
SEARCH, not a flat list. It is pure, deterministic-given-(tried,ledger,seed), and
never raises.

  * DEDUP-vs-tried memory -- a tried combo id is NEVER re-rolled (monotone coverage;
    R3 -- no fishing for a lucky fold by re-rolling).
  * CHEAP |corr| PRE-SCREEN (RANK ONLY, never a decider) on a DEDICATED SCREEN SLICE
    that shares NO row index with ANY CV fold the gate later uses (R2 -- screening on
    the gate's data is selection-on-the-test-set, the #1 leak). The screen only ORDERS
    which combos to propose; the honest nested-CV gate is the sole decider. A
    collinear-with-base drop (_ORTHO_CAP) refuses re-expressions before they cost K.
  * DETERMINISTIC THOMPSON bandit per FAMILY arm using a skeptical Beta(1,4) posterior
    over the ledger's per-family pass rate -- it cannot promote a combo above its own
    family's planted null (the screen is a RANK term only).
  * HARD K-CAP per cycle tied to the FWER budget (R1): K never grows so large that
    eps_eff = eps / K_live drops below a floor min_eps_eff (below which a real signal
    is un-shippable). The enum REFUSES to emit a combo that would push eps_eff under
    the floor -- it proposes FEWER, higher-information combos rather than dilute the
    budget. K is CUMULATIVE across cycles (R13 -- a cycle split cannot reset the budget).

NEVER writes data/registry/, never flips a flag, never creates the sentinel. The build
path routes ONLY through the MF-choke (build_fn), constructing no candidate itself.
Calibration, not edge; no $/ROI token. numpy + stdlib; ASCII; <=300 LOC.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from scripts.platformkit.combo.combination_families import CombinationSpec
from scripts.platformkit.combo.fwer_budget import (
    DEFAULT_EPS, cumulative_k, eps_eff,
)

# A combo whose |corr| with a shipped base column meets/exceeds this is a re-expression.
_ORTHO_CAP = 0.92
# A skeptical Beta(1,4) prior: a family must EARN its pass-rate posterior from the ledger.
_BETA_A, _BETA_B = 1.0, 4.0
# Score weights (fixed + deterministic): the screen is a RANK tie-break, never a promoter.
_W_SCREEN, _W_POSTMEAN, _W_NOVELTY = 0.30, 0.55, 0.15
# Hard ceiling on K regardless of budget (the generator never proposes a wide cycle).
_K_HARD_CAP = 8
# eps_eff floor: below this a genuine 2-corpora signal becomes un-shippable (R9).
_MIN_EPS_EFF = 0.005


@dataclass(frozen=True)
class ScreenColumns:
    """Aligned (combo_col, target_col) plus the row indices the screen is allowed to use.

    `screen_idx` MUST be disjoint from every index any CV fold uses -- the enum asserts
    this disjointness so the screen can never see a gate fold (R2).
    """

    combo_col: np.ndarray
    target_col: np.ndarray
    screen_idx: np.ndarray
    base_cols: Tuple[np.ndarray, ...] = ()


def fwer_budget_remaining(prior_k: int, eps: float = DEFAULT_EPS,
                          min_eps_eff: float = _MIN_EPS_EFF) -> int:
    """Max NEW deduped combos this cycle before eps_eff(eps, K_live) drops below floor.

    K_live = prior_k + new; we solve for the largest `new` with eps/(K_live) >= floor,
    i.e. K_live <= eps/floor. Returns >= 0. R13: prior_k is the CUMULATIVE ledger total.
    """
    if min_eps_eff <= 0.0:
        return _K_HARD_CAP
    k_max_live = int(np.floor(eps / float(min_eps_eff)))
    allowed = k_max_live - int(max(0, prior_k))
    return int(max(0, allowed))


def k_cap(prior_k: int, eps: float = DEFAULT_EPS,
          min_eps_eff: float = _MIN_EPS_EFF) -> int:
    """The HARD per-cycle K = min(_K_HARD_CAP, fwer_budget_remaining)."""
    return int(min(_K_HARD_CAP, fwer_budget_remaining(prior_k, eps, min_eps_eff)))


def _abs_corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2 or a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0
    c = float(np.corrcoef(a, b)[0, 1])
    return abs(c) if np.isfinite(c) else 0.0


def screen_score(cols: ScreenColumns) -> Optional[float]:
    """|corr(combo, target)| on the DISJOINT screen slice, or None if collinear-with-base.

    Returns None (DROP) when the combo |corr| with ANY base column on the screen slice
    is >= _ORTHO_CAP (a re-expression, not a discovery -- it must not cost K). Otherwise
    returns the absolute screen correlation as a RANK term (never a decider).
    """
    idx = cols.screen_idx
    x = np.asarray(cols.combo_col, dtype=float)[idx]
    y = np.asarray(cols.target_col, dtype=float)[idx]
    for bc in cols.base_cols:
        b = np.asarray(bc, dtype=float)[idx]
        if _abs_corr(x, b) >= _ORTHO_CAP:
            return None
    return _abs_corr(x, y)


def _family_post_mean(family: str, ledger: Dict[str, Tuple[int, int]]) -> float:
    """Beta(1,4)-posterior mean pass rate for a family from ledger {family:(pass,fail)}."""
    p, f = ledger.get(family, (0, 0))
    return (_BETA_A + p) / (_BETA_A + _BETA_B + p + f)


def _novelty(combo_id: str, seed: int) -> float:
    """Bounded deterministic novelty jitter in [0,1) (Thompson exploration term)."""
    h = hashlib.blake2b(f"{seed}|{combo_id}".encode("utf-8"), digest_size=8)
    return (int.from_bytes(h.digest(), "big") % 100000) / 100000.0


def assert_screen_disjoint(screen_idx: Sequence[int],
                           cv_fold_idx: Sequence[int]) -> None:
    """Raise if the screen slice shares ANY row with a CV fold (the anti-leak invariant)."""
    overlap = set(int(i) for i in screen_idx) & set(int(i) for i in cv_fold_idx)
    if overlap:
        raise AssertionError(
            f"SCREEN-LEAK: screen slice overlaps CV folds on {len(overlap)} rows "
            "-- screening on the gate's data is selection-on-the-test-set (R2).")


def enumerate_combination_specs(
    specs: Sequence[CombinationSpec],
    *,
    tried_ids: Optional[Set[str]] = None,
    ledger: Optional[Dict[str, Tuple[int, int]]] = None,
    prior_k: int = 0,
    eps: float = DEFAULT_EPS,
    min_eps_eff: float = _MIN_EPS_EFF,
    screen_of: Optional[Callable[[CombinationSpec], Optional[ScreenColumns]]] = None,
    cv_fold_idx: Optional[Sequence[int]] = None,
    seed: int = 0,
) -> List[CombinationSpec]:
    """Return the <= K_cycle highest-information UNTRIED combos (the bandit survivors).

    Dedup-vs-tried, optional cheap-screen rank (collinear-with-base dropped), per-family
    Beta posterior + bounded novelty, then the HARD K-cap. K is computed from the
    CUMULATIVE prior_k so a cycle split cannot reset the budget (R13). Deterministic
    given (specs, tried, ledger, prior_k, seed). NEVER raises except the disjointness
    tripwire (a programming error, surfaced loudly).
    """
    tried = set(tried_ids or ())
    led = dict(ledger or {})
    cands = [s for s in specs if s.combo_id not in tried]
    if not cands:
        return []
    if screen_of is not None and cv_fold_idx is not None:
        # one disjointness check is enough -- screen slices share the same fold partition
        sample = screen_of(cands[0])
        if sample is not None:
            assert_screen_disjoint(sample.screen_idx, cv_fold_idx)
    scored: List[Tuple[float, str, CombinationSpec]] = []
    for s in cands:
        sc = 0.0
        if screen_of is not None:
            cols = screen_of(s)
            if cols is not None:
                rs = screen_score(cols)
                if rs is None:
                    continue  # collinear-with-base -> dropped, never costs K (R5)
                sc = rs
        post = _family_post_mean(s.family, led)
        nov = _novelty(s.combo_id, seed)
        info = _W_SCREEN * sc + _W_POSTMEAN * post + _W_NOVELTY * nov
        scored.append((info, s.combo_id, s))
    # deterministic ordering: info desc, then combo_id for a stable tie-break
    scored.sort(key=lambda t: (-t[0], t[1]))
    k = k_cap(prior_k, eps, min_eps_eff)
    return [s for _, _, s in scored[:k]]


def build_combination_candidates(
    specs: Sequence[CombinationSpec],
    build_fn: Callable[[CombinationSpec], Optional[dict]],
) -> List[dict]:
    """Route EVERY spec through the build choke ONLY (the MF guarantee).

    Constructs NO candidate dict itself: it calls build_fn (the recalibrator MF-choke)
    and keeps only non-None results. With the PIPELINE_ENABLED sentinel absent the real
    choke returns None for every spec, so this returns [] (byte-identical NO_CANDIDATE).
    """
    out: List[dict] = []
    for s in specs:
        cand = build_fn(s)
        if cand is not None:
            out.append(cand)
    return out


__all__ = [
    "ScreenColumns", "fwer_budget_remaining", "k_cap", "screen_score",
    "assert_screen_disjoint", "enumerate_combination_specs",
    "build_combination_candidates", "cumulative_k", "eps_eff",
]
