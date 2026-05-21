"""
cohort_calibrator.py — Segmented isotonic calibration for player prop predictions.

Slices predictions into cohorts by (minutes_bin, usage_bin, rest_days) and fits
a separate IsotonicRegression per cohort.  Cohorts with < MIN_COHORT_SAMPLES
observations fall back to the global calibrator.

Architecture
------------
    Cohort key:  (minutes_bin, usage_bin, rest_bin)  — each 3 levels → 27 cells
    Calibrator:  IsotonicRegression(out_of_bounds='clip') per cohort
    Fallback:    Global IsotonicRegression when cohort is undertrained

Public API
----------
    CohortCalibrator.fit(records)       -> CohortCalibrator
    CohortCalibrator.transform(prob, ctx) -> float
    CohortCalibrator.brier_score(records) -> dict
    CohortCalibrator.save(path) / load(path)
    compare_brier(records) -> dict   (global vs cohort Brier scores)
"""

from __future__ import annotations

import logging
import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Minimum samples in a cohort to fit its own calibrator (else use global)
MIN_COHORT_SAMPLES: int = 30

# Bin edges — tuples define (low_edge, high_edge) boundaries
_MINUTES_BINS: List[float] = [0.0, 20.0, 32.0, 999.0]   # lo | mid | hi
_USAGE_BINS:   List[float] = [0.0, 0.15, 0.25, 1.0]      # lo | mid | hi
_REST_BINS:    List[int]   = [0, 1, 3, 99]                # 0-1 | 2-3 | 4+

_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "models",
)


def _minutes_bin(minutes: float) -> int:
    """Map projected minutes to bin index 0-2."""
    for i in range(len(_MINUTES_BINS) - 1):
        if minutes < _MINUTES_BINS[i + 1]:
            return i
    return len(_MINUTES_BINS) - 2


def _usage_bin(usage: float) -> int:
    """Map usage rate (0–1) to bin index 0-2."""
    for i in range(len(_USAGE_BINS) - 1):
        if usage < _USAGE_BINS[i + 1]:
            return i
    return len(_USAGE_BINS) - 2


def _rest_bin(rest_days: int) -> int:
    """Map rest days to bin index 0-2."""
    for i in range(len(_REST_BINS) - 1):
        if rest_days < _REST_BINS[i + 1]:
            return i
    return len(_REST_BINS) - 2


def _cohort_key(
    minutes: float,
    usage: float,
    rest_days: int,
) -> Tuple[int, int, int]:
    """Return a 3-tuple cohort key from raw context values."""
    return (_minutes_bin(minutes), _usage_bin(usage), _rest_bin(rest_days))


