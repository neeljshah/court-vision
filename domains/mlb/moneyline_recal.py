"""domains.mlb.moneyline_recal -- Leak-free walk-forward MLB moneyline recalibration.

PROBLEM: raw Elo P(home) collapses to ELO_MEAN baseline for teams with thin history,
producing near-uniform output (7-of-12 MLB bestbets cards share model_prob=0.4655).
Walk-forward recalibration re-sharpens probs without future-row leakage.

ALGORITHM: expanding-window Platt (logistic) or isotonic selected by OOS log-loss.
Fit strictly on rows BEFORE position i; 50-game warmup passthrough.

HONESTY: No $ / ROI / PnL field. note='calibration, not edge'. vs_close='UNPROVEN'.
OWNERSHIP: BE lane only (domains/mlb/**). NEVER touches src/ kernel/ api/ team_system/.
Propose-only hook noted in domains/mlb/predictor.py docstring (do NOT edit it).
<=300 LOC; stdlib + numpy + sklearn; ASCII only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

CALIBRATION_NOTE: str = "calibration, not edge; no $ field; vs_close=UNPROVEN"
MIN_HISTORY: int = 50
PLANTED_NULL_BRIER_TOLERANCE: float = 0.005
_EPS: float = 1e-9


def ece(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """Expected Calibration Error -- inline, no kernel import needed."""
    p, y = np.asarray(probs, dtype=float), np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(p)
    if total == 0:
        return 0.0
    val = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        n_bin = int(mask.sum())
        if n_bin == 0:
            continue
        val += (n_bin / total) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


def brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean Brier score (lower = better)."""
    return float(np.mean((np.asarray(probs, float) - np.asarray(outcomes, float)) ** 2))


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def _logloss(probs: np.ndarray, outcomes: np.ndarray) -> float:
    p = np.clip(probs, _EPS, 1.0 - _EPS)
    return float(-np.mean(outcomes * np.log(p) + (1.0 - outcomes) * np.log(1.0 - p)))


@dataclass
class RecalResult:
    """Scored output from recalibrate_bundle."""
    raw_probs: np.ndarray
    recal_probs: np.ndarray
    outcomes: np.ndarray
    dates: List[str]
    half2_raw_ece: float
    half2_recal_ece: float
    half2_raw_brier: float
    half2_recal_brier: float
    identity_ece: float        # second-pass ECE (idempotence reference)
    null_brier_excess: float   # excess Brier improvement on shuffled labels above trivial mean correction
    n_total: int
    n_half2: int
    chosen_method: str
    note: str = CALIBRATION_NOTE
    vs_close: str = "UNPROVEN"
    passes_acceptance: bool = False
    rejection_reason: str = ""
    extra: dict = field(default_factory=dict)


