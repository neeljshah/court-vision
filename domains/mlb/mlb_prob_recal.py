"""domains.mlb.mlb_prob_recal -- MLB win-prob recalibrator (Platt/isotonic).

DISTINCT from moneyline_recal.py (which uses a walk-forward per-step refit).
This module does a CLEAN HALF-SPLIT: fit on half1 (train), evaluate on half2 (eval),
and -- iff the gate passes -- ship a serve-time recal_prob() callable.
Root cause: Elo probs collapse to a flat prior (~0.4655/0.5345) for thin-history teams.
Platt/isotonic on the full-corpus train half resharpens the served win-probs.

Gate (all must pass; else falls back to IDENTITY / no-harm):
  1. ECE(recal) < ECE(raw) on half2.
  2. Brier(recal) <= Brier(raw) + 0.001 on half2.
  3. Identity check: applying recal to already-recal probs Brier worsening <= 0.001.
  4. Planted-null: Brier excess over trivial mean-correction <= NULL_BRIER_TOL.

Absent corpus -> identity passthrough, no error raised.
No $ / ROI / PnL field. CALIBRATION not edge. vs_close = UNPROVEN. <=300 LOC.
OWNERSHIP: BE lane only. NEVER touches src/ kernel/ api/ team_system/.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

CALIBRATION_NOTE = "calibration, not edge; no $ field; vs_close=UNPROVEN"
NULL_BRIER_TOL = 0.005
_EPS = 1e-9


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    p, y = np.asarray(p, float), np.asarray(y, float)
    if len(p) == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    n, val = len(p), 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        nb = int(mask.sum())
        if nb:
            val += (nb / n) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, float), _EPS, 1.0 - _EPS)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


def _logit(p: np.ndarray) -> np.ndarray:
    c = np.clip(np.asarray(p, float), _EPS, 1.0 - _EPS)
    return np.log(c / (1.0 - c))


class HalfSplitRecal:
    """Fit Platt or isotonic on a training split; apply at serve time.

    Selects the family with lower log-loss on the last 20% of the train split.
    Falls back to IDENTITY if the corpus is too thin or single-class.
    """

    def __init__(self, min_train: int = 50) -> None:
        self.min_train = int(min_train)
        self._method = "identity"
        self._lr: Optional[LogisticRegression] = None
        self._ir: Optional[IsotonicRegression] = None
        self._fitted = False

    def fit(self, p_tr: Sequence[float], y_tr: Sequence[float]) -> str:
        p = np.asarray(p_tr, float); y = np.asarray(y_tr, float)
        ok = np.isfinite(p) & np.isfinite(y)
        p, y = p[ok], y[ok]
        if len(p) < self.min_train or len(np.unique(y)) < 2:
            self._method = "identity"; self._fitted = True; return "identity"
        cut = max(int(0.8 * len(p)), self.min_train)
        pf, yf, pv, yv = p[:cut], y[:cut], p[cut:], y[cut:]
        best, best_ll = "identity", _logloss(pv, yv)
        for name in ("platt", "isotonic"):
            if len(np.unique(yf)) < 2:
                continue
            try:
                if name == "platt":
                    lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=300)
                    lr.fit(_logit(pf).reshape(-1, 1), yf)
                    cand = np.clip(lr.predict_proba(_logit(pv).reshape(-1, 1))[:, 1], 0, 1)
                else:
                    ir = IsotonicRegression(out_of_bounds="clip")
                    ir.fit(pf, yf)
                    cand = np.clip(ir.transform(pv), 0, 1)
                ll = _logloss(cand, yv)
                if ll < best_ll - _EPS:
                    best_ll, best = ll, name
            except Exception:  # noqa: BLE001
                continue
        # Refit on ALL train data with the chosen family
        if best == "platt":
            self._lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=300)
            self._lr.fit(_logit(p).reshape(-1, 1), y)
        elif best == "isotonic":
            self._ir = IsotonicRegression(out_of_bounds="clip")
            self._ir.fit(p, y)
        self._method = best; self._fitted = True
        return best

    def transform(self, p_new: Sequence[float]) -> np.ndarray:
        arr = np.clip(np.asarray(p_new, float), 0.0, 1.0)
        if not self._fitted or self._method == "identity":
            return arr.copy()
        if self._method == "platt" and self._lr is not None:
            return np.clip(self._lr.predict_proba(_logit(arr).reshape(-1, 1))[:, 1], 0, 1)
        if self._method == "isotonic" and self._ir is not None:
            return np.clip(self._ir.transform(arr), 0, 1)
        return arr.copy()

    def recal_one(self, p: float) -> float:
        return float(np.clip(self.transform([float(p)])[0], 0.0, 1.0))


@dataclass
class ProbRecalResult:
    """Output of fit_and_gate. No $ / ROI / PnL field."""
    raw_probs: np.ndarray
    recal_probs: np.ndarray
    outcomes: np.ndarray
    half2_raw_ece: float
    half2_recal_ece: float
    half2_raw_brier: float
    half2_recal_brier: float
    id_brier_worsening: float
    null_brier_excess: float
    n_train: int
    n_eval: int
    chosen_method: str
    ship: bool
    rejection_reason: str
    note: str = CALIBRATION_NOTE
    vs_close: str = "UNPROVEN"
    extra: Dict = field(default_factory=dict)


def fit_and_gate(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    *,
    min_train: int = 50,
    rng_seed: int = 42,
) -> ProbRecalResult:
    """Fit on half1; gate on half2. Returns ProbRecalResult (no $ field)."""
    p = np.asarray(raw_probs, float); y = np.asarray(outcomes, float)
    n = len(p); half = n // 2
    p1, y1, p2, y2 = p[:half], y[:half], p[half:], y[half:]
    cal = HalfSplitRecal(min_train=min_train)
    method = cal.fit(p1, y1)
    r2 = cal.transform(p2)
    h2_raw_ece = _ece(p2, y2); h2_recal_ece = _ece(r2, y2)
    h2_raw_b = _brier(p2, y2); h2_recal_b = _brier(r2, y2)
    # Identity check: recal of recal must not worsen Brier
    cal2 = HalfSplitRecal(min_train=min_train); cal2.fit(p1, y1)
    id_worse = _brier(cal2.transform(r2), y2) - h2_recal_b
    # Planted-null
    rng = np.random.default_rng(rng_seed); y_sh = rng.permutation(y)
    cal_n = HalfSplitRecal(min_train=min_train); cal_n.fit(p1, y_sh[:half])
    null_raw = _brier(p2, y_sh[half:]); null_recal = _brier(cal_n.transform(p2), y_sh[half:])
    trivial = null_raw - _brier(np.full(n - half, float(y_sh[:half].mean())), y_sh[half:])
    null_excess = (null_raw - null_recal) - trivial
    reasons: List[str] = []
    if h2_recal_ece >= h2_raw_ece:
        reasons.append(f"ECE not improved: {h2_recal_ece:.5f}>={h2_raw_ece:.5f}")
    if h2_recal_b > h2_raw_b + 0.001:
        reasons.append(f"Brier worsened: {h2_recal_b:.5f}>{h2_raw_b:.5f}+0.001")
    if id_worse > 0.001:
        reasons.append(f"Identity check: {id_worse:.5f}>0.001")
    if null_excess > NULL_BRIER_TOL:
        reasons.append(f"Planted-null: {null_excess:.5f}>{NULL_BRIER_TOL}")
    ship = not reasons
    recal_full = np.concatenate([p1, r2]) if ship else p.copy()
    return ProbRecalResult(
        raw_probs=p, recal_probs=recal_full, outcomes=y,
        half2_raw_ece=h2_raw_ece, half2_recal_ece=h2_recal_ece,
        half2_raw_brier=h2_raw_b, half2_recal_brier=h2_recal_b,
        id_brier_worsening=id_worse, null_brier_excess=null_excess,
        n_train=half, n_eval=n - half, chosen_method=method,
        ship=ship, rejection_reason="; ".join(reasons),
        extra={"trivial_null_correction": float(trivial)},
    )


class MLBProbRecal:
    """Serve-time recalibrator. Falls back to identity if corpus absent or gate fails."""

    def __init__(
        self, cal: Optional[HalfSplitRecal], method: str,
        gate: Optional[ProbRecalResult],
    ) -> None:
        self._cal = cal; self._method = method; self._gate = gate
        self._active = cal is not None and gate is not None and gate.ship

    @classmethod
    def from_arrays(
        cls, raw_probs: Sequence[float], outcomes: Sequence[float], *, min_train: int = 50,
    ) -> "MLBProbRecal":
        p, y = np.asarray(raw_probs, float), np.asarray(outcomes, float)
        gate = fit_and_gate(p, y, min_train=min_train)
        cal = HalfSplitRecal(min_train=min_train)
        cal.fit(p[:len(p) // 2], y[:len(p) // 2])
        return cls(cal if gate.ship else None, gate.chosen_method if gate.ship else "identity", gate)

    @classmethod
    def from_corpus(
        cls, games_df=None, *, repo_root: Optional[Path] = None, min_train: int = 50,
    ) -> "MLBProbRecal":
        """Build from the MLB games corpus. Falls back to identity if absent."""
        try:
            import pandas as pd  # noqa: PLC0415
            if games_df is None:
                root = repo_root or Path(__file__).resolve().parents[2]
                p = root / "data" / "domains" / "mlb" / "games.parquet"
                if not p.exists():
                    logger.warning("mlb_prob_recal: corpus absent -- identity")
                    return cls(None, "identity", None)
                games_df = pd.read_parquet(p)
            df = games_df.copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)
            from scripts.platformkit.proof_mlb.beat_the_close_ml import _walk_forward_elo  # noqa: PLC0415
            raw_p = _walk_forward_elo(df)
            y = (df["home_runs"].to_numpy(float) > df["away_runs"].to_numpy(float)).astype(float)
            return cls.from_arrays(raw_p, y, min_train=min_train)
        except Exception:  # noqa: BLE001
            logger.warning("mlb_prob_recal: build error -- identity", exc_info=True)
            return cls(None, "identity", None)

    def recal_prob(self, p: float) -> float:
        """Recalibrate a serve-time win-prob. Identity if gate not shipped."""
        if not self._active or self._cal is None:
            return float(np.clip(p, 0.0, 1.0))
        return self._cal.recal_one(float(p))

    @property
    def active(self) -> bool:
        return self._active

    @property
    def method(self) -> str:
        return self._method

    @property
    def gate_result(self) -> Optional[ProbRecalResult]:
        return self._gate

    def summary(self) -> Dict:
        g = self._gate
        return {
            "active": self._active, "method": self._method,
            "ship": g.ship if g else False,
            "rejection_reason": g.rejection_reason if g else "not built",
            "half2_raw_ece": g.half2_raw_ece if g else None,
            "half2_recal_ece": g.half2_recal_ece if g else None,
            "note": CALIBRATION_NOTE, "vs_close": "UNPROVEN",
        }


# Propose-only hook (do NOT edit predictor.py directly -- human-gated path):
# In MLBPredictor.__init__: self._prob_recal = MLBProbRecal.from_corpus(games_df)
# In predict(): p_home = self._prob_recal.recal_prob(_mov_p_home(...))

__all__ = [
    "MLBProbRecal", "HalfSplitRecal", "ProbRecalResult",
    "fit_and_gate", "CALIBRATION_NOTE", "NULL_BRIER_TOL",
]