def _brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Brier score: mean squared error between probabilities and binary outcomes."""
    return float(np.mean((probs - outcomes) ** 2))


class CohortCalibrator:
    """Segmented isotonic regression calibration for player prop win probabilities.

    Each (minutes_bin, usage_bin, rest_bin) cell has its own IsotonicRegression
    fitted on (predicted_prob, actual_outcome) pairs.  Cells with fewer than
    MIN_COHORT_SAMPLES observations fall back to a global IsotonicRegression.

    Record format (for fit / brier_score):
        {
            "prob":       float,   # raw predicted win probability
            "outcome":    float,   # 1 = over hit, 0 = under hit
            "minutes":    float,   # projected or actual minutes (default 25.0)
            "usage":      float,   # usage rate 0–1 (default 0.20)
            "rest_days":  int,     # days since last game (default 2)
        }

    Context format (for transform):
        {
            "minutes":   float,  # optional, default 25.0
            "usage":     float,  # optional, default 0.20
            "rest_days": int,    # optional, default 2
        }
    """

    def __init__(self) -> None:
        self._cohort_models: Dict[Tuple[int, int, int], object] = {}
        self._global_model: Optional[object] = None

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit(self, records: List[dict]) -> "CohortCalibrator":
        """Fit per-cohort isotonic calibrators from a list of prediction records.

        Args:
            records: List of dicts with keys: prob, outcome, and optionally
                     minutes, usage, rest_days.

        Returns:
            self (for chaining).
        """
        from sklearn.isotonic import IsotonicRegression

        if not records:
            logger.warning("CohortCalibrator.fit: empty records — no calibrators fitted")
            return self

        # Group records by cohort key
        buckets: Dict[Tuple[int, int, int], List[Tuple[float, float]]] = {}
        all_probs: List[float] = []
        all_outcomes: List[float] = []

        for r in records:
            prob    = float(r.get("prob", 0.5))
            outcome = float(r.get("outcome", 0.0))
            mins    = float(r.get("minutes", 25.0))
            usage   = float(r.get("usage",   0.20))
            rest    = int(r.get("rest_days",  2))

            key = _cohort_key(mins, usage, rest)
            buckets.setdefault(key, []).append((prob, outcome))
            all_probs.append(prob)
            all_outcomes.append(outcome)

        # Global fallback model
        gp = np.array(all_probs)
        go = np.array(all_outcomes)
        if len(np.unique(go)) >= 2:
            global_ir = IsotonicRegression(out_of_bounds="clip")
            global_ir.fit(gp, go)
            self._global_model = global_ir
            logger.info("CohortCalibrator: global model fitted on %d samples", len(gp))

        # Per-cohort models
        fitted_count = 0
        skipped_count = 0
        for key, pairs in buckets.items():
            if len(pairs) < MIN_COHORT_SAMPLES:
                skipped_count += 1
                continue
            probs_c   = np.array([p for p, _ in pairs])
            outcomes_c = np.array([o for _, o in pairs])
            if len(np.unique(outcomes_c)) < 2:
                skipped_count += 1
                continue
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(probs_c, outcomes_c)
            self._cohort_models[key] = ir
            fitted_count += 1

        logger.info(
            "CohortCalibrator: fitted %d cohorts, %d fell back to global (< %d samples)",
            fitted_count, skipped_count, MIN_COHORT_SAMPLES,
        )
        return self

    # ── Inference ─────────────────────────────────────────────────────────────

    def transform(self, prob: float, ctx: Optional[dict] = None) -> float:
        """Return calibrated probability for a given raw prob and context.

        Args:
            prob: Raw win probability in [0, 1].
            ctx:  Dict with optional keys: minutes, usage, rest_days.

        Returns:
            Calibrated probability in [0, 1].
        """
        ctx = ctx or {}
        mins  = float(ctx.get("minutes",   25.0))
        usage = float(ctx.get("usage",     0.20))
        rest  = int(ctx.get("rest_days",    2))

        key = _cohort_key(mins, usage, rest)
        model = self._cohort_models.get(key) or self._global_model

        if model is None:
            return float(prob)
        try:
            return float(np.clip(model.predict([float(prob)])[0], 0.0, 1.0))
        except Exception:
            return float(prob)

    # ── Evaluation ────────────────────────────────────────────────────────────

    def brier_score(self, records: List[dict]) -> dict:
        """Compute Brier score of calibrated probabilities on supplied records.

        Returns:
            {"n": int, "brier_cohort": float, "brier_raw": float,
             "improvement": float}  where improvement > 0 means cohort is better.
        """
        if not records:
            return {"n": 0, "brier_cohort": float("nan"),
                    "brier_raw": float("nan"), "improvement": 0.0}

        raw_probs: List[float] = []
        cal_probs: List[float] = []
        outcomes:  List[float] = []

        for r in records:
            prob    = float(r.get("prob",    0.5))
            outcome = float(r.get("outcome", 0.0))
            ctx     = {k: r[k] for k in ("minutes", "usage", "rest_days") if k in r}

            raw_probs.append(prob)
            cal_probs.append(self.transform(prob, ctx))
            outcomes.append(outcome)

        raw_arr = np.array(raw_probs)
        cal_arr = np.array(cal_probs)
        out_arr = np.array(outcomes)

        b_raw    = _brier(raw_arr, out_arr)
        b_cohort = _brier(cal_arr, out_arr)
        return {
            "n": len(records),
            "brier_cohort": round(b_cohort, 6),
            "brier_raw":    round(b_raw, 6),
            "improvement":  round(b_raw - b_cohort, 6),
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        """Persist calibrators to disk via pickle."""
        if path is None:
            path = os.path.join(_MODEL_DIR, "cohort_calibrator.pkl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "cohort_models": self._cohort_models,
                "global_model":  self._global_model,
                "min_samples":   MIN_COHORT_SAMPLES,
            }, f)
        logger.info("CohortCalibrator saved to %s", path)
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "CohortCalibrator":
        """Load calibrators from disk."""
        if path is None:
            path = os.path.join(_MODEL_DIR, "cohort_calibrator.pkl")
        with open(path, "rb") as f:
            data = pickle.load(f)
        obj = cls()
        obj._cohort_models = data.get("cohort_models", {})
        obj._global_model  = data.get("global_model", None)
        return obj


# ── Module-level comparison helper ───────────────────────────────────────────

def compare_brier(records: List[dict]) -> dict:
    """Fit both a global and cohort calibrator on records and compare Brier scores.

    Uses an 80/20 train/eval split.  Logs and returns a comparison dict.

    Args:
        records: List of dicts with keys: prob, outcome, minutes, usage, rest_days.

    Returns:
        {
            "n_train": int, "n_eval": int,
            "global_brier": float, "cohort_brier": float,
            "improvement": float,   # global - cohort (positive = cohort wins)
            "cohort_wins": bool,
        }
    """
    from sklearn.isotonic import IsotonicRegression

    if len(records) < 10:
        logger.warning("compare_brier: only %d records — returning empty comparison",
                       len(records))
        return {"n_train": 0, "n_eval": 0, "global_brier": float("nan"),
                "cohort_brier": float("nan"), "improvement": 0.0, "cohort_wins": False}

    rng = np.random.default_rng(42)
    idx = rng.permutation(len(records))
    split = int(len(records) * 0.8)
    train_recs = [records[i] for i in idx[:split]]
    eval_recs  = [records[i] for i in idx[split:]]

    # Global calibrator
    gp = np.array([float(r.get("prob", 0.5)) for r in train_recs])
    go = np.array([float(r.get("outcome", 0.0)) for r in train_recs])
    global_ir = IsotonicRegression(out_of_bounds="clip")
    if len(np.unique(go)) >= 2:
        global_ir.fit(gp, go)

    ep  = np.array([float(r.get("prob",    0.5)) for r in eval_recs])
    eo  = np.array([float(r.get("outcome", 0.0)) for r in eval_recs])
    try:
        global_cal = global_ir.predict(ep)
    except Exception:
        global_cal = ep
    global_brier = _brier(global_cal, eo)

    # Cohort calibrator
    cohort_cal = CohortCalibrator().fit(train_recs)
    cohort_scores = cohort_cal.brier_score(eval_recs)
    cohort_brier = cohort_scores["brier_cohort"]

    improvement = round(global_brier - cohort_brier, 6)
    result = {
        "n_train": len(train_recs),
        "n_eval":  len(eval_recs),
        "global_brier":  round(global_brier, 6),
        "cohort_brier":  round(cohort_brier, 6),
        "improvement":   improvement,
        "cohort_wins":   improvement > 0,
    }
    logger.info(
        "compare_brier: global=%.5f  cohort=%.5f  improvement=%.5f  cohort_wins=%s",
        global_brier, cohort_brier, improvement, result["cohort_wins"],
    )
    print(
        f"[cohort_calibrator] Brier comparison — "
        f"global={global_brier:.5f}  cohort={cohort_brier:.5f}  "
        f"improvement={improvement:+.5f}  "
        f"({'cohort wins' if result['cohort_wins'] else 'global wins or tie'})"
    )
    return result
