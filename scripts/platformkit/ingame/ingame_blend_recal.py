"""scripts.platformkit.ingame.ingame_blend_recal -- post-blend per-segment
isotonic recalibration so Q4 (and other time-bucket) in-game ECE stops drifting.

DESIGN
------
After the blend surface (eval_gate.ingame_blend) produces a blended probability
for every state, a single global IsotonicRegression is not enough: Q1 states
(score still close, high uncertainty) and Q3 states (margin decisive, lower
uncertainty) have very different calibration surfaces. A per-time-bucket
IsotonicRegression addresses this segment-by-segment.

PROTOCOL (identical to the crossval design -- leak-free by construction)
  * Split the available states into disjoint halves A and B by game_id parity
    (even game_ids in A, odd in B). Game-level split prevents within-game leakage.
  * Fit the blend weight surface on A; apply it to produce blended probs on A.
  * Fit one IsotonicRegression per time-bucket (0..n_time-1) on (blended probs, outcomes) from A.
  * Evaluate on B: apply the SAME blend surface and the SAME fitted regressors to B's states.
  * Verdict: per-quarter ECE(recal) < ECE(raw) AND Brier(recal) <= Brier(raw) + TOLERANCE.

PLANTED-NULL GUARD
  * Shuffle labels in the FIT pool (A) before fitting the regressors.
  * A legitimate isotonic fitter on shuffled labels produces near-identity output
    (monotone fit on noise). Any ECE improvement claim on B after shuffled-label
    fitting is an artifact -- the null check must reject (i.e., NOT claim improvement).

HONEST REJECT
  * If ECE(recal) >= ECE(raw) on any quarter the verdict for that segment is REJECT.
  * The overall verdict is SHIP only if ALL quarters improve; PARTIAL if >=1 but not all;
    NOT_IMPROVED if none do.
  * An honest REJECT is a SUCCESS (confirms ECE drift is not correctable by isotonic alone).

No $ anywhere; verdict = CALIBRATION. numpy + sklearn + stdlib only.
<=300 LOC; ASCII-only; INVARIANTS: never edit src/ or kernel/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import (
    WeightSurface,
    blended_predictions,
    fit_weight_surface,
    time_bucket,
)
from scripts.platformkit.eval_gate.scoring import brier, ece

try:
    from sklearn.isotonic import IsotonicRegression as _IsoReg
    _SKLEARN = True
except ImportError:  # fallback: identity (no sklearn)
    _SKLEARN = False
    _IsoReg = None  # type: ignore

_TOLERANCE = 1e-6          # brier(recal) may be worse by at most this epsilon
_MIN_SEGMENT = 20          # minimum samples per bucket to fit; else identity
_N_BUCKETS = 4             # matches WeightSurface.n_time


# ---------------------------------------------------------------------------
# isotonic wrapper
# ---------------------------------------------------------------------------

class _IdentityReg:
    """Stand-in when sklearn is absent or the bucket is too small to fit."""
    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x, dtype=float)


def _fit_iso(p: np.ndarray, y: np.ndarray) -> object:
    """Fit an IsotonicRegression on (p, y); fall back to identity on thin sets."""
    if len(p) < _MIN_SEGMENT or not _SKLEARN:
        return _IdentityReg()
    reg = _IsoReg(out_of_bounds="clip")
    reg.fit(p, y)
    return reg


def _predict_iso(reg: object, p: np.ndarray) -> np.ndarray:
    out = reg.predict(np.asarray(p, dtype=float))
    return np.clip(np.asarray(out, dtype=float), 0.0, 1.0)


# ---------------------------------------------------------------------------
# SegmentRecalibrator: per-time-bucket iso regressors
# ---------------------------------------------------------------------------

@dataclass
class SegmentRecalibrator:
    """Holds one fitted IsotonicRegression per time-bucket (0..n_buckets-1)."""
    n_buckets: int = _N_BUCKETS
    regs: Dict[int, object] = field(default_factory=dict)

    def predict(self, states: List[dict], blended: np.ndarray) -> np.ndarray:
        """Apply per-bucket regressor to blended probs; returns recalibrated array."""
        out = blended.copy()
        for b in range(self.n_buckets):
            mask = np.array([
                time_bucket(s["seconds_remaining"], n=self.n_buckets) == b
                for s in states
            ])
            if not mask.any():
                continue
            reg = self.regs.get(b, _IdentityReg())
            out[mask] = _predict_iso(reg, blended[mask])
        return out


def fit_recal(states: List[dict], surf: WeightSurface,
              rng: Optional[np.random.Generator] = None,
              shuffle_labels: bool = False) -> SegmentRecalibrator:
    """Fit per-bucket isotonic regressors on `states` using the pre-fitted `surf`.

    Parameters
    ----------
    states       : in-game state dicts (keys: p0, p_live, seconds_remaining, outcome, ...)
    surf         : blend weight surface (fit on the SAME split as states; A-split)
    rng          : optional RNG for shuffling (planted-null test only)
    shuffle_labels : if True, shuffle outcomes before fitting (planted-null test)
    """
    blended = blended_predictions(states, surf)
    outcomes = np.array([s["outcome"] for s in states], dtype=float)
    if shuffle_labels:
        if rng is None:
            rng = np.random.default_rng(seed=42)
        rng.shuffle(outcomes)

    recal = SegmentRecalibrator(n_buckets=_N_BUCKETS)
    for b in range(_N_BUCKETS):
        mask = np.array([
            time_bucket(s["seconds_remaining"], n=_N_BUCKETS) == b
            for s in states
        ])
        if not mask.any():
            recal.regs[b] = _IdentityReg()
            continue
        recal.regs[b] = _fit_iso(blended[mask], outcomes[mask])
    return recal


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _per_quarter_metrics(states: List[dict], raw: np.ndarray,
                         recal_p: np.ndarray) -> Dict[str, Dict]:
    """Per-time-bucket ECE and Brier for raw vs recal, keyed by bucket index."""
    out: Dict[str, Dict] = {}
    y_arr = np.array([s["outcome"] for s in states], dtype=float)
    for b in range(_N_BUCKETS):
        mask = np.array([
            time_bucket(s["seconds_remaining"], n=_N_BUCKETS) == b
            for s in states
        ])
        if not mask.any():
            continue
        y_b = y_arr[mask]
        raw_b = raw[mask]
        rec_b = recal_p[mask]
        n = int(mask.sum())
        out[f"bucket_{b}"] = {
            "n": n,
            "ece_raw": round(float(ece(raw_b, y_b)), 6),
            "ece_recal": round(float(ece(rec_b, y_b)), 6),
            "brier_raw": round(float(brier(raw_b, y_b)), 6),
            "brier_recal": round(float(brier(rec_b, y_b)), 6),
            "ece_improved": bool(ece(rec_b, y_b) < ece(raw_b, y_b)),
            "brier_not_worse": bool(
                brier(rec_b, y_b) <= brier(raw_b, y_b) + _TOLERANCE
            ),
        }
    return out


def _decide_verdict(per_q: Dict[str, Dict]) -> str:
    """SHIP: all buckets ECE improves AND Brier not worse.
    PARTIAL: >=1 bucket improves. NOT_IMPROVED: none improve.
    """
    if not per_q:
        return "INSUFFICIENT_DATA"
    improved = [v["ece_improved"] for v in per_q.values()]
    brier_ok = [v["brier_not_worse"] for v in per_q.values()]
    if all(improved) and all(brier_ok):
        return "SHIP"
    if any(improved):
        return "PARTIAL"
    return "NOT_IMPROVED"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

@dataclass
class RecalResult:
    verdict: str
    per_bucket: Dict[str, Dict] = field(default_factory=dict)
    brier_raw_pooled: float = 0.0
    brier_recal_pooled: float = 0.0
    ece_raw_pooled: float = 0.0
    ece_recal_pooled: float = 0.0
    n_fit: int = 0
    n_eval: int = 0
    planted_null: bool = False

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "planted_null": self.planted_null,
            "n_fit": self.n_fit,
            "n_eval": self.n_eval,
            "brier_raw_pooled": round(self.brier_raw_pooled, 6),
            "brier_recal_pooled": round(self.brier_recal_pooled, 6),
            "ece_raw_pooled": round(self.ece_raw_pooled, 6),
            "ece_recal_pooled": round(self.ece_recal_pooled, 6),
            "per_bucket": self.per_bucket,
            "honesty": "CALIBRATION only; no dollar edge implied",
        }


def split_ab(states: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Split states into A (even game_id) and B (odd game_id)."""
    a = [s for s in states if s["game_id"] % 2 == 0]
    b = [s for s in states if s["game_id"] % 2 == 1]
    return a, b


