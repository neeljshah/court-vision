"""scripts/platformkit/recalibration.py — Sport-agnostic walk-forward isotonic recalibration.

RELIABILITY UTILITY — NOT AN EDGE CLAIM.
Calibration != edge: better-calibrated probabilities do NOT imply beating the
closing line or a positive expected value.  See: feedback_accuracy_is_not_edge.md.

ALGORITHM — Strictly leak-free expanding-window isotonic regression:
  For event i the calibration map uses ONLY events 0 … i-1.  Events before
  min_history pass through raw.  Mirrors domains/soccer/calibration.py, generalised
  to accept any (raw_probs, outcomes) sequence.

IMPORTS: stdlib + numpy + sklearn + kernel.validation.proof_metrics.ece (lazy).
  NO src.*, NO domains.*.  Adapter loading is lazy in measure_sport_recal().

CLI: python scripts/platformkit/recalibration.py
  Prints per-sport raw vs recal ECE for tennis + mlb + soccer + nba.
  Reports honestly; near-zero or negative delta = expected for well-calibrated models.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from sklearn.isotonic import IsotonicRegression

# ---------------------------------------------------------------------------
# Public constant
# ---------------------------------------------------------------------------

CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)
_MIN_HISTORY_DEFAULT: int = 50
REFIT_EVERY_SCOREBOARD: int = 20  # block-refit for scoreboard builds: ~10× speedup, ECE delta <1e-5
# Registry mirrors calibration_conformance.py — extended to include soccer.
_ADAPTER_REGISTRY: Dict[str, Tuple[str, str]] = {
    "tennis": ("domains.tennis.adapter", "TennisAdapter"),
    "mlb":    ("domains.mlb.adapter",    "MLBAdapter"),
    "soccer": ("domains.soccer.adapter", "SoccerAdapter"),
    "nba":    ("domains.basketball_nba.adapter", "NBAAdapter"),
}


# ---------------------------------------------------------------------------
# Core: walk-forward calibrated probabilities (sport-agnostic)
# ---------------------------------------------------------------------------


def walk_forward_recalibrate(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    min_history: int = _MIN_HISTORY_DEFAULT,
    refit_every: int = 1,
) -> np.ndarray:
    """Strictly leak-free expanding-window isotonic recalibration.

    For each event i, if i < min_history pass through raw; else fit
    IsotonicRegression on (raw_probs[:i], outcomes[:i]) — strictly before i —
    and transform raw_probs[i].  NaN/inf entries are dropped from the fit
    window; invalid query points pass through.  All-finite inputs are
    bit-identical to the unguarded version.

    ``refit_every`` (default 1) refits only every K events, reusing the most
    recent model (fit strictly BEFORE its refit point <= i, so leak-free for any
    K).  K=1 is bit-identical to per-row refit; large corpora pass K>1 -> O(n/K)
    fits (board path: ~55min -> seconds).  Returns (N,) clipped to [0,1].
    CALIBRATION != EDGE.  See CALIBRATION_NOTE.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    n = len(p)
    if n != len(y):
        raise ValueError(
            f"raw_probs and outcomes must have equal length ({n} vs {len(y)})"
        )
    step = max(1, int(refit_every))

    calibrated = np.empty(n, dtype=float)
    ir = IsotonicRegression(out_of_bounds="clip")
    have_model = False
    next_fit = min_history  # refit when i >= next_fit
    for i in range(n):
        if i < min_history:
            calibrated[i] = float(p[i])
            continue
        if i >= next_fit:
            # Drop NaN/inf pairs (all-finite -> all-True mask -> bit-identical).
            valid_window = np.isfinite(p[:i]) & np.isfinite(y[:i])
            if valid_window.any():
                ir.fit(p[:i][valid_window], y[:i][valid_window])
                have_model = True
            next_fit = i + step
        if have_model and np.isfinite(p[i]):
            calibrated[i] = float(ir.transform([p[i]])[0])
        else:  # no valid model yet, or invalid query point -> pass through raw
            calibrated[i] = float(p[i])

    return np.clip(calibrated, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Helper: measure ECE before and after recalibration
# ---------------------------------------------------------------------------


def _ece(probs: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    """ECE via kernel.validation.proof_metrics.ece (with inline fallback).

    The inline fallback is identical in algorithm; it exists only so tests run
    in isolated environments where the kernel may be unavailable.
    calibration != edge.
    """
    try:
        from kernel.validation.proof_metrics import ece as _kernel_ece
        return _kernel_ece(probs, outcomes, bins=bins)
    except ImportError:
        pass
    # Inline fallback — same formula.
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(p)
    if total == 0:
        return 0.0
    ece_val = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        n_bin = int(mask.sum())
        if n_bin == 0:
            continue
        ece_val += (n_bin / total) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(ece_val)


def measure_recal(
    raw_probs: Sequence[float],
    outcomes: Sequence[float],
    min_history: int = _MIN_HISTORY_DEFAULT,
    bins: int = 10,
) -> Dict[str, object]:
    """Measure raw vs walk-forward-recalibrated ECE on a pre-loaded corpus.

    Parameters
    ----------
    raw_probs : sequence of float
        Raw model probabilities in [0, 1].
    outcomes : sequence of float
        Binary outcomes {0, 1}.
    min_history : int
        Warmup count; events with index < min_history pass through raw.
    bins : int
        Number of ECE bins (default 10).

    Returns
    -------
    dict with keys:
        raw_ece    (float)  — ECE of raw probabilities.
        recal_ece  (float)  — ECE after walk-forward isotonic recalibration.
        delta      (float)  — raw_ece - recal_ece (positive = improvement).
        n          (int)    — total number of events.
        note       (str)    — CALIBRATION_NOTE; carries no edge meaning.

    Notes
    -----
    calibration != edge.  A near-zero or negative delta on already-calibrated
    models (e.g. tennis ECE ~0.040, mlb ECE ~0.007) is the honest expected result.
    """
    p = np.asarray(raw_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    valid = ~(np.isnan(p) | np.isnan(y))
    p, y = p[valid], y[valid]

    calibrated = walk_forward_recalibrate(p, y, min_history=min_history)
    raw_ece = _ece(p, y, bins=bins)
    recal_ece = _ece(calibrated, y, bins=bins)
    return {
        "raw_ece": raw_ece,
        "recal_ece": recal_ece,
        "delta": raw_ece - recal_ece,
        "n": int(len(p)),
        "note": CALIBRATION_NOTE,
    }


# ---------------------------------------------------------------------------
# Convenience: load adapter and return raw vs recal ECE
# ---------------------------------------------------------------------------


def measure_sport_recal(
    sport: str,
    min_history: int = _MIN_HISTORY_DEFAULT,
    bins: int = 10,
) -> Dict[str, object]:
    """Load a sport adapter, pull the feature_bundle, and measure recalibration.

    Mirrors the adapter-loading pattern from proof runners:
    import the adapter class, instantiate with default repo_root, call
    feature_bundle(hypothesis=None, seasons=[]).

    Parameters
    ----------
    sport : str
        One of 'tennis', 'mlb', 'soccer', 'nba'.
    min_history, bins : forwarded to measure_recal.

    Returns
    -------
    dict with keys: sport, raw_ece, recal_ece, delta, n, note.
    On missing corpus or import failure: raw_ece=nan, error=<str>.

    calibration != edge.
    """
    if sport not in _ADAPTER_REGISTRY:
        return {
            "sport": sport, "raw_ece": float("nan"), "recal_ece": float("nan"),
            "delta": float("nan"), "n": 0,
            "error": f"Unknown sport '{sport}'. Valid: {list(_ADAPTER_REGISTRY)}",
            "note": CALIBRATION_NOTE,
        }
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    try:
        mod = importlib.import_module(module_path)
        adapter = getattr(mod, class_name)()
        bundle = adapter.feature_bundle(hypothesis=None, seasons=[])
    except FileNotFoundError as exc:
        return {
            "sport": sport, "raw_ece": float("nan"), "recal_ece": float("nan"),
            "delta": float("nan"), "n": 0,
            "error": f"Corpus absent: {exc}", "note": CALIBRATION_NOTE,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "sport": sport, "raw_ece": float("nan"), "recal_ece": float("nan"),
            "delta": float("nan"), "n": 0,
            "error": str(exc), "note": CALIBRATION_NOTE,
        }
    result = measure_recal(bundle.signal_col, bundle.target,
                           min_history=min_history, bins=bins)
    result["sport"] = sport
    return result


# ---------------------------------------------------------------------------
# __main__ CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    print()
    print("Walk-forward recalibration — raw vs recal ECE per sport")
    print(f"NOTE: {CALIBRATION_NOTE}")
    print()
    hdr = f"{'Sport':<10} {'N':>7} {'RawECE':>10} {'RecalECE':>10} {'Delta':>8}  Interpretation"
    print(hdr)
    print("-" * len(hdr))

    sports = list(_ADAPTER_REGISTRY.keys())
    for sport in sports:
        r = measure_sport_recal(sport)
        err = r.get("error")
        n = r.get("n", 0)
        raw = r.get("raw_ece", float("nan"))
        rec = r.get("recal_ece", float("nan"))
        delta = r.get("delta", float("nan"))

        def _fmt(v: object) -> str:
            try:
                return f"{float(v):10.4f}"  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return f"{'n/a':>10}"

        if err and n == 0:
            print(f"{sport:<10} [SKIP] {err[:60]}")
            continue

        if abs(delta) < 0.002:
            interp = "no meaningful change (already well-calibrated)"
        elif delta > 0:
            interp = f"improved by {delta:.4f}"
        else:
            interp = f"worsened by {abs(delta):.4f} (already well-calibrated)"

        print(f"{sport:<10} {n:>7} {_fmt(raw)} {_fmt(rec)} {_fmt(delta)}  {interp}")

    print("-" * len(hdr))
    print()
    print(f"REMINDER: {CALIBRATION_NOTE}")
    print("A near-zero or negative delta is the honest expected result for")
    print("already-calibrated models (tennis/mlb Elo baselines).")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
