"""scripts.platformkit.ingame.ingame_served_reliability -- held-out reliability
scoreboard for the SERVED (post-recal) in-game number.

PURPOSE
-------
After the blend surface + isotonic recalibration pipeline produces a served
probability, we need an independent reliability scoreboard that proves:
  (a) ECE(served) <= ECE(raw_blend) + EPS per bucket on held-out data, OR
  (b) Honestly REJECTs (the recal worsened calibration) -- not fabricated green.

This is NOT the same as ingame_blend_recal.py, which proves recal improves ECE
in aggregate. This module scores the SERVED number as a reliability diagnostic:
if the live stack has a recal map loaded, is that map helping or hurting?

PROTOCOL (leak-free by construction)
  * Split states by game_id parity (A = even, B = odd) -- same as blend_recal.
  * Fit blend surface on A; fit per-bucket isotonic regressors on A.
  * The SERVED probability is recal(blend(state, surf)) on B.
  * Raw blend is blend(state, surf) on B (no recal applied).
  * Compare ECE and Brier per time bucket and pooled.

VERDICTS
  PASS   -- ECE(served) <= ECE(raw_blend) + EPS per bucket AND Brier non-worse
  REJECT -- served ECE is worse than raw on >= 1 bucket (honest reject, no suppress)
  PARTIAL -- some buckets pass, some reject
  INSUFFICIENT_DATA -- fewer than MIN_EVAL_TOTAL samples in eval pool

HONEST REJECT
  A REJECT is a valid, important output. It means recalibration is not helping
  (or actively hurting) calibration on this data. Do not suppress or paper over it.

STALE-NEVER-GREEN: the verdict is computed fresh every call; no cached result.

No $ anywhere; verdict = CALIBRATION only. numpy + sklearn + stdlib only.
<=300 LOC; ASCII-only; invariants: never edit src/ or kernel/.
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
from scripts.platformkit.ingame.ingame_blend_recal import (
    SegmentRecalibrator,
    fit_recal,
    split_ab,
)

_EPS = 1e-4          # ECE(served) may exceed ECE(raw) by at most this per bucket
_BRIER_TOL = 1e-6   # Brier(served) may exceed Brier(raw) by at most this
_MIN_EVAL_TOTAL = 30 # fewer samples -> INSUFFICIENT_DATA
_N_BUCKETS = 4       # time buckets (matches WeightSurface.n_time / blend_recal)


# ---------------------------------------------------------------------------
# Bucket-level scoring
# ---------------------------------------------------------------------------

def _bucket_metrics(
    states: List[dict],
    raw: np.ndarray,
    served: np.ndarray,
) -> Dict[str, Dict]:
    """Per-time-bucket ECE and Brier for raw vs served, keyed by 'bucket_N'."""
    out: Dict[str, Dict] = {}
    y = np.array([s["outcome"] for s in states], dtype=float)
    for b in range(_N_BUCKETS):
        mask = np.array([
            time_bucket(s["seconds_remaining"], n=_N_BUCKETS) == b
            for s in states
        ])
        if not mask.any():
            continue
        y_b, raw_b, srv_b = y[mask], raw[mask], served[mask]
        n = int(mask.sum())
        ece_raw = float(ece(raw_b, y_b))
        ece_srv = float(ece(srv_b, y_b))
        brier_raw = float(brier(raw_b, y_b))
        brier_srv = float(brier(srv_b, y_b))
        out[f"bucket_{b}"] = {
            "n": n,
            "ece_raw": round(ece_raw, 6),
            "ece_served": round(ece_srv, 6),
            "brier_raw": round(brier_raw, 6),
            "brier_served": round(brier_srv, 6),
            "ece_pass": bool(ece_srv <= ece_raw + _EPS),
            "brier_not_worse": bool(brier_srv <= brier_raw + _BRIER_TOL),
        }
    return out


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

def _decide(per_bucket: Dict[str, Dict], n_eval: int) -> str:
    """Derive verdict from per-bucket results."""
    if n_eval < _MIN_EVAL_TOTAL or not per_bucket:
        return "INSUFFICIENT_DATA"
    passes = [v["ece_pass"] and v["brier_not_worse"] for v in per_bucket.values()]
    if all(passes):
        return "PASS"
    if any(passes):
        return "PARTIAL"
    return "REJECT"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ServedReliabilityResult:
    """Output of the served reliability scoreboard."""
    verdict: str                          # PASS / REJECT / PARTIAL / INSUFFICIENT_DATA
    per_bucket: Dict[str, Dict] = field(default_factory=dict)
    ece_raw_pooled: float = 0.0
    ece_served_pooled: float = 0.0
    brier_raw_pooled: float = 0.0
    brier_served_pooled: float = 0.0
    n_fit: int = 0
    n_eval: int = 0
    injected_bad: bool = False            # True when test plants a worse recal map

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "n_fit": self.n_fit,
            "n_eval": self.n_eval,
            "ece_raw_pooled": round(self.ece_raw_pooled, 6),
            "ece_served_pooled": round(self.ece_served_pooled, 6),
            "brier_raw_pooled": round(self.brier_raw_pooled, 6),
            "brier_served_pooled": round(self.brier_served_pooled, 6),
            "per_bucket": self.per_bucket,
            "injected_bad": self.injected_bad,
            "honesty": "CALIBRATION only; no dollar edge implied",
        }


# ---------------------------------------------------------------------------
# Core scoreboard
# ---------------------------------------------------------------------------

def run_scoreboard(
    states_a: List[dict],
    states_b: List[dict],
    recal: Optional[SegmentRecalibrator] = None,
    min_cell: int = 20,
    injected_bad: bool = False,
) -> ServedReliabilityResult:
    """Fit blend on A, score SERVED vs RAW on B.

    Parameters
    ----------
    states_a     : fit pool (blend surface + recal regressors trained here)
    states_b     : eval pool (never touched during fit; held-out)
    recal        : optional pre-fitted SegmentRecalibrator; if None, one is fit on A
    min_cell     : passed to fit_weight_surface
    injected_bad : flag passed through to result (for test transparency)
    """
    if not states_a or not states_b:
        return ServedReliabilityResult(verdict="INSUFFICIENT_DATA")
    if len(states_b) < _MIN_EVAL_TOTAL:
        return ServedReliabilityResult(
            verdict="INSUFFICIENT_DATA",
            n_fit=len(states_a),
            n_eval=len(states_b),
        )

    # Fit blend surface on A
    surf = fit_weight_surface(states_a, min_cell=min_cell)

    # Fit or accept recal on A
    if recal is None:
        recal = fit_recal(states_a, surf)

    # Produce RAW blend and SERVED (post-recal) on B
    raw_b = blended_predictions(states_b, surf)
    served_b = recal.predict(states_b, raw_b)

    # Pooled metrics
    y_b = np.array([s["outcome"] for s in states_b], dtype=float)
    ece_raw = float(ece(raw_b, y_b))
    ece_srv = float(ece(served_b, y_b))
    brier_raw = float(brier(raw_b, y_b))
    brier_srv = float(brier(served_b, y_b))

    # Per-bucket metrics
    per_bucket = _bucket_metrics(states_b, raw_b, served_b)

    verdict = _decide(per_bucket, n_eval=len(states_b))

    return ServedReliabilityResult(
        verdict=verdict,
        per_bucket=per_bucket,
        ece_raw_pooled=ece_raw,
        ece_served_pooled=ece_srv,
        brier_raw_pooled=brier_raw,
        brier_served_pooled=brier_srv,
        n_fit=len(states_a),
        n_eval=len(states_b),
        injected_bad=injected_bad,
    )


def run(
    states: List[dict],
    min_cell: int = 20,
) -> ServedReliabilityResult:
    """Convenience: split states by game_id parity then score served reliability."""
    a, b = split_ab(states)
    if not a or not b:
        return ServedReliabilityResult(verdict="INSUFFICIENT_DATA")
    return run_scoreboard(a, b, min_cell=min_cell)