class WalkForwardRecal:
    """Expanding-window MLB moneyline recalibrator.

    Selects between Platt and isotonic by OOS log-loss evaluated on [half:].
    Applies the chosen method walk-forward over the full corpus.
    No future-row leak: at position i, only rows[:i] are used.
    """

    def __init__(
        self,
        min_history: int = MIN_HISTORY,
        refit_every: int = 10,
        methods: Optional[List[str]] = None,
    ) -> None:
        self.min_history = int(min_history)
        self.refit_every = max(1, int(refit_every))
        self.methods: List[str] = methods if methods is not None else ["platt", "isotonic"]

    def _wf_platt(self, p: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Walk-forward Platt scaling (LogisticRegression on logit features)."""
        n = len(p)
        out = np.empty(n, dtype=float)
        lr: Optional[LogisticRegression] = None
        next_fit = self.min_history
        for i in range(n):
            if i < self.min_history:
                out[i] = p[i]; continue
            if i >= next_fit:
                valid = np.isfinite(p[:i]) & np.isfinite(y[:i])
                if valid.sum() >= 2 and len(np.unique(y[:i][valid])) >= 2:
                    lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=200)
                    lr.fit(_logit(p[:i][valid]).reshape(-1, 1), y[:i][valid])
                next_fit = i + self.refit_every
            if lr is not None and np.isfinite(p[i]):
                out[i] = float(lr.predict_proba(_logit(np.array([p[i]])).reshape(1, 1))[0, 1])
            else:
                out[i] = p[i]
        return np.clip(out, 0.0, 1.0)

    def _wf_isotonic(self, p: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Walk-forward isotonic regression."""
        n = len(p)
        out = np.empty(n, dtype=float)
        ir = IsotonicRegression(out_of_bounds="clip")
        have = False
        next_fit = self.min_history
        for i in range(n):
            if i < self.min_history:
                out[i] = p[i]; continue
            if i >= next_fit:
                valid = np.isfinite(p[:i]) & np.isfinite(y[:i])
                if valid.any():
                    ir.fit(p[:i][valid], y[:i][valid]); have = True
                next_fit = i + self.refit_every
            out[i] = float(ir.transform([p[i]])[0]) if have and np.isfinite(p[i]) else p[i]
        return np.clip(out, 0.0, 1.0)

    def _run(self, name: str, p: np.ndarray, y: np.ndarray) -> np.ndarray:
        if name == "platt":
            return self._wf_platt(p, y)
        if name == "isotonic":
            return self._wf_isotonic(p, y)
        return np.clip(p.copy(), 0.0, 1.0)

    def fit_transform(
        self, raw_probs: Sequence[float], outcomes: Sequence[float]
    ) -> tuple[np.ndarray, str]:
        """Select best method on [half:] OOS log-loss, transform full corpus."""
        p = np.asarray(raw_probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)
        n = len(p)
        half = n // 2
        best_method, best_ll = "identity", float("inf")
        for name in self.methods:
            arr = self._run(name, p, y)
            mask = (np.arange(n) >= max(half, self.min_history)) & np.isfinite(arr) & np.isfinite(y)
            if mask.sum() < 10:
                continue
            ll = _logloss(arr[mask], y[mask])
            if ll < best_ll:
                best_ll, best_method = ll, name
        return self._run(best_method, p, y), best_method


def recalibrate_bundle(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    dates: Optional[List[str]] = None,
    *,
    min_history: int = MIN_HISTORY,
    refit_every: int = 10,
    rng_seed: int = 42,
) -> RecalResult:
    """Walk-forward recalibration pipeline with four acceptance checks.

    Acceptance (all must pass):
      1. ECE(recal) < ECE(raw) on held-out half2.
      2. Brier(recal) <= Brier(raw) + 0.001 on half2 (not meaningfully worse).
      3. Identity check: second-pass Brier worsening <= 0.001.
         Re-applying recal to its own output must not degrade a calibrated predictor.
      4. Planted-null: Brier excess over trivial mean-correction <= PLANTED_NULL_BRIER_TOLERANCE.
         Recal on shuffled labels may move probs toward the mean (trivial correction);
         it must NOT exceed that by more than the tolerance (no spurious signal).
         Stored in null_brier_excess (was null_delta_ece, renamed for accuracy).

    Returns RecalResult. No $ / ROI / PnL field.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    half = n // 2
    _dates: List[str] = dates if dates is not None else [""] * n

    recal_probs, chosen = WalkForwardRecal(min_history=min_history,
                                           refit_every=refit_every).fit_transform(p, y)
    p2, r2, y2 = p[half:], recal_probs[half:], y[half:]
    h2_raw_ece = ece(p2, y2)
    h2_recal_ece = ece(r2, y2)
    h2_raw_brier = brier(p2, y2)
    h2_recal_brier = brier(r2, y2)

    # Identity check: re-calibrating already-calibrated probs must not worsen Brier
    id_recal_probs, _ = WalkForwardRecal(min_history=min_history,
                                          refit_every=refit_every).fit_transform(recal_probs, y)
    id_ece = ece(id_recal_probs[half:], y2)
    id_brier_worsening = brier(id_recal_probs[half:], y2) - brier(r2, y2)

    # Planted-null: shuffle labels; Brier delta must not exceed trivial mean correction
    rng = np.random.default_rng(rng_seed)
    y_sh = rng.permutation(y)
    null_recal, _ = WalkForwardRecal(min_history=min_history,
                                      refit_every=refit_every).fit_transform(p, y_sh)
    null_raw_b = brier(p[half:], y_sh[half:])
    null_recal_b = brier(null_recal[half:], y_sh[half:])
    trivial = null_raw_b - brier(np.full(n - half, float(y_sh[:half].mean())), y_sh[half:])
    null_excess = (null_raw_b - null_recal_b) - trivial

    reasons: List[str] = []
    if h2_recal_ece >= h2_raw_ece:
        reasons.append(f"ECE not improved: recal={h2_recal_ece:.5f} >= raw={h2_raw_ece:.5f}")
    if h2_recal_brier > h2_raw_brier + 0.001:
        reasons.append(f"Brier worsened: {h2_recal_brier:.5f} > {h2_raw_brier:.5f}+0.001")
    if id_brier_worsening > 0.001:
        reasons.append(f"Identity check: 2nd-pass Brier worsening {id_brier_worsening:.5f} > 0.001")
    if null_excess > PLANTED_NULL_BRIER_TOLERANCE:
        reasons.append(f"Planted-null: excess {null_excess:.5f} > {PLANTED_NULL_BRIER_TOLERANCE}")

    return RecalResult(
        raw_probs=p, recal_probs=recal_probs, outcomes=y, dates=list(_dates),
        half2_raw_ece=h2_raw_ece, half2_recal_ece=h2_recal_ece,
        half2_raw_brier=h2_raw_brier, half2_recal_brier=h2_recal_brier,
        identity_ece=id_ece,
        null_brier_excess=null_excess,
        n_total=n, n_half2=n - half, chosen_method=chosen,
        passes_acceptance=len(reasons) == 0,
        rejection_reason="; ".join(reasons) if reasons else "",
        extra={
            "null_brier_delta": null_raw_b - null_recal_b,
            "trivial_correction": trivial,
            "null_excess": null_excess,
            "id_ece_worsening": id_brier_worsening,
        },
    )


__all__ = [
    "WalkForwardRecal", "recalibrate_bundle", "RecalResult",
    "ece", "brier", "CALIBRATION_NOTE", "MIN_HISTORY", "PLANTED_NULL_BRIER_TOLERANCE",
]