def eval_recal(states_a: List[dict], states_b: List[dict],
               shuffle_labels: bool = False,
               rng: Optional[np.random.Generator] = None,
               min_cell: int = 20) -> RecalResult:
    """Full pipeline: fit blend+recal on A, evaluate on B.

    Parameters
    ----------
    states_a : fit pool (blend surface + iso regressors trained here)
    states_b : eval pool (never touched during fit)
    shuffle_labels : True -> planted-null mode (outcomes shuffled on A)
    rng      : optional RNG (for planted-null reproducibility)
    min_cell : passed to fit_weight_surface (sparse cells fall back to prior)
    """
    if not states_a or not states_b:
        return RecalResult(verdict="INSUFFICIENT_DATA")

    # 1. Fit blend surface on A
    surf = fit_weight_surface(states_a, min_cell=min_cell)

    # 2. Fit per-bucket isotonic regressors on A (optionally shuffled labels)
    recal = fit_recal(states_a, surf, rng=rng, shuffle_labels=shuffle_labels)

    # 3. Apply to B: blended (raw) and recalibrated
    raw_b = blended_predictions(states_b, surf)
    recal_b = recal.predict(states_b, raw_b)

    # 4. Pooled metrics
    y_b = np.array([s["outcome"] for s in states_b], dtype=float)
    br_raw = float(brier(raw_b, y_b))
    br_rec = float(brier(recal_b, y_b))
    ec_raw = float(ece(raw_b, y_b))
    ec_rec = float(ece(recal_b, y_b))

    # 5. Per-bucket metrics
    per_q = _per_quarter_metrics(states_b, raw_b, recal_b)

    # 6. Verdict
    verdict = _decide_verdict(per_q)

    return RecalResult(
        verdict=verdict,
        per_bucket=per_q,
        brier_raw_pooled=br_raw,
        brier_recal_pooled=br_rec,
        ece_raw_pooled=ec_raw,
        ece_recal_pooled=ec_rec,
        n_fit=len(states_a),
        n_eval=len(states_b),
        planted_null=shuffle_labels,
    )


def run(states: List[dict], min_cell: int = 20,
        rng: Optional[np.random.Generator] = None) -> RecalResult:
    """Convenience: split `states` into A/B by game_id parity, then run eval_recal."""
    a, b = split_ab(states)
    if not a or not b:
        return RecalResult(verdict="INSUFFICIENT_DATA")
    return eval_recal(a, b, min_cell=min_cell, rng=rng)
