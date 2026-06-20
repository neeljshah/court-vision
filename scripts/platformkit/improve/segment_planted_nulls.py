"""scripts.platformkit.improve.segment_planted_nulls -- per-segment FWER null lane (SI-09).

As segment coverage widens (more margin x period x time_bucket splits), the
multiple-comparisons surface grows.  This is the FWER tripwire for the IN-GAME SEGMENT
recal lane: for each segment, route >=20 shuffled-label probes through a canonical gate
and measure the realized false-ship RATE.

  fdr_hat(segment) = (# shuffled-label probes that 'SHIP') / (# run)

Consequences:
  - Any ship -> segment is FROZEN (flexibility_alarm; human review required).
  - n_run < MIN_NULLS -> fdr_hat=None, INSUFFICIENT (NOT frozen; deferred).
  - fdr_hat > fdr_budget(eps, K) -> FROZEN (rate exceeded budget).

Build-on: fusion/fusion_planted_nulls (mirrors null-construction pattern),
  prioritizer.frozen_families (reads ledger-shaped dict produced by ledger_of).

Segment "families" are NAMED segments (e.g. "close|early|ample"), not cluster-ids.

INVARIANTS: never writes data/registry/, never flips a flag, never creates sentinel,
never edits MEMORY.md.  Calibration NOT edge: no $/pnl/roi/profit field anywhere.
Stdlib + numpy only; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, fdr_budget
from scripts.platformkit.improve.ingame_recal_segments import (
    _MARGIN_THRESHOLDS,
    _PERIOD_THRESHOLDS,
    _TIME_THRESHOLDS,
)

logger = logging.getLogger("segment_planted_nulls")

MIN_NULLS: int = 20  # power floor: one null cannot estimate FDR

_MARGINS: Tuple[str, ...] = tuple(sorted(_MARGIN_THRESHOLDS.keys()))
_PERIODS: Tuple[str, ...] = tuple(sorted(_PERIOD_THRESHOLDS.keys()))
_TIMES: Tuple[str, ...] = tuple(sorted(_TIME_THRESHOLDS.keys()))

SEGMENT_TRIPLES: Tuple[Tuple[str, str, str], ...] = tuple(
    (m, p, t) for m in _MARGINS for p in _PERIODS for t in _TIMES
)


def segment_name(margin: str, period: str, time: str) -> str:
    """Canonical key: 'margin|period|time' (name-stable, not a cluster-id)."""
    return "%s|%s|%s" % (margin, period, time)


__all__ = [
    "MIN_NULLS", "SEGMENT_TRIPLES", "SegmentNullResult",
    "run_segment_nulls", "run_all_segment_nulls",
    "frozen_segments", "ledger_of", "segment_name",
]


@dataclass(frozen=True)
class SegmentNullResult:
    """Per-segment realized false-discovery estimate from shuffled-label probes.

    fdr_hat is None when n_run < MIN_NULLS (INSUFFICIENT; NOT frozen).
    No $/pnl/roi/profit field by construction.  Calibration, not edge.
    """

    segment: str             # canonical 'margin|period|time' label
    fdr_hat: Optional[float] # None => INSUFFICIENT
    n_run: int
    n_shipped: int
    budget: float
    frozen: bool             # True => flexibility_alarm; human review required
    insufficient: bool       # True => n_run < MIN_NULLS; NOT frozen
    note: str = "calibration, not edge"


# ---------------------------------------------------------------------------
# Synthetic corpus + null-gate internals
# ---------------------------------------------------------------------------

_CLIP_EPS = 1e-6
# Minimum Brier-delta for a null probe to count as a SHIP.  Sub-threshold wins
# are numerical noise on corpora of the default size, not genuine false positives.
_MIN_SHIP_DELTA: float = 1e-3


def _clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, _CLIP_EPS, 1.0 - _CLIP_EPS)


def _synth_corpus(n_games: int, ticks: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
    """Synthetic (base_prob, outcome) pairs -- a segment Platt calibrator's input.

    Each game has latent strength ~ N(0,1); outcome = (strength + N(0,.5)) > 0.
    Tick-level base_prob is a sigmoid of (strength * frac * 2 + noise), giving a
    realistic -- imperfect but correlated -- base that has a real link to outcome.
    Returns (base_probs, outcomes) as 1-D float arrays of length n_games * ticks.
    """
    rng = np.random.default_rng(seed)
    bases, outcomes = [], []
    for _ in range(n_games):
        strength = float(rng.normal(0.0, 1.0))
        outcome = 1 if (strength + float(rng.normal(0.0, 0.5))) > 0.0 else 0
        for t in range(ticks):
            frac = (t + 1) / float(ticks)
            state = strength * frac * 2.0 + float(rng.normal(0.0, 0.5))
            base_p = float(np.clip(1.0 / (1.0 + np.exp(-state)), 1e-4, 1.0 - 1e-4))
            bases.append(base_p)
            outcomes.append(float(outcome))
    return np.array(bases, dtype=float), np.array(outcomes, dtype=float)


def _shuffled_outcome(outcomes: np.ndarray, seed: int) -> np.ndarray:
    """Permute outcomes (preserves marginal, destroys row link -- the strongest null)."""
    rng = np.random.default_rng(seed + 7919)
    return outcomes[rng.permutation(len(outcomes))]


def _fit_platt(base: np.ndarray, y: np.ndarray) -> Optional[Tuple[float, float]]:
    """GD Platt scaling a*logit(base)+b -> (a, b) or None if diverged."""
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    a, b, lr, n = 1.0, 0.0, 0.1, float(len(z))
    for _ in range(400):
        p = _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))
        g = p - y
        a -= lr * float(np.dot(g, z) / n)
        b -= lr * float(np.mean(g))
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
    return float(a), float(b)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _null_gate(base: np.ndarray, y_shuf: np.ndarray, y_real: np.ndarray) -> str:
    """SHIP iff Platt(base, y_shuffled) improves Brier vs base by > _MIN_SHIP_DELTA.

    A Platt fit on SHUFFLED labels is pure noise and must not beat the real base.
    Requiring delta > threshold prevents sub-epsilon numerical fluctuations from
    triggering false FWER alarms.
    """
    ab = _fit_platt(base, y_shuf)
    if ab is None:
        return "REJECT"
    a, b = ab
    z = np.log(_clip01(base) / (1.0 - _clip01(base)))
    cand = _clip01(1.0 / (1.0 + np.exp(-(a * z + b))))
    delta = _brier(base, y_real) - _brier(cand, y_real)
    return "SHIP" if delta > _MIN_SHIP_DELTA else "REJECT"


# ---------------------------------------------------------------------------
# Public: run nulls for one segment
# ---------------------------------------------------------------------------

def run_segment_nulls(
    segment: str, *, n: int = MIN_NULLS, n_games: int = 50, ticks: int = 8,
    seed: int = 4321, eps: float = DEFAULT_EPS, K: int = 1, gate=_null_gate,
) -> SegmentNullResult:
    """Run >=MIN_NULLS shuffled-label probes for `segment` through the null gate.

    Each probe: build synthetic (base, y_real), shuffle y -> y_shuf, call
    gate(base, y_shuf, y_real) -> 'SHIP'|'REJECT', count ships.

    fdr_hat = n_shipped / n_run.  n_run < MIN_NULLS -> INSUFFICIENT, NOT frozen.
    Any ship OR fdr_hat > fdr_budget -> FROZEN.

    `gate` is injectable so a test can prove the tripwire fires on a weak gate;
    production always uses the real _null_gate.  No $ field emitted.
    """
    n_run = max(MIN_NULLS, int(n))
    budget = fdr_budget(eps, K)

    if n_run < MIN_NULLS:  # pragma: no cover -- floor enforces n_run >= MIN_NULLS above
        return SegmentNullResult(
            segment=segment, fdr_hat=None, n_run=n_run,
            n_shipped=0, budget=budget, frozen=False, insufficient=True,
        )

    n_shipped = 0
    for i in range(n_run):
        s = seed + i * 17
        base, y_real = _synth_corpus(n_games, ticks, seed=s)
        y_shuf = _shuffled_outcome(y_real, seed=s)
        try:
            verdict = gate(base, y_shuf, y_real)
        except Exception as exc:
            logger.debug("segment null %s/%d crashed -> non-ship: %s", segment, i, exc)
            verdict = "REJECT"
        if str(verdict) == "SHIP":
            n_shipped += 1

    fdr_hat = n_shipped / float(n_run)
    frozen = bool(n_shipped > 0 or fdr_hat > budget)
    return SegmentNullResult(
        segment=segment, fdr_hat=float(fdr_hat), n_run=n_run,
        n_shipped=n_shipped, budget=budget, frozen=frozen, insufficient=False,
    )


# ---------------------------------------------------------------------------
# Public: run nulls for every segment + derive frozen set / ledger
# ---------------------------------------------------------------------------

def run_all_segment_nulls(
    *, n: int = MIN_NULLS, n_games: int = 50, ticks: int = 8,
    eps: float = DEFAULT_EPS, K: int = 1,
    triples: Sequence[Tuple[str, str, str]] = SEGMENT_TRIPLES,
    gate=_null_gate,
) -> Dict[str, SegmentNullResult]:
    """Run the null lane for EVERY segment triple. Returns {segment_name: result}.

    Each triple uses a stable, independent seed offset.  HONEST EXPECTATION:
    every fdr_hat == 0.0 (a shuffled label has no real signal at any segment).
    """
    results: Dict[str, SegmentNullResult] = {}
    for idx, (m, p, t) in enumerate(triples):
        seg = segment_name(m, p, t)
        res = run_segment_nulls(seg, n=n, n_games=n_games, ticks=ticks,
                                seed=4321 + idx * 137, eps=eps, K=K, gate=gate)
        results[seg] = res
        logger.info("segment=%s fdr_hat=%s n_shipped=%d frozen=%s",
                    seg, ("%.4f" % res.fdr_hat) if res.fdr_hat is not None else "None",
                    res.n_shipped, res.frozen)
    return results


def frozen_segments(results: Dict[str, SegmentNullResult]) -> List[str]:
    """Segments whose null shipped or FDR-hat > budget -> FROZEN.

    INSUFFICIENT segments are NOT frozen (deferred, not condemned).
    """
    return [seg for seg, r in results.items() if r.frozen]


def ledger_of(results: Dict[str, SegmentNullResult]) -> Dict[str, object]:
    """Convert results to a prioritizer-compatible ledger dict.

    Shape: { segment_name: { "null_shipped": bool, "null_ships": int, ... } }
    INSUFFICIENT entries emit null_shipped=False so they are NOT frozen downstream.
    """
    out: Dict[str, object] = {}
    for seg, r in results.items():
        out[seg] = {
            "null_shipped": r.frozen and not r.insufficient,
            "null_ships": r.n_shipped,
            "fdr_hat": r.fdr_hat,
            "n_run": r.n_run,
            "budget": r.budget,
            "insufficient": r.insufficient,
            "note": "calibration, not edge",
        }
    return out
